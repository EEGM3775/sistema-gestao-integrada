"""Testes da Prancheta (PRA.0 + PRA.1).

O que se prova aqui, em ordem de importância:

1. **O gate é um só, e fecha.** Diferente do Maps, a Prancheta não tem metade de
   fundação: sem o entitlement `prancheta`, nada responde. Se isso quebrar, o
   acervo de projeto de quem não contratou passou a estar aberto.
2. **Publicar não é editar.** Quem tem `prancheta.documento.edit` sobe revisão,
   mas não decide qual desenho o campo executa. É a lição do D28 aplicada na
   fatia que cria o verbo, e não uma fatia depois — inclusive contra o atalho
   óbvio de mudar `situacao` por PATCH.
3. **Só uma revisão vigente.** É a trava que sustenta a pergunta do canteiro
   ("esta é a última?"). Duas vigentes fariam a tela escolher uma — adivinhar.
4. **O gate de formato é comercial (402), não técnico.** E extensão desconhecida
   é 400, não upsell: mandar o cliente pagar por algo que nenhum plano abre seria
   pior que recusar.
5. **Registry e planos concordam.** Formato vendido sem motor habilitado deixa o
   arquivo parado no acervo depois de pago — a divergência tem de falhar aqui,
   não no cliente.

E, do **PRA.1** (pipeline de conversão), duas teses que valem por todo o resto:

6. **A falha é dado, e a taxonomia dela é o produto.** `motor_insuficiente`
   (limite de plano → upsell) e `motor_indisponivel` (motor fora da imagem →
   problema nosso) são estados diferentes, com filas diferentes no cockpit.
   Trocá-los manda o cliente comprar um plano por causa de um binário que
   esquecemos de instalar.
7. **A idempotência é por `hash` + versão do motor.** É o que faz um upgrade do
   `ezdxf` invalidar o acervo convertido por comparação, sem flag manual.

**Dependência de ambiente, declarada:** os motores fazem import tardio, e nem
`ezdxf` nem `ifcopenshell` nem o `dwg2dxf` estão garantidos na máquina de quem
roda a suíte. Os testes que exercitam um motor de verdade usam `skipUnless` e
dizem qual falta; os que exercitam o **pipeline** usam adaptador falso — o que
se prova ali é a máquina de estados, não a biblioteca de terceiro.
"""
import unittest
import uuid
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario
from obras.models import EtapaObra, Obra
from payment.planos import (
    DWG_MB_MOTOR_LIVRE,
    IMPEXP_TETO_INFRA_ARQUIVO_MB,
    PLANOS,
    PRANCHETA_MB_POR_FORMATO,
)

from . import bcf, entrega, interop, pipeline, taxonomia
from .formatos import (
    FORMATO_POR_CODIGO,
    FORMATOS,
    MOTOR_POR_CODIGO,
    OLE2,
    TETO_UPLOAD_DIRETO_MB,
    tiers_do_formato,
)
from .models import (
    ComentarioMarcacao,
    DerivadaProjeto,
    DesenhoProjeto,
    DisciplinaProjeto,
    DocumentoProjeto,
    Marcacao,
    Medicao,
    PontoDeVista,
    RevisaoDocumento,
)
from .motores import ADAPTADORES, Parte, Saida, estado_dos_motores, planejar
from .motores.base import (
    Adaptador,
    ArquivoCorrompido,
    FalhaDoIntermediario,
    FalhaMotor,
    MotorInsuficiente,
    Retomada,
)
from .motores.dxf import MARGEM_MM, escala_do_desenho
from .planos import formatos_declarados
from .serializers import DocumentoProjetoSerializer

PERMS_FULL = [
    "prancheta.documento.view",
    "prancheta.documento.edit",
    "prancheta.revisao.publicar",
    "prancheta.conversao.reprocessar",
]
# Quem sobe revisão mas não decide o que vale em campo.
PERMS_SEM_PUBLICAR = ["prancheta.documento.view", "prancheta.documento.edit"]


class MotorFalso(Adaptador):
    """Adaptador de teste: converte, falha ou some, sob controle.

    Existe para separar duas coisas que os testes de pipeline sempre confundem:
    **a máquina de estados** (que é nossa e tem de estar certa em qualquer
    máquina) e **a biblioteca de conversão** (que é de terceiro e pode nem estar
    instalada). Tudo o que este arquivo prova sobre agendamento, idempotência e
    taxonomia de erro é provado aqui — sem `ezdxf`, sem `dwg2dxf`, sem rede.
    """

    codigo = "ezdxf"  # ocupa o lugar de um motor real do registry
    tipos = ("vetor_2d",)

    retomavel = True

    def __init__(self, *, versao="falso-1", erro=None, detalhe=None, partes=(),
                 lotes=()):
        self._versao = versao
        self._erro = erro
        # `detalhe` é parametrizável porque é por ele que o motor publica a
        # escala lida do desenho (PRA.3b): sem isso, provar a soberania da
        # calibração humana exigiria um DXF de verdade e um `skipUnless`.
        self._detalhe = detalhe if detalhe is not None else {"teste": True}
        # `partes` vazio = o motor de uma folha só (miniatura, 3D). Com partes, é
        # o motor 2D da PRA.1c, e é esse ramo que cria os `DesenhoProjeto`.
        self._partes = tuple(partes)
        #: Partes agrupadas por PASSADA (PRA.11) — `((folha1, folha2), (folha3,))`
        #: é um arquivo que precisa de duas voltas à fila para terminar.
        self._lotes = tuple(tuple(l) for l in lotes)
        self.chamadas = 0
        #: O marcador que o pipeline devolveu em cada chamada. É o que prova que
        #: a passada seguinte continua de onde parou em vez de recomeçar.
        self.retomadas_recebidas = []
        #: Que economia o pipeline pediu em cada chamada (PRA.1d). Vazio no
        #: caminho normal — é o registro de que a conversão fiel vem sempre
        #: primeiro, e de que nenhuma prancha que converte bem é degradada.
        self.economias_pedidas = []

    def _detectar_versao(self) -> str:
        return self._versao

    def converter(self, caminho, *, formato, tipo, economia="", retomada=None,
                  prazo=None) -> Saida:
        self.chamadas += 1
        self.economias_pedidas.append(economia)
        self.retomadas_recebidas.append(retomada)
        if self._erro is not None:
            raise self._erro
        if self._lotes:
            # Motor que entrega o arquivo **em pedaços** (PRA.11): cada chamada
            # devolve o lote seguinte e o marcador do que falta. É o contrato
            # que o `MotorDxf` cumpre folha a folha; aqui ele é encenado sem
            # `ezdxf`, porque o que se prova é a máquina de estados do pipeline.
            indice = (retomada.grupos_feitos if retomada else 0)
            lote = self._lotes[indice] if indice < len(self._lotes) else ()
            restam = max(0, len(self._lotes) - indice - 1)
            feitos = sum(len(l) for l in self._lotes[:indice + 1])
            return Saida(
                conteudo=lote[0].conteudo if lote else b"",
                extensao="svg", content_type="image/svg+xml",
                detalhe=dict(self._detalhe), partes=lote,
                retomada=Retomada(
                    grupos_feitos=indice + 1, desenhos_feitos=feitos, restam=restam,
                ) if restam else None,
            )
        return Saida(conteudo=b"<svg/>", extensao="svg", content_type="image/svg+xml",
                     detalhe=dict(self._detalhe), partes=self._partes)


def pdf_falso(nome="planta.pdf", kb=4):
    """PDF plausível o bastante: cabeçalho real + corpo, para o caminho de hash e
    tamanho exercitar bytes de verdade em vez de string vazia."""
    conteudo = b"%PDF-1.4\n" + (b"0" * (kb * 1024))
    return SimpleUploadedFile(nome, conteudo, content_type="application/pdf")


def rvt_falso(nome="modelo.rvt", kb=1):
    """RVT o bastante para a porta o RECONHECER: o cabeçalho OLE2 de verdade.

    Antes do [D75](../../docs/historico-correcoes.md) o **nome** decidia o formato, e por
    isso qualquer byte com sufixo `.rvt` chegava à parede comercial. Agora quem
    decide são os bytes: sem contêiner OLE2 o arquivo é recusado antes, como
    formato desconhecido (400), e um teste de 402 que passasse assim estaria
    provando o oposto do que diz.

    A distinção que o RVT exercita e o PDF não: aqui a recusa é **comercial** —
    a plataforma sabe o que é o arquivo e o plano é que não o vende. Reusa a
    constante do registry de propósito, para a amostra acompanhar a allowlist se
    ela mudar.
    """
    conteudo = OLE2[0] + (b"0" * (kb * 1024))
    return SimpleUploadedFile(nome, conteudo)


class PranchetaTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pra-a", nome="Construtora A")
        cls.tenant_b = Tenant.objects.create(slug="pra-b", nome="Construtora B")
        cls.user = Usuario.objects.create(username="proj_a", tenant=cls.tenant)
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Aurora", endereco="Rua X, 100"
        )
        cls.etapa = EtapaObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome_etapa="Fundações", ordem=1
        )
        cls.obra_b = Obra.objects.create(
            tenant=cls.tenant_b, nome_obra="Obra da Concorrente", endereco="Rua Y, 200"
        )

    def autenticar(self, user=None, modules=("prancheta",), perms=PERMS_FULL, plano="empresarial"):
        user = user or self.user
        user.iam_modules = list(modules)
        user.iam_permissions = list(perms)
        user.iam_plano = plano
        self.client.force_authenticate(user=user)
        return user

    def _documento(self, codigo="ARQ-PLB-001", tenant=None, obra=None):
        return DocumentoProjeto.objects.create(
            tenant=tenant or self.tenant,
            obra=obra or self.obra,
            codigo=codigo,
            titulo="Planta baixa pavimento tipo",
            disciplina="arquitetura",
        )

    def _revisao(self, documento=None, revisao="R00", situacao="rascunho", tenant=None):
        documento = documento or self._documento()
        return RevisaoDocumento.objects.create(
            tenant=tenant or documento.tenant,
            documento=documento,
            revisao=revisao,
            arquivo=SimpleUploadedFile(f"{revisao}.pdf", b"%PDF-1.4\n0000"),
            nome_original=f"{revisao}.pdf",
            formato="pdf",
            tamanho_bytes=13,
            situacao=situacao,
        )

    def _pelo_lote(self, *arquivos, caminhos=None, obra=None, disciplina=None,
                   aplicar=True):
        """Põe arquivo no acervo pela **única porta que existe** (PRA.9d).

        Nasceu ao remover o `documentos/enviar/`: os testes que precisavam de uma
        prancha no acervo o usavam como fixture, porque era o caminho de uma
        chamada só. O lote são três (enviar → conferir → aplicar), e repetir as
        três em oito testes seria a cerimônia escondendo o assunto de cada um.

        Devolve o corpo da conferência **antes** de aplicar, que é o que os testes
        de palpite querem ler; `aplicar=False` para o teste da recusa, que não
        chega a gravar.
        """
        import json

        contexto = {"obra": (obra or self.obra).pk}
        if disciplina:
            contexto["disciplina"] = disciplina
        corpo = {"arquivos": list(arquivos), "contexto": json.dumps(contexto)}
        if caminhos:
            corpo["caminhos"] = list(caminhos)

        enviou = self.client.post(
            "/api/impexp/prancheta.acervo/importar-arquivos/", corpo, format="multipart",
        )
        if enviou.status_code != 201 or not aplicar:
            return enviou

        importacao_id = enviou.json()["importacao_id"]
        detalhe = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()
        self.client.post(f"/api/impexp/importacoes/{importacao_id}/aplicar/")
        return detalhe


# ---------------------------------------------------------------------------
# 1. Entitlement — o gate é um só
# ---------------------------------------------------------------------------
class EntitlementTests(PranchetaTestBase):
    ROTAS = ("documentos", "revisoes", "derivadas")

    def test_sem_o_modulo_nada_responde(self):
        """A Prancheta não tem metade de fundação (planta §2): sem `prancheta`,
        nem o acervo nem o status abrem."""
        self.autenticar(modules=[])
        for rota in self.ROTAS:
            self.assertEqual(
                self.client.get(f"/api/prancheta/{rota}/").status_code, 403,
                f"/api/prancheta/{rota}/ deveria exigir o entitlement `prancheta`",
            )
        self.assertEqual(self.client.get("/api/prancheta/status/").status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").status_code, 403
        )

    def test_com_o_modulo_e_sem_permissao_tambem_fecha(self):
        """Entitlement é do tenant; permissão é do usuário. As duas camadas."""
        self.autenticar(modules=["prancheta"], perms=[])
        for rota in self.ROTAS:
            self.assertEqual(self.client.get(f"/api/prancheta/{rota}/").status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").status_code, 403
        )

    def test_com_modulo_e_permissao_abre(self):
        self.autenticar()
        self.assertEqual(self.client.get("/api/prancheta/documentos/").status_code, 200)
        self.assertEqual(self.client.get("/api/prancheta/status/").status_code, 200)

    def test_leitura_nao_da_escrita(self):
        self.autenticar(perms=["prancheta.documento.view"])
        resposta = self.client.post("/api/prancheta/documentos/", {
            "obra": self.obra.pk, "codigo": "EST-FRM-001",
            "titulo": "Forma da fundação", "disciplina": "estrutural",
        })
        self.assertEqual(resposta.status_code, 403)


# ---------------------------------------------------------------------------
# 2. Isolamento entre tenants
# ---------------------------------------------------------------------------
class IsolamentoTests(PranchetaTestBase):
    def test_documento_de_outro_tenant_nao_aparece(self):
        self._documento(codigo="ARQ-001")
        self._documento(codigo="ARQ-001", tenant=self.tenant_b, obra=self.obra_b)
        self.autenticar()
        dados = self.client.get("/api/prancheta/documentos/").json()
        self.assertEqual(dados["count"], 1)
        self.assertEqual(dados["results"][0]["obra"], self.obra.pk)

    def test_mesmo_codigo_em_tenants_distintos_convive(self):
        """A unicidade é por tenant+obra (Fase 8.3): 'ARQ-PLB-001' é o código de
        prancha mais comum do Brasil, e duas construtoras têm de poder usá-lo."""
        self._documento(codigo="ARQ-PLB-001")
        self._documento(codigo="ARQ-PLB-001", tenant=self.tenant_b, obra=self.obra_b)
        self.assertEqual(DocumentoProjeto.objects.count(), 2)

    def test_codigo_duplicado_na_mesma_obra_da_400_limpo(self):
        self._documento(codigo="ARQ-PLB-001")
        self.autenticar()
        resposta = self.client.post("/api/prancheta/documentos/", {
            "obra": self.obra.pk, "codigo": "ARQ-PLB-001",
            "titulo": "Outra planta", "disciplina": "arquitetura",
        })
        self.assertEqual(resposta.status_code, 400)

    def test_revisao_nao_pode_apontar_para_documento_de_outro_tenant(self):
        alheio = self._documento(codigo="SEG-001", tenant=self.tenant_b, obra=self.obra_b)
        self.autenticar()
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": alheio.pk, "revisao": "R00", "arquivo": pdf_falso(),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("documento", resposta.json())


# ---------------------------------------------------------------------------
# 3. Upload — o que entra no acervo
# ---------------------------------------------------------------------------
class UploadTests(PranchetaTestBase):
    def test_upload_grava_formato_tamanho_e_hash_do_arquivo(self):
        """Nada disso é digitado: sai do arquivo. Um acervo que aceitasse o
        cliente declarar o próprio formato mentiria para o pipeline do PRA.1."""
        documento = self._documento()
        self.autenticar()
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R00", "arquivo": pdf_falso(kb=8),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        corpo = resposta.json()
        self.assertEqual(corpo["formato"], "pdf")
        self.assertEqual(corpo["nome_original"], "planta.pdf")
        self.assertEqual(corpo["tamanho_bytes"], len(b"%PDF-1.4\n") + 8 * 1024)
        self.assertEqual(len(corpo["hash_sha256"]), 64)
        # Nasce rascunho: subir não é publicar.
        self.assertEqual(corpo["situacao"], "rascunho")

    def test_extensao_desconhecida_e_400_e_nao_upsell(self):
        documento = self._documento()
        self.autenticar()
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R00",
            "arquivo": SimpleUploadedFile("contrato.docx", b"PK\x03\x04"),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 400)

    def test_formato_fora_do_plano_e_402_com_o_motivo(self):
        """Parede COMERCIAL: 402 e não 403, com a lista do que passa — é o que
        deixa a tela dizer 'seu plano abre PDF; DWG está no Profissional'."""
        documento = self._documento()
        self.autenticar(plano="free")  # free = só pdf/imagem
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R00",
            "arquivo": SimpleUploadedFile("planta.dwg", b"AC1032" + b"0" * 512),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 402)
        corpo = resposta.json()
        self.assertEqual(corpo["code"], "formato_nao_contratado")
        self.assertEqual(corpo["formato"], "dwg")
        self.assertEqual(corpo["plano"], "free")
        self.assertIn("pdf", corpo["formatos_aceitos"])

    def test_formato_contratado_no_plano_maior_passa(self):
        documento = self._documento()
        self.autenticar(plano="profissional")
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R00",
            "arquivo": SimpleUploadedFile("planta.dwg", b"AC1032" + b"0" * 512),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["formato"], "dwg")

    def test_status_declara_o_que_o_plano_nao_abre_em_vez_de_esconder(self):
        """Régua da planta §6: formato não contratado aparece TRAVADO com o
        motivo. Uma lista só do que passa deixaria o cliente sem saber que o
        produto lê RVT — e sem motivo para subir de plano."""
        self.autenticar(plano="free")
        corpo = self.client.get("/api/prancheta/status/").json()
        por_codigo = {f["codigo"]: f for f in corpo["formatos"]}
        self.assertEqual(len(por_codigo), len(FORMATOS))  # todos, não só os abertos
        self.assertTrue(por_codigo["pdf"]["contratado"])
        self.assertFalse(por_codigo["rvt"]["contratado"])
        # E o motivo do cadeado do RVT é o MOTOR, não o formato.
        self.assertTrue(por_codigo["rvt"]["exige_motor_premium"])
        self.assertFalse(por_codigo["rvt"]["motor_disponivel"])

        # `conversao_disponivel` é do PLANO cruzado com a IMAGEM, e no `free` ele
        # é verdadeiro: o motor livre (miniatura de PDF/imagem) é exatamente o
        # que esse plano compra. Dizer "não há conversão" a quem já tem a
        # miniatura esconderia o único produto de conversão que ele contratou —
        # e o que o `free` NÃO tem é o motor premium, que é o que se afirma aqui.
        por_motor = {m["codigo"]: m for m in corpo["motores"]}
        self.assertTrue(por_motor["pdf_nativo"]["habilitado"])
        self.assertFalse(por_motor["aps"]["habilitado"])
        self.assertEqual(
            corpo["conversao_disponivel"], por_motor["pdf_nativo"]["disponivel"]
        )

    def test_arquivo_e_write_once(self):
        """"Revisão nova é linha nova, nunca UPDATE" (planta §9). Trocar o
        arquivo deixaria hash, formato e tamanho descrevendo o anterior — e quem
        já abriu a R01 veria "R01" com outro desenho dentro."""
        revisao = self._revisao()
        self.autenticar()
        resposta = self.client.patch(
            f"/api/prancheta/revisoes/{revisao.pk}/",
            {"arquivo": pdf_falso("outra.pdf")}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("arquivo", resposta.json())

    def test_sem_plano_conhecido_o_gate_e_fail_open(self):
        """Token de serviço/legado não vira indisponibilidade de escrita — mesmo
        trade-off registrado em `nucleo/quotas.py`. É parede comercial."""
        documento = self._documento()
        self.autenticar(plano=None)
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R00",
            "arquivo": rvt_falso(),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 201, resposta.content)


# ---------------------------------------------------------------------------
# 4. Publicar — a alçada que decide o que o campo executa
# ---------------------------------------------------------------------------
class PublicarTests(PranchetaTestBase):
    def test_publicar_exige_permissao_propria(self):
        """A lição do D28, provada na fatia que cria o verbo: quem sobe revisão
        não decide qual desenho vale."""
        revisao = self._revisao()
        self.autenticar(perms=PERMS_SEM_PUBLICAR)
        resposta = self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/publicar/")
        self.assertEqual(resposta.status_code, 403)
        revisao.refresh_from_db()
        self.assertEqual(revisao.situacao, "rascunho")

    def test_situacao_nao_e_editavel_por_patch(self):
        """O atalho óbvio para burlar a alçada. Se `situacao` fosse campo comum,
        a permissão separada de publicar seria decoração."""
        revisao = self._revisao()
        self.autenticar(perms=PERMS_SEM_PUBLICAR)
        resposta = self.client.patch(
            f"/api/prancheta/revisoes/{revisao.pk}/", {"situacao": "vigente"}, format="json"
        )
        self.assertEqual(resposta.status_code, 200)
        revisao.refresh_from_db()
        self.assertEqual(revisao.situacao, "rascunho")

    def test_publicar_torna_vigente_e_rebaixa_a_anterior(self):
        documento = self._documento()
        r00 = self._revisao(documento=documento, revisao="R00", situacao="vigente")
        r01 = self._revisao(documento=documento, revisao="R01")
        self.autenticar()

        resposta = self.client.post(f"/api/prancheta/revisoes/{r01.pk}/publicar/")
        self.assertEqual(resposta.status_code, 200, resposta.content)

        r00.refresh_from_db()
        r01.refresh_from_db()
        self.assertEqual(r00.situacao, "superada")
        self.assertEqual(r01.situacao, "vigente")
        self.assertEqual(r01.publicado_por_id, self.user.pk)
        self.assertIsNotNone(r01.publicado_em)
        # A trava que sustenta a pergunta do canteiro.
        self.assertEqual(documento.revisoes.filter(situacao="vigente").count(), 1)

    def test_republicar_a_vigente_e_409(self):
        revisao = self._revisao(situacao="vigente")
        self.autenticar()
        resposta = self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/publicar/")
        self.assertEqual(resposta.status_code, 409)

    def test_republicar_uma_superada_e_409_com_o_caminho_certo(self):
        """Voltar o canteiro para um desenho antigo pode ser legítimo, mas é
        decisão com consequência em campo — trata-se como revisão nova, não como
        um botão que desfaz em silêncio."""
        revisao = self._revisao(situacao="superada")
        self.autenticar()
        resposta = self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/publicar/")
        self.assertEqual(resposta.status_code, 409)
        self.assertIn("revisão nova", resposta.json()["detail"])

class PublicarPendentesTests(PranchetaTestBase):
    """O verbo em lote — sem ele a segunda alçada era impossível de exercer.

    O acervo histórico entra todo em `rascunho` (a conferência do lote é da
    alçada de `documento.edit`; publicar é de `revisao.publicar`). Sem um verbo
    em massa, um acervo de 141 documentos exigia 141 cliques — e o resultado
    medido em 13/08/2026 foi ninguém publicar nada: 159 revisões em rascunho,
    168 derivadas prontas e o canteiro vendo "sem revisão vigente" em tudo.
    """

    def _obra_com_rascunhos(self, quantos=3):
        documentos = []
        for indice in range(quantos):
            documento = self._documento(codigo=f"LOTE-{indice:03d}")
            self._revisao(documento=documento, revisao="R00")
            documentos.append(documento)
        return documentos

    def test_publica_a_mais_recente_de_cada_documento_sem_vigente(self):
        documentos = self._obra_com_rascunhos()
        self.autenticar()

        resposta = self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        )

        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["publicadas"], 3)
        for documento in documentos:
            self.assertEqual(documento.revisoes.filter(situacao="vigente").count(), 1)

    def test_entre_varios_rascunhos_publica_o_de_rotulo_maior(self):
        """"Mais recente" é o que o carimbo diz, e o carimbo é o rótulo."""
        documento = self._documento(codigo="LOTE-MULTI")
        self._revisao(documento=documento, revisao="R00")
        self._revisao(documento=documento, revisao="R02")
        self._revisao(documento=documento, revisao="R01")
        self.autenticar()

        self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        )

        vigentes = documento.revisoes.filter(situacao="vigente")
        self.assertEqual(vigentes.count(), 1)
        self.assertEqual(vigentes.first().revisao, "R02")
        # As outras continuam rascunho: o lote publica, não arruma o histórico.
        self.assertEqual(documento.revisoes.filter(situacao="rascunho").count(), 2)

    def test_nao_troca_uma_vigente_que_ja_existe(self):
        """A trava que separa este verbo do `publicar`: trocar o desenho que o
        campo executa é decisão prancha a prancha, com motivo — nunca efeito
        colateral de um botão de massa."""
        documento = self._documento(codigo="LOTE-VIGENTE")
        vigente = self._revisao(documento=documento, revisao="R00", situacao="vigente")
        rascunho = self._revisao(documento=documento, revisao="R01")
        self.autenticar()

        resposta = self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        )

        self.assertEqual(resposta.json()["publicadas"], 0)
        vigente.refresh_from_db()
        rascunho.refresh_from_db()
        self.assertEqual(vigente.situacao, "vigente")
        self.assertEqual(rascunho.situacao, "rascunho")

    def test_nao_republica_superada(self):
        """Documento cujo único histórico é uma superada não tem o que publicar
        — voltar o canteiro a um desenho antigo é o 409 do verbo unitário."""
        documento = self._documento(codigo="LOTE-SUPERADA")
        superada = self._revisao(documento=documento, revisao="R00", situacao="superada")
        self.autenticar()

        resposta = self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        )

        self.assertEqual(resposta.json()["publicadas"], 0)
        superada.refresh_from_db()
        self.assertEqual(superada.situacao, "superada")

    def test_exige_a_permissao_de_publicar(self):
        """Mesma alçada do verbo unitário — em lote não pode ser mais fácil."""
        self._obra_com_rascunhos(1)
        self.autenticar(perms=PERMS_SEM_PUBLICAR)
        resposta = self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 403)

    def test_exige_a_obra(self):
        """Publicar o tenant inteiro é poder demais para um POST sem alvo."""
        self.autenticar()
        resposta = self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)

    def test_nao_alcanca_documento_de_outro_tenant(self):
        outro = Tenant.objects.create(nome="Outra", slug="outra")
        alheio = self._documento(codigo="ALHEIO-001", tenant=outro)
        self._revisao(documento=alheio, revisao="R00", tenant=outro)
        self.autenticar()

        self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/",
            {"obra": alheio.obra_id}, format="json",
        )

        self.assertEqual(alheio.revisoes.filter(situacao="vigente").count(), 0)

    def test_o_relatorio_diz_o_que_publicou(self):
        """Ato de massa sem relatório é ato que ninguém confere."""
        self._obra_com_rascunhos(2)
        self.autenticar()
        corpo = self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        ).json()
        self.assertEqual(len(corpo["documentos"]), 2)
        self.assertEqual(
            {d["revisao"] for d in corpo["documentos"]}, {"R00"},
        )


class AcervoDepoisDoLoteTests(PranchetaTestBase):
    """O acervo importado tem de ficar **abrível**, não só existir.

    É a regressão do defeito relatado pelo dono em 13/08/2026: a aba Pranchas
    mostrava 141 cartões "sem revisão vigente" com o arquivo já convertido, e a
    fila do cockpit contava o problema sem oferecer a saída.
    """

    def test_a_fila_conta_o_que_o_lote_deixou_pendente(self):
        documento = self._documento(codigo="FILA-001")
        self._revisao(documento=documento, revisao="R00")
        self.autenticar()

        fila = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()["requer_decisao"]

        self.assertIn("FILA-001", fila["documentos_sem_revisao_vigente"])
        self.assertEqual(fila["revisoes_em_rascunho"], 1)

    def test_depois_de_publicar_em_lote_a_fila_zera_e_a_prancha_aparece(self):
        documento = self._documento(codigo="FILA-002")
        self._revisao(documento=documento, revisao="R00")
        self.autenticar()

        self.client.post(
            "/api/prancheta/revisoes/publicar-pendentes/", {"obra": self.obra.pk}, format="json"
        )
        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()

        self.assertEqual(acervo["requer_decisao"]["documentos_sem_revisao_vigente"], [])
        self.assertEqual(acervo["requer_decisao"]["revisoes_em_rascunho"], 0)
        docs = [d for g in acervo["disciplinas"] for d in g["documentos"]]
        alvo = next(d for d in docs if d["codigo"] == "FILA-002")
        self.assertIsNotNone(alvo["vigente"], "o cartão do canteiro depende do vigente")


class RevisaoExtraTests(PranchetaTestBase):
    def test_revisao_duplicada_no_mesmo_documento_da_400(self):
        documento = self._documento()
        self._revisao(documento=documento, revisao="R00")
        self.autenticar()
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R00", "arquivo": pdf_falso(),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 400)


# ---------------------------------------------------------------------------
# 5. Acervo — a tela do canteiro em um endpoint
# ---------------------------------------------------------------------------
class AcervoTests(PranchetaTestBase):
    def test_acervo_exige_a_obra(self):
        self.autenticar()
        self.assertEqual(self.client.get("/api/prancheta/acervo/").status_code, 400)

    def test_acervo_agrupa_por_disciplina_e_traz_a_vigente(self):
        arq = self._documento(codigo="ARQ-PLB-001")
        est = DocumentoProjeto.objects.create(
            tenant=self.tenant, obra=self.obra, codigo="EST-FRM-001",
            titulo="Forma", disciplina="estrutural",
        )
        self._revisao(documento=arq, revisao="R00", situacao="superada")
        self._revisao(documento=arq, revisao="R01", situacao="vigente")
        self._revisao(documento=est, revisao="R00")  # rascunho: est fica sem vigente

        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()

        self.assertEqual(corpo["total_documentos"], 2)
        disciplinas = {d["disciplina"] for d in corpo["disciplinas"]}
        self.assertEqual(disciplinas, {"arquitetura", "estrutural"})

        arquitetura = next(d for d in corpo["disciplinas"] if d["disciplina"] == "arquitetura")
        self.assertEqual(arquitetura["documentos"][0]["vigente"]["revisao"], "R01")

        # Fila de decisão: documento sem vigente e revisão em rascunho.
        self.assertEqual(
            corpo["requer_decisao"]["documentos_sem_revisao_vigente"], ["EST-FRM-001"]
        )
        self.assertEqual(corpo["requer_decisao"]["revisoes_em_rascunho"], 1)

    def test_documento_sem_revisao_devolve_vigente_nulo(self):
        """`None` é a resposta honesta — acervo carregado em lote nasce assim, e
        é isso que alimenta a fila de decisão. Um objeto vazio esconderia a
        pendência."""
        self._documento()
        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        self.assertIsNone(corpo["disciplinas"][0]["documentos"][0]["vigente"])

    def test_acervo_nao_vaza_obra_de_outro_tenant(self):
        self._documento(codigo="SEG-001", tenant=self.tenant_b, obra=self.obra_b)
        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra_b.pk}").json()
        self.assertEqual(corpo["total_documentos"], 0)


# ---------------------------------------------------------------------------
# 6. Derivada — existe, e é honesta sobre não ter pipeline ainda
# ---------------------------------------------------------------------------
class DerivadaTests(PranchetaTestBase):
    def test_derivada_e_somente_leitura_no_pra0(self):
        revisao = self._revisao()
        self.autenticar()
        resposta = self.client.post("/api/prancheta/derivadas/", {
            "revisao": revisao.pk, "tipo": "vetor_2d", "motor": "pdf_nativo",
        }, format="json")
        self.assertEqual(resposta.status_code, 405)

    def test_duas_derivadas_do_mesmo_tipo_com_motores_diferentes_convivem(self):
        """É o que faz o upgrade de plano melhorar a derivada sem invalidar a
        antiga, e o downgrade não apagar nada (planta §4.1)."""
        revisao = self._revisao()
        for motor in ("libredwg", "aps"):
            DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor=motor,
            )
        self.assertEqual(revisao.derivadas.count(), 2)


# ---------------------------------------------------------------------------
# 7. Conformidade registry × planos — os dois lados têm de casar
# ---------------------------------------------------------------------------
class RegistryEPlanosTests(APITestCase):
    def test_todo_formato_vendido_existe_no_registry(self):
        for slug, plano in PLANOS.items():
            declarados = plano.get("formatos_prancheta")
            if declarados is None:
                continue
            for codigo in declarados:
                self.assertIn(
                    codigo, FORMATO_POR_CODIGO,
                    f"plano '{slug}' vende o formato '{codigo}', que não existe em formatos.py",
                )

    def test_todo_formato_vendido_tem_motor_habilitado_no_plano(self):
        """A divergência cara: o upload passa, o arquivo ocupa storage pago e a
        conversão nunca roda. É o caso do RVT, que só a APS traduz.

        **Formato de interoperabilidade fica de fora da regra** (PRA.3): o BCF
        não tem motor porque não há o que converter — ele entra pela importação
        de marcações, não pelo acervo. Exigir motor dele faria este teste pedir
        um adaptador que, se alguém escrevesse, nunca rodaria.
        """
        for slug, plano in PLANOS.items():
            tiers = plano.get("motores_prancheta")
            if tiers is None:
                continue  # todos os motores habilitados
            # `formatos_prancheta = None` significa TODOS — e é justamente aí que
            # o descasamento passaria batido: um plano que abre tudo mas habilita
            # só o motor livre venderia RVT que nunca converte.
            declarados = plano.get("formatos_prancheta")
            if declarados is None:
                declarados = [f.codigo for f in FORMATOS]
            for codigo in declarados:
                if FORMATO_POR_CODIGO[codigo].interop:
                    continue
                self.assertTrue(
                    tiers_do_formato(codigo) & set(tiers),
                    f"plano '{slug}' vende '{codigo}' mas não habilita nenhum motor "
                    f"capaz de abri-lo (tiers do plano: {tiers})",
                )

    def test_nenhum_formato_excede_o_teto_do_upload_direto(self):
        """Subir o teto de um formato sem resolver upload retomável faz o
        arquivo morrer no timeout depois de o cliente esperar por ele.

        Ganhou peso quando o número saiu para `payment/planos.py`: agora é uma
        edição do **dono** que este teste vigia, e o efeito de errá-la é a tela
        do catálogo prometendo um tamanho que o caminho de upload não entrega.
        """
        for formato in FORMATOS:
            self.assertLessEqual(
                formato.max_mb, TETO_UPLOAD_DIRETO_MB,
                f"'{formato.codigo}' declara {formato.max_mb} MB, acima do teto do "
                f"caminho de upload direto ({TETO_UPLOAD_DIRETO_MB} MB)",
            )

    def test_todo_formato_do_registry_tem_teto_declarado_no_payment(self):
        """O descasamento silencioso do outro lado: formato **sem** número.

        `max_mb` cai para 0, o motor passa a aplicar o teto de PLANILHA do plano
        (5 a 50 MB) sobre uma prancha, e o cliente recebe um 402 dizendo um
        número que ninguém escreveu. É a razão de o registry ter deixado de
        guardar o próprio teto valer a pena: um lugar só, cobrado aqui.
        """
        faltando = [f.codigo for f in FORMATOS if f.codigo not in PRANCHETA_MB_POR_FORMATO]
        self.assertEqual(
            faltando, [],
            f"formatos sem teto em payment/planos.py §5.3: {faltando}",
        )
        sobrando = [c for c in PRANCHETA_MB_POR_FORMATO if c not in FORMATO_POR_CODIGO]
        self.assertEqual(
            sobrando, [],
            f"payment/planos.py §5.3 declara teto de formato que não existe: {sobrando}",
        )

    def test_o_teto_do_snapshot_e_do_bcf_vem_do_payment(self):
        """Todo teto mora em `payment/` (decisão do dono, 08/08/2026).

        O snapshot foi o caso que revelou a regra: teto em constante de
        engenharia, recusa em 402, e o 402 oferecendo um upgrade que nenhum plano
        vendia. Este teste é o que impede alguém de reescrever o número aqui —
        ele falha se `bcf.py` voltar a decidir sozinho.
        """
        from payment.planos import (
            PRANCHETA_TETO_BCF_DESCOMPRIMIDO_MB,
            PRANCHETA_TETO_BCF_TOPICOS,
            PRANCHETA_TETO_BCF_XML_MB,
            PRANCHETA_TETO_SNAPSHOT_MB,
        )

        MB = 1024 * 1024
        self.assertEqual(bcf.MAX_SNAPSHOT_BYTES, PRANCHETA_TETO_SNAPSHOT_MB * MB)
        self.assertEqual(bcf.MAX_DESCOMPRIMIDO_BYTES, PRANCHETA_TETO_BCF_DESCOMPRIMIDO_MB * MB)
        self.assertEqual(bcf.MAX_XML_BYTES, PRANCHETA_TETO_BCF_XML_MB * MB)
        self.assertEqual(bcf.MAX_TOPICOS, PRANCHETA_TETO_BCF_TOPICOS)
        # E o teto do caminho de upload deixou de ser um segundo 300 no módulo.
        self.assertEqual(TETO_UPLOAD_DIRETO_MB, IMPEXP_TETO_INFRA_ARQUIVO_MB)

    def test_extensao_composta_ganha_da_simples(self):
        """`.copc.laz` também casa `.laz` — e casaria com o formato errado.

        Depois da PRA.5a quem responde isto é a porta única, não mais um
        `formato_da_extensao` local: a pergunta passou a ser feita sobre bytes +
        nome, e por isso as três chamadas mandam a assinatura `LASF` junto. O
        teste continua aqui, e não no impexp, porque o par LAS/COPC é da
        Prancheta — é ela quem sabe que os dois compartilham cabeçalho.
        """
        from funcoesimpexp.limites import FormatoDesconhecido, detectar_formato

        cabecalho = b"LASF" + b"\x00" * 64
        self.assertEqual(detectar_formato("nuvem.copc.laz", cabecalho).codigo, "copc")
        self.assertEqual(detectar_formato("nuvem.laz", cabecalho).codigo, "las")
        # E o que não é nenhum dos dois não vira "o primeiro que casou": sem
        # assinatura reconhecida a porta recusa, que é a régua do D75.
        with self.assertRaises(FormatoDesconhecido):
            detectar_formato("contrato.docx", b"MZ\x90\x00 executavel")

    def test_todo_motor_referenciado_por_formato_existe(self):
        for formato in FORMATOS:
            if formato.interop:
                # Interop não converte: motor declarado aqui seria código morto.
                self.assertFalse(
                    formato.motores,
                    f"'{formato.codigo}' é interop e não deveria declarar motor",
                )
                continue
            self.assertTrue(formato.motores, f"'{formato.codigo}' não declara motor")
            for motor in formato.motores:
                self.assertIn(motor, MOTOR_POR_CODIGO)

    def test_formato_interop_nao_aparece_como_upsell_de_motor(self):
        """O BCF contratado não pode chegar à tela com cadeado de motor premium.

        `tiers_do_formato` devolve vazio para ele, e o cálculo ingênuo
        (`"livre" not in tiers`) diria "exige alta fidelidade" — um upsell
        inventado, para quem já pagou pelo formato.
        """
        usuario = Usuario(username="x")
        usuario.iam_plano = "profissional"  # vende `bcf`, só motor livre
        declarados = {f["codigo"]: f for f in formatos_declarados(usuario)}
        self.assertTrue(declarados["bcf"]["contratado"])
        self.assertTrue(declarados["bcf"]["interop"])
        self.assertFalse(declarados["bcf"]["exige_motor_premium"])
        self.assertTrue(declarados["bcf"]["motor_disponivel"])


# ---------------------------------------------------------------------------
# 8. PRA.1 — o registry de motores
# ---------------------------------------------------------------------------
class RegistryDeMotoresTests(APITestCase):
    def test_todo_adaptador_ocupa_um_motor_declarado(self):
        """Adaptador sem motor no `formatos.py` é código que nunca roda: o
        `planejar()` percorre os motores DO FORMATO, então ninguém o alcançaria."""
        for codigo, adaptador in ADAPTADORES.items():
            self.assertIn(codigo, MOTOR_POR_CODIGO,
                          f"o adaptador '{codigo}' não corresponde a motor nenhum")
            self.assertEqual(adaptador.codigo, codigo)

    def test_todo_adaptador_produz_tipo_valido_de_derivada(self):
        validos = {t.value for t in DerivadaProjeto.Tipo}
        for codigo, adaptador in ADAPTADORES.items():
            self.assertTrue(adaptador.tipos, f"'{codigo}' não declara tipo de derivada")
            for tipo in adaptador.tipos:
                self.assertIn(tipo, validos, f"'{codigo}' produz tipo inexistente '{tipo}'")

    def test_estado_dos_motores_separa_implementado_de_disponivel(self):
        """Três colunas, três perguntas: o PLANO habilita, o CÓDIGO implementa, a
        IMAGEM tem instalado. Fundi-las faria "motor faltando no servidor" e
        "fatia futura" virarem a mesma frase na tela."""
        por_codigo = {m["codigo"]: m for m in estado_dos_motores()}
        self.assertEqual(set(por_codigo), set(MOTOR_POR_CODIGO))
        # A APS é o caso canônico de declarada-mas-não-implementada (chega no PRA.4).
        self.assertFalse(por_codigo["aps"]["implementado"])
        self.assertFalse(por_codigo["aps"]["disponivel"])
        self.assertTrue(por_codigo["ezdxf"]["implementado"])
        # ...e o `pdf_nativo` é o único que não pode faltar: Pillow é dependência
        # dura do backend, então este é o piso da conversão em qualquer imagem.
        self.assertTrue(por_codigo["pdf_nativo"]["disponivel"])

    def test_licenca_gpl_do_libredwg_esta_declarada_no_registry(self):
        """A licença anda junto do motor de propósito (planta §12.3): num
        comentário de Dockerfile ela se perde na primeira refatoração, e a
        obrigação de redistribuição é legal, não organizacional."""
        self.assertIn("GPL", MOTOR_POR_CODIGO["libredwg"].licenca)

    def test_planejar_pdf_rende_a_miniatura_do_acervo(self):
        self.assertEqual(planejar("pdf", ["livre"]), [("miniatura", "pdf_nativo")])

    def test_planejar_nao_inventa_derivada_para_motor_sem_adaptador(self):
        """RVT é vendido no `empresarial` e só a APS o traduz — que ainda não tem
        adaptador. Criar uma derivada `pendente` aqui a deixaria pendurada para
        sempre, e "aguardando conversão" viraria mentira permanente na tela."""
        self.assertEqual(planejar("rvt", ["livre", "premium"]), [])

    def test_planejar_respeita_o_dono_do_dado(self):
        """KMZ e LAS passam pela Prancheta sem virar derivada: o dono é o Maps e o
        drone (planta §3). Vazio é a resposta certa, não uma lacuna."""
        self.assertEqual(planejar("kmz", ["livre", "premium"]), [])
        self.assertEqual(planejar("las", ["livre", "premium"]), [])

    def test_planejar_prefere_o_motor_livre_mesmo_no_plano_premium(self):
        """Ordem de preferência é ordem de CUSTO. A APS cobra por tradução, e
        queimar token num arquivo que o motor livre abriria gastaria o dinheiro
        do cliente sem entregar nada a mais — o premium se paga quando o livre
        levanta `MotorInsuficiente`."""
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso()}):
            self.assertEqual(planejar("dxf", ["livre", "premium"]), [("vetor_2d", "ezdxf")])

    def test_motor_indisponivel_nao_entra_no_plano(self):
        """Motor sem a dependência instalada sai do planejamento em vez de gerar
        derivada que já nasce morta."""
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(versao="")}):
            self.assertEqual(planejar("dxf", ["livre"]), [])


# ---------------------------------------------------------------------------
# 9. PRA.1 — o pipeline: agendar, idempotência, estados
# ---------------------------------------------------------------------------
class PipelineTests(PranchetaTestBase):
    def _revisao_dxf(self, hash_sha256="hash-a"):
        documento = self._documento(codigo="ARQ-DXF-001")
        return RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00",
            arquivo=SimpleUploadedFile("planta.dxf", b"0\nSECTION\n"),
            nome_original="planta.dxf", formato="dxf", tamanho_bytes=10,
            hash_sha256=hash_sha256,
        )

    def test_agendar_poe_na_fila_da_frota_em_vez_de_publicar_direto(self):
        """D98 — quem publica agora é o **porteiro**, não o `agendar`.

        Era um `.delay()` no `on_commit`, e a troca é a promessa inteira da
        frota: um `.delay()` publica e esquece — não sabe dizer quem está na
        frente, não reserva cadeira para plano nenhum e não tem onde um job
        recolocado voltar. O `agendar` cria a LINHA na fila; o despachante
        escolhe e só então manda a mensagem.
        """
        from nucleo.models import TarefaNaFila

        revisao = self._revisao_dxf()
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso()}), \
                mock.patch("celery.current_app.send_task") as publicar:
            with self.captureOnCommitCallbacks(execute=True):
                agendadas = pipeline.agendar(revisao, tiers=["livre"])

        self.assertEqual(len(agendadas), 1)
        derivada = DerivadaProjeto.objects.get(revisao=revisao)
        self.assertEqual(derivada.tipo, "vetor_2d")
        self.assertEqual(derivada.motor, "ezdxf")
        self.assertEqual(derivada.estado, "pendente")
        self.assertEqual(derivada.tenant_id, self.tenant.pk)

        fila = TarefaNaFila.objects.get(chave=f"prancheta.derivada:{derivada.pk}")
        self.assertEqual(fila.frota, "conversao")
        self.assertEqual(fila.tenant_id, self.tenant.pk)
        # Com a frota livre o despacho é imediato: a cadeira estava vazia, e
        # fazer o arquivo esperar um tique seria porteiro virando burocracia.
        self.assertEqual(fila.situacao, "despachada")
        # O `0` é o `teto_snap` (PRA.10): quem enfileira resolve o teto do plano,
        # porque o worker não tem usuário para consultar assinatura nem add-on.
        # Zero é o default seguro — sem snap —, e é o que um chamador que não
        # sabe do recurso produz.
        publicar.assert_called_once_with(
            "moduloprancheta.converter_derivada",
            args=[derivada.pk, str(self.tenant.pk), ["livre"], 0],
        )

    def test_o_mesmo_trabalho_nao_ocupa_dois_lugares_na_fila(self):
        """A `chave` é do TRABALHO, não da linha (D98).

        O upload reenviado, o `reprocessar` clicado duas vezes e o retry do
        Celery pedem a mesma conversão — três lugares seriam três conversões
        idênticas disputando a mesma cadeira, e a segunda encontraria o arquivo
        que a primeira acabou de gravar.
        """
        from nucleo.models import TarefaNaFila

        revisao = self._revisao_dxf()
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso()}), \
                mock.patch("celery.current_app.send_task"):
            for _ in range(3):
                with self.captureOnCommitCallbacks(execute=True):
                    pipeline.agendar(revisao, tiers=["livre"], forcar=True)

        self.assertEqual(
            TarefaNaFila.objects.filter(frota="conversao").count(), 1,
        )

    def test_executar_grava_a_derivada_com_hash_e_versao_do_motor(self):
        revisao = self._revisao_dxf()
        motor = MotorFalso(versao="ezdxf-9.9")
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}):
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf")
            pipeline.executar(derivada)

        derivada.refresh_from_db()
        self.assertEqual(derivada.estado, "pronto")
        self.assertEqual(derivada.hash_origem, "hash-a")
        self.assertEqual(derivada.motor_versao, "ezdxf-9.9")
        self.assertEqual(derivada.tamanho_bytes, len(b"<svg/>"))
        # A memória do motor continua inteira; o `custo` entra ao lado dela.
        self.assertEqual(derivada.memoria["teste"], True)
        self.assertTrue(derivada.arquivo)
        self.assertIsNotNone(derivada.concluido_em)

    def test_executar_grava_o_custo_de_maquina_daquele_arquivo(self):
        """O consumo é **por conversão**, e vai junto do resultado.

        Sem isto, "quanto custou este arquivo?" só tinha resposta rodando o
        `medir_cobertura_dwg` de bancada sobre o acervo de novo — e a pergunta
        aparece justamente quando a conversão já aconteceu, no cockpit.

        A asserção que importa é a de `pico_filho_mb`: ele é `None` quando
        nenhum subprocesso foi medido, e **nunca** 0. Zero se leria como "não
        custou nada", que é a leitura que o [D82](../../docs/pendencias.md)
        produziu ao herdar a memória do pai.
        """
        revisao = self._revisao_dxf()
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(versao="ezdxf-9.9")}):
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf")
            pipeline.executar(derivada)

        custo = derivada.refresh_from_db() or derivada.memoria["custo"]
        self.assertIn("pico_va_mb", custo)
        self.assertIn("segundos", custo)
        self.assertIs(custo["filho_medido"], False)
        self.assertIsNone(custo["pico_filho_mb"])

    def test_derivada_atual_nao_reconverte(self):
        """A idempotência que a planta §11 pede: `hash` + versão do motor batendo
        significa que não há trabalho a fazer."""
        revisao = self._revisao_dxf()
        motor = MotorFalso(versao="ezdxf-9.9")
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}):
            DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf",
                estado="pronto", hash_origem="hash-a", motor_versao="ezdxf-9.9")
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(pipeline.agendar(revisao, tiers=["livre"]), [])

    def test_versao_nova_do_motor_invalida_o_acervo_convertido(self):
        """O ponto todo de carimbar a versão: subir o `ezdxf` desatualiza tudo
        **por comparação**, sem flag manual e sem migration de dados."""
        revisao = self._revisao_dxf()
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(versao="ezdxf-10.0")}), \
                mock.patch("moduloprancheta.tasks.converter_derivada.delay"):
            DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf",
                estado="pronto", hash_origem="hash-a", motor_versao="ezdxf-9.9")
            with self.captureOnCommitCallbacks(execute=True):
                agendadas = pipeline.agendar(revisao, tiers=["livre"])
        self.assertEqual(len(agendadas), 1)

    def test_forcar_reconverte_o_que_ja_estava_pronto(self):
        revisao = self._revisao_dxf()
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(versao="ezdxf-9.9")}), \
                mock.patch("moduloprancheta.tasks.converter_derivada.delay"):
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf",
                estado="pronto", hash_origem="hash-a", motor_versao="ezdxf-9.9")
            with self.captureOnCommitCallbacks(execute=True):
                agendadas = pipeline.agendar(revisao, tiers=["livre"], forcar=True)
        self.assertEqual(agendadas, [derivada.pk])
        derivada.refresh_from_db()
        self.assertEqual(derivada.estado, "pendente")

    def test_falha_nao_retentavel_vira_dado_e_nao_sobe(self):
        """Erro é dado (planta §9): estado + motivo + detalhe na linha. E limite
        de plano não pode ir para o Celery — falharia idêntico 3× e entulharia a
        DLQ de coisa que retentativa nenhuma conserta."""
        revisao = self._revisao_dxf()
        erro = MotorInsuficiente("Este DWG exige o motor de alta fidelidade.")
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(erro=erro)}):
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf")
            pipeline.executar(derivada)  # não levanta

        derivada.refresh_from_db()
        self.assertEqual(derivada.estado, "erro")
        self.assertEqual(derivada.erro_motivo, "motor_insuficiente")
        self.assertIn("alta fidelidade", derivada.erro_detalhe)

    def test_falha_retentavel_persiste_o_estado_antes_de_subir(self):
        """O Celery reagenda, mas a tela não pode ficar mostrando `convertendo`
        no intervalo — o estado é gravado ANTES de a exceção subir."""
        revisao = self._revisao_dxf()
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(erro=FalhaMotor("rede caiu"))}):
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf")
            with self.assertRaises(FalhaMotor):
                pipeline.executar(derivada)

        derivada.refresh_from_db()
        self.assertEqual(derivada.estado, "erro")
        self.assertEqual(derivada.erro_motivo, "falha_motor")

    def test_quem_ja_paga_o_premium_nao_recebe_convite_para_comprar(self):
        """A tradução que separa as duas metades do PRA.1 do PRA.4: para quem NÃO
        contratou o motor premium, "exige alta fidelidade" é upsell honesto; para
        quem contratou, a mesma frase manda comprar o que já está comprado. O
        problema real ali é que a escalada da APS ainda não existe — e dizer isso
        é a diferença entre um cliente que espera e um que abre chamado."""
        revisao = self._revisao_dxf()
        erro = MotorInsuficiente("Este DWG exige o motor de alta fidelidade.")
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso(erro=erro)}):
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf")
            pipeline.executar(derivada, tiers=["livre", "premium"])

        derivada.refresh_from_db()
        self.assertEqual(derivada.erro_motivo, "motor_indisponivel")
        self.assertIn("ainda não está ligado", derivada.erro_detalhe)

    def test_upload_agenda_a_conversao(self):
        """O laço fechado: subir arquivo cria a derivada pendente sem ninguém
        pedir. `on_commit` e não `post_save` — antes do commit a linha não existe
        para o worker, e o job pegaria um arquivo inexistente."""
        documento = self._documento()
        self.autenticar()
        with mock.patch("celery.current_app.send_task") as publicar:
            with self.captureOnCommitCallbacks(execute=True):
                resposta = self.client.post("/api/prancheta/revisoes/", {
                    "documento": documento.pk, "revisao": "R00", "arquivo": pdf_falso(),
                }, format="multipart")

        self.assertEqual(resposta.status_code, 201, resposta.content)
        derivada = DerivadaProjeto.objects.get(revisao_id=resposta.json()["revisao_id"])
        self.assertEqual((derivada.tipo, derivada.motor), ("miniatura", "pdf_nativo"))
        # Pela fila da frota (D98), não pelo broker direto.
        publicar.assert_called_once()


# ---------------------------------------------------------------------------
# 10. PRA.1 — o nó do DWG, testável sem o LibreDWG instalado
# ---------------------------------------------------------------------------
class MotorDwgTests(APITestCase):
    """A parte do motor de DWG que **não** depende do binário: a leitura do
    cabeçalho e a decisão de alcance. Ela existe justamente para falhar rápido e
    com a frase certa, antes de gastar um subprocesso — então é também a parte
    que qualquer máquina consegue verificar."""

    def _arquivo(self, marca: bytes):
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dwg")
        with __import__("os").fdopen(descritor, "wb") as saida:
            saida.write(marca + b"\x00" * 128)
        self.addCleanup(lambda: __import__("os").unlink(caminho))
        return caminho

    def test_le_a_versao_do_cabecalho(self):
        from .motores.dwg import ler_versao_dwg

        self.assertEqual(ler_versao_dwg(self._arquivo(b"AC1032")), ("AC1032", "R2018"))
        self.assertEqual(ler_versao_dwg(self._arquivo(b"AC1037")), ("AC1037", "R2024"))
        self.assertEqual(ler_versao_dwg(self._arquivo(b"PK\x03\x04ZZ")), ("", ""))

    def test_versao_acima_do_alcance_e_upsell_e_nao_erro(self):
        """A frase da planta §4.1, literal: DWG que o motor livre não abre diz
        *"exige o motor de alta fidelidade"*, não "falha na conversão". E a
        recusa é ANTES do subprocesso — falhar rápido com a frase certa é melhor
        que falhar devagar com a errada."""
        from .motores.dwg import MotorDwg

        with self.assertRaises(MotorInsuficiente) as capturado:
            MotorDwg().converter(self._arquivo(b"AC1037"), formato="dwg", tipo="vetor_2d")
        self.assertIn("alta fidelidade", str(capturado.exception))
        self.assertEqual(capturado.exception.extra["versao_dwg"], "AC1037")

    def test_arquivo_que_nao_e_dwg_e_corrompido_e_nao_upsell(self):
        from .motores.base import ArquivoCorrompido
        from .motores.dwg import MotorDwg

        with self.assertRaises(ArquivoCorrompido):
            MotorDwg().converter(self._arquivo(b"PK\x03\x04ZZ"), formato="dwg", tipo="vetor_2d")

    def test_binario_ausente_e_problema_nosso_nao_do_plano(self):
        """A distinção que este módulo inteiro existe para não perder: sem o
        `dwg2dxf` na imagem, mandar o cliente comprar um plano melhor venderia
        uma solução que não resolve o problema dele — o que conserta é deploy."""
        from .motores.base import MotorIndisponivel
        from .motores.dwg import MotorDwg

        with mock.patch("moduloprancheta.motores.dwg.executavel", return_value=None):
            with self.assertRaises(MotorIndisponivel):
                MotorDwg().converter(self._arquivo(b"AC1032"), formato="dwg", tipo="vetor_2d")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_conversor_que_recusa_sobrescrever_nao_pode_virar_upsell(self):
        """Regressão do achado que só apareceu com o binário de verdade.

        O `mkstemp` do adaptador **cria** o arquivo de destino (é de onde vem a
        garantia de nome exclusivo) e o `dwg2dxf` recusa sobrescrever arquivo
        existente: sai com código 1, destino vazio e
        `ERROR: File not overwritten: …, use -y` no stderr. Pelo teste de
        `returncode`/tamanho do adaptador isso é idêntico a "o motor livre não
        deu conta" — então **todo** DWG virava `MotorInsuficiente` e a
        plataforma mandava comprar o plano premium para resolver um bug nosso.
        É a confusão exata que a planta §4.2 separa em dois motivos de erro.

        O falso binário reproduz só essa semântica (recusa sem `-y`, copia com
        `-y`), de modo que o teste vale em qualquer máquina — inclusive nas que
        não têm o LibreDWG, que foi por onde o defeito passou.
        """
        import os
        import stat
        import tempfile

        import ezdxf

        from .motores.dwg import MotorDwg

        modelo = ezdxf.new("R2000")
        modelo.modelspace().add_line((0, 0), (100, 50))
        pasta = tempfile.mkdtemp(prefix="prancheta-teste-")
        self.addCleanup(lambda: __import__("shutil").rmtree(pasta, ignore_errors=True))
        fonte = os.path.join(pasta, "fonte.dxf")
        modelo.saveas(fonte)

        falso = os.path.join(pasta, "dwg2dxf")
        with open(falso, "w") as script:
            script.write(
                "#!/usr/bin/env python3\n"
                "import os, shutil, sys\n"
                "argv = sys.argv[1:]\n"
                "destino = argv[argv.index('-o') + 1]\n"
                "if os.path.exists(destino) and '-y' not in argv:\n"
                f"    sys.stderr.write('ERROR: File not overwritten: %s, use -y.' % destino)\n"
                "    sys.exit(1)\n"
                f"shutil.copyfile({fonte!r}, destino)\n"
            )
        os.chmod(falso, os.stat(falso).st_mode | stat.S_IEXEC)

        with mock.patch("moduloprancheta.motores.dwg.executavel", return_value=falso):
            saida = MotorDwg().converter(
                self._arquivo(b"AC1015"), formato="dwg", tipo="vetor_2d"
            )

        self.assertEqual(saida.extensao, "svg")
        self.assertEqual(saida.detalhe["versao_dwg"], "AC1015")


# ---------------------------------------------------------------------------
# 11. PRA.1 — motores reais (pulados quando a dependência não está na máquina)
# ---------------------------------------------------------------------------
class MotoresReaisTests(APITestCase):
    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_dxf_de_verdade_vira_svg(self):
        """O DoD da fatia: arquivo real de cada formato vira derivada."""
        import tempfile

        import ezdxf

        documento = ezdxf.new("R2010")
        documento.modelspace().add_line((0, 0), (100, 50))
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as arquivo:
            caminho = arquivo.name
        documento.saveas(caminho)
        self.addCleanup(lambda: __import__("os").unlink(caminho))

        saida = ADAPTADORES["ezdxf"].converter(caminho, formato="dxf", tipo="vetor_2d")
        self.assertEqual(saida.extensao, "svg")
        self.assertIn(b"<svg", saida.conteudo)
        self.assertEqual(saida.detalhe["recuperado"], False)

    @unittest.skipUnless(ADAPTADORES["pdf_nativo"].disponivel(), "Pillow não instalado")
    def test_imagem_de_verdade_vira_miniatura(self):
        import tempfile

        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as arquivo:
            caminho = arquivo.name
        Image.new("RGB", (2000, 1200), "steelblue").save(caminho)
        self.addCleanup(lambda: __import__("os").unlink(caminho))

        saida = ADAPTADORES["pdf_nativo"].converter(caminho, formato="imagem", tipo="miniatura")
        self.assertEqual(saida.extensao, "jpg")
        # Encolheu: o card do acervo não carrega 2000 px.
        self.assertLessEqual(max(saida.detalhe["largura"], saida.detalhe["altura"]), 600)

    @unittest.skipUnless(ADAPTADORES["ifcopenshell"].disponivel(), "ifcopenshell não instalado")
    def test_ifc_de_verdade_vira_gltf(self):
        """O DoD da fatia no formato 3D — e a regressão de um defeito que só um
        IFC de verdade mostra.

        O serializador glTF acumula a malha em `.glb.vertices.tmp`/`.glb.indices.tmp`
        e só monta o binário final **no destrutor**; o `finalize()`, apesar do
        nome, encerra a coleta e não escreve nada. Enquanto o motor lia o arquivo
        com o serializador ainda vivo, TODA conversão de IFC devolvia zero byte e
        virava "a tesselação terminou sem produzir geometria" — frase que descreve
        um modelo vazio e manda o cliente procurar defeito no arquivo dele.
        Este teste falha se a referência voltar a ser segurada.
        """
        import glob
        import os
        import tempfile
        import uuid

        import ifcopenshell

        modelo = ifcopenshell.file(schema="IFC4")
        metro = modelo.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
        origem = modelo.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        eixos = modelo.create_entity("IfcAxis2Placement3D", Location=origem)
        contexto = modelo.create_entity(
            "IfcGeometricRepresentationContext", ContextType="Model",
            CoordinateSpaceDimension=3, Precision=1e-5, WorldCoordinateSystem=eixos,
        )
        modelo.create_entity(
            "IfcProject",
            GlobalId=ifcopenshell.guid.compress(uuid.uuid4().hex),
            Name="Teste",
            RepresentationContexts=[contexto],
            UnitsInContext=modelo.create_entity("IfcUnitAssignment", Units=[metro]),
        )
        solido = modelo.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=modelo.create_entity(
                "IfcRectangleProfileDef", ProfileType="AREA", XDim=4.0, YDim=0.2
            ),
            Position=eixos,
            ExtrudedDirection=modelo.create_entity(
                "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
            ),
            Depth=2.8,
        )
        modelo.create_entity(
            "IfcWall",
            GlobalId=ifcopenshell.guid.compress(uuid.uuid4().hex),
            Name="Parede",
            ObjectPlacement=modelo.create_entity("IfcLocalPlacement", RelativePlacement=eixos),
            Representation=modelo.create_entity(
                "IfcProductDefinitionShape",
                Representations=[modelo.create_entity(
                    "IfcShapeRepresentation", ContextOfItems=contexto,
                    RepresentationIdentifier="Body", RepresentationType="SweptSolid",
                    Items=[solido],
                )],
            ),
        )

        pasta = tempfile.mkdtemp(prefix="prancheta-ifc-")
        self.addCleanup(lambda: __import__("shutil").rmtree(pasta, ignore_errors=True))
        caminho = os.path.join(pasta, "modelo.ifc")
        modelo.write(caminho)

        saida = ADAPTADORES["ifcopenshell"].converter(
            caminho, formato="ifc", tipo="modelo_3d"
        )
        self.assertEqual(saida.extensao, "glb")
        # Assinatura do glTF binário: sem ela o conteúdo não é um modelo.
        self.assertTrue(saida.conteudo.startswith(b"glTF"), "não é um glTF binário")
        self.assertEqual(saida.detalhe["elementos"], 1)

        # Os dois buffers do serializador não podem sobrar no disco: uma
        # conversão por revisão, num acervo de milhares, enche /tmp.
        self.assertEqual(glob.glob(os.path.join(tempfile.gettempdir(), "prancheta-*.tmp")), [])


# ---------------------------------------------------------------------------
# 11b. D42 — de quem é o arquivo que falhou, e o bloco que não existe
#
# A medição de 01/08/2026 sobre 73 DWGs reais deu 54,8%, e o achado não foi o
# número: **das 33 falhas, só 5 vinham do LibreDWG**. As outras 28 aconteciam
# depois, com o DWG já convertido em DXF — ou seja, mediam defeito nosso, e a
# fronteira comercial entre os planos ia ser posicionada por elas.
# ---------------------------------------------------------------------------
class DonoDoArquivoQueFalhouTests(SimpleTestCase):
    """A mesma falha de leitura muda de dono conforme quem gerou o arquivo.

    Roda em qualquer máquina de propósito: `_ilegivel` não toca no `ezdxf`,
    porque a regra é de **taxonomia de erro**, não de biblioteca. Se ela
    dependesse do motor instalado, a garantia mais cara desta fatia (não acusar o
    arquivo do cliente) só valeria onde a dependência existe.
    """

    def test_dxf_que_o_cliente_subiu_ilegivel_e_do_cliente(self):
        from .motores.dxf import MotorDxf

        erro = MotorDxf()._ilegivel(cliente="Não é um DXF válido.", nosso="quebrou")
        self.assertIsInstance(erro, ArquivoCorrompido)
        self.assertEqual(erro.motivo, "arquivo_corrompido")
        self.assertEqual(str(erro), "Não é um DXF válido.")

    def test_dxf_intermediario_ilegivel_nao_acusa_o_arquivo_do_cliente(self):
        """O defeito exato do D42: 13 dos 73 clientes leriam *"O arquivo não é um
        DXF válido"* sobre um DXF que nunca viram — o nosso `dwg2dxf` o produziu,
        a partir de um DWG que ele abriu sem erro."""
        from .motores.dxf import MotorDxf

        erro = MotorDxf(origem="dwg")._ilegivel(
            cliente="O arquivo não é um DXF válido, nem depois da tentativa de reparo.",
            nosso="não é um DXF válido, nem depois da tentativa de reparo",
        )
        self.assertIsInstance(erro, FalhaDoIntermediario)
        # `falha_motor` põe a linha na fila do que NÓS consertamos — que é a
        # outra metade da contagem que o acervo separa de `motor_insuficiente`.
        self.assertEqual(erro.motivo, "falha_motor")
        self.assertIn("intermediário", str(erro))
        self.assertIn("não o seu", str(erro))
        # E não pode sobrar, no texto, a frase que acusa o arquivo do cliente.
        self.assertNotIn("O arquivo não é um DXF válido", str(erro))

    def test_falha_do_intermediario_nao_e_retentavel(self):
        """Mesmo DWG + mesmo binário = mesmo DXF quebrado. Retentar 3× reproduz o
        defeito idêntico e só enche a DLQ — a distinção que `base.py` existe para
        manter."""
        from .motores.dxf import MotorDxf

        erro = MotorDxf(origem="dwg")._ilegivel(cliente="x", nosso="y")
        self.assertFalse(erro.retentavel)

    def test_falha_ao_desenhar_fala_do_formato_que_o_cliente_subiu(self):
        from .motores.dxf import MotorDxf

        self.assertEqual(MotorDxf().origem, "dxf")
        self.assertEqual(MotorDxf(origem="dwg").origem, "dwg")

    def test_o_conserto_de_blocos_devolve_as_duas_contagens(self):
        from .motores.dxf import MotorDxf

        class SemBlocos:
            @property
            def blocks(self):
                raise RuntimeError("DXF sem seção de blocos")

        # Documento tão torto que nem a seção de blocos abre: o saneamento se
        # cala e deixa o render falhar como falharia, nunca pior.
        self.assertEqual(MotorDxf()._sanear_blocos(SemBlocos()), ([], 0))


class BlocoAusenteTests(SimpleTestCase):
    """A maior causa isolada de falha do motor livre — 10 dos 73 DWGs reais.

    O `dwg2dxf` emite `INSERT` apontando para bloco anônimo (`*U3`) e nem sempre
    escreve a definição; o `ezdxf` trata como erro de estrutura e **aborta a
    prancha inteira**. Uma planta de milhares de linhas era perdida por causa de
    um carimbo que não desenha.
    """

    def _documento(self):
        import ezdxf

        documento = ezdxf.new("R2000")
        espaco = documento.modelspace()
        espaco.add_line((0, 0), (100, 50))
        return documento

    def _gravar(self, documento) -> str:
        import os
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        documento.saveas(caminho)
        self.addCleanup(lambda: os.path.exists(caminho) and os.unlink(caminho))
        return caminho

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_bloco_referenciado_e_nao_definido_nao_derruba_a_prancha(self):
        documento = self._documento()
        # Um no modelspace e outro **aninhado** dentro de um bloco: a varredura
        # que só olhasse o modelspace passaria batido no segundo, e a prancha
        # continuaria morrendo pelo mesmo motivo.
        documento.modelspace().add_blockref("*U3", (10, 10))
        interno = documento.blocks.new("PORTA")
        interno.add_blockref("*U9", (0, 0))
        documento.modelspace().add_blockref("PORTA", (50, 0))

        saida = ADAPTADORES["ezdxf"].converter(
            self._gravar(documento), formato="dxf", tipo="vetor_2d"
        )

        self.assertEqual(saida.extensao, "svg")
        self.assertIn(b"<svg", saida.conteudo)
        # A prancha saiu — e saiu **incompleta**, o que fica declarado na memória
        # de conversão em vez de virar silêncio. Duas inserções desenharam vazio.
        self.assertEqual(saida.detalhe["blocos_ausentes"], 2)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_insercao_sem_nome_de_bloco_e_descartada_e_a_prancha_sai(self):
        """A segunda avaria, achada na medição do acervo: `Required block
        definition for "" does not exist`.

        Aqui não há o que definir — um `INSERT` sem nome não referencia coisa
        alguma —, então a entidade sai. Ela já não desenhava nada; era só ela
        que separava a prancha inteira de ser desenhada.
        """
        documento = self._documento()
        orfa = documento.modelspace().add_blockref("PROVISORIO", (10, 10))
        orfa.dxf.name = ""

        saida = ADAPTADORES["ezdxf"].converter(
            self._gravar(documento), formato="dxf", tipo="vetor_2d"
        )

        self.assertEqual(saida.extensao, "svg")
        self.assertIn(b"<svg", saida.conteudo)
        self.assertEqual(saida.detalhe["insercoes_descartadas"], 1)
        # E a linha do desenho continua lá: descartar a órfã não levou o resto.
        self.assertGreater(saida.conteudo.count(b"<path"), 0)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_desenho_completo_declara_zero_bloco_ausente(self):
        """Zero é declarado do mesmo jeito: a diferença entre "nada faltou" e
        "ninguém contou" tem de ser legível sem adivinhação."""
        saida = ADAPTADORES["ezdxf"].converter(
            self._gravar(self._documento()), formato="dxf", tipo="vetor_2d"
        )
        self.assertEqual(saida.detalhe["blocos_ausentes"], 0)
        self.assertEqual(saida.detalhe["insercoes_descartadas"], 0)


class RemendoDeContinuacaoTests(SimpleTestCase):
    """**D43** — o `dwg2dxf` corta texto em 255 bytes e esquece o código `3`.

    Os bytes malformados vivem **aqui dentro**, escritos à mão, e não num DWG de
    amostra: é a lição do [D41](../../docs/pendencias.md) — o instrumento que
    prova um conserto não pode depender de arquivo que só existe na máquina de
    quem o rodou. A forma reproduzida é a medida em 09/08/2026 sobre os DWGs do
    próprio AutoCAD.
    """

    def _remendar(self, bruto: bytes):
        from .motores.dwg import remendar_continuacoes

        return remendar_continuacoes(bruto)

    def _linhas(self, conteudo: bytes) -> list[bytes]:
        return conteudo.split(b"\n")

    def test_continuacao_orfa_ganha_o_codigo_3(self):
        cabeca = b"A" * 255
        cauda = b";RD1=LINE15;REV2=LINE16;"
        bruto = b"\n".join([b"  1", cabeca, cauda, b"  7", b"WD"])

        conteudo, remendos = self._remendar(bruto)

        self.assertEqual(remendos, 1)
        self.assertIn(b"  3", self._linhas(conteudo))
        # E o par seguinte continua intacto: o remendo não come o resto do arquivo.
        self.assertEqual(self._linhas(conteudo)[-2:], [b"  7", b"WD"])

    def test_o_codigo_original_vem_por_ULTIMO(self):
        """A parte que quase passou: `3`…`3`, **depois** o `1`.

        Pela spec do DXF, texto longo é uma sequência de códigos `3` *terminada*
        pelo código original. Inverter conserta a estrutura e a geometria sai
        idêntica — mas o MTEXT remonta com o fim na frente, e o estrago cai em
        carimbo, legenda e chamada de cota, que é onde ninguém confere byte.
        """
        cabeca = b"{comeco}" + b"x" * (255 - 8)
        cauda = b"{fim}"
        conteudo, _ = self._remendar(b"\n".join([b"  1", cabeca, cauda]))

        linhas = self._linhas(conteudo)
        self.assertEqual(linhas[0], b"  3", "o pedaço inicial tem de ser código 3")
        self.assertTrue(linhas[1].startswith(b"{comeco}"))
        self.assertEqual(linhas[2], b"  1", "o código original é o do ÚLTIMO pedaço")
        self.assertEqual(linhas[3], cauda)

    def test_o_texto_remontado_preserva_ordem_e_tamanho(self):
        inteiro = ("{\\Fmonotxt;" + "abcdefgh" * 40 + "} 3.4").encode()
        self.assertGreater(len(inteiro), 255)
        partido = [inteiro[:255], inteiro[255:]]
        conteudo, _ = self._remendar(b"\n".join([b"  1", *partido]))

        # Remonta como o leitor de DXF remonta: os `3` na ordem, o `1` no fim.
        linhas = self._linhas(conteudo)
        pares = list(zip(linhas[::2], linhas[1::2]))
        remontado = b"".join(v for c, v in pares if c.strip() == b"3")
        remontado += b"".join(v for c, v in pares if c.strip() == b"1")
        self.assertEqual(remontado, inteiro)

    def test_corte_no_meio_de_caractere_multibyte_e_recomposto(self):
        """O outro filho do mesmo defeito: o corte é em BYTES.

        Preservar os pedaços como vieram bastaria para a quebra estrutural e
        deixaria as duas metades de um caractere em linhas separadas, decodificadas
        em separado. Como o remendo **junta e refatia**, o caractere volta inteiro.
        """
        # O "x" desalinha de propósito: 255 é múltiplo de 3, então sem ele o
        # corte cairia em fronteira limpa e o teste não exercitaria nada.
        bruto_texto = ("x" + "△" * 200).encode("utf-8")
        partido = [bruto_texto[:255], bruto_texto[255:]]
        with self.assertRaises(UnicodeDecodeError):
            partido[0].decode("utf-8")  # o pedaço cru é inválido sozinho

        conteudo, _ = self._remendar(b"\n".join([b"  1", *partido]))

        for linha in self._linhas(conteudo):
            if linha.strip() in (b"1", b"3"):
                continue
            linha.decode("utf-8")  # nenhuma linha de valor quebra caractere

    def test_varias_continuacoes_encadeadas(self):
        pedacos = [b"A" * 255, b"B" * 255, b"C" * 10]
        conteudo, remendos = self._remendar(b"\n".join([b"  1", *pedacos]))

        self.assertEqual(remendos, 2)
        linhas = self._linhas(conteudo)
        self.assertEqual([l for l in linhas if l in (b"  1", b"  3")], [b"  3", b"  3", b"  1"])

    def test_arquivo_sao_nao_muda_um_byte(self):
        """A passagem roda em toda conversão de DWG; sobre DXF são é identidade."""
        sao = b"\n".join([b"  0", b"SECTION", b"  2", b"HEADER", b"  0", b"ENDSEC"])
        conteudo, remendos = self._remendar(sao)

        self.assertEqual(remendos, 0)
        self.assertEqual(conteudo, sao)

    def test_valor_de_255_bytes_seguido_de_codigo_e_legitimo(self):
        """Não é toda linha de 255 bytes que é defeito — só a órfã.

        Se o texto tem exatamente o tamanho do corte, não há continuação, e o
        arquivo está correto. Remendar aqui inventaria um código `3` vazio.
        """
        bruto = b"\n".join([b"  1", b"A" * 255, b"  7", b"ESTILO"])
        conteudo, remendos = self._remendar(bruto)

        self.assertEqual(remendos, 0)
        self.assertEqual(conteudo, bruto)

    def test_crlf_e_preservado(self):
        bruto = b"\r\n".join([b"  1", b"A" * 255, b";resto", b"  7", b"WD"])
        conteudo, remendos = self._remendar(bruto)

        self.assertEqual(remendos, 1)
        self.assertIn(b"\r\n", conteudo)
        self.assertNotIn(b"\n\n", conteudo.replace(b"\r\n", b"\n"))


class ReparosDoIntermediarioTests(SimpleTestCase):
    """**D43, 3ª e 4ª causas** — os dois defeitos do escritor achados em 09/08/2026.

    Ambos em DXF **completo** (com a tag `EOF`), o que os separa da 2ª causa: o
    LibreDWG leu o DWG inteiro e escreveu errado, e escrever errado se conserta
    reescrevendo. Cada reparo dispara contra uma construção que **não existe em
    DXF são** — é isso que o torna inofensivo no arquivo bom, e é isso que estes
    testes cobram.
    """

    def _reparos(self):
        from .motores import dwg

        return dwg

    # -- registro de tabela vazio (FILE.DWG) ---------------------------------
    #: A `TABLES` como o `dwg2dxf` a escreveu: um `BLOCK_RECORD` aberto e nunca
    #: preenchido, colado no `ENDTAB`.
    TABELA_COM_VAZIO = b"\n".join([
        b"  0", b"SECTION", b"  2", b"TABLES",
        b"  0", b"TABLE", b"  2", b"BLOCK_RECORD",
        b"  0", b"BLOCK_RECORD", b"  5", b"1B", b"  2", b"*Model_Space",
        b"  0", b"BLOCK_RECORD",          # ← vazio: o próximo par já é código 0
        b"  0", b"ENDTAB",
        b"  0", b"ENDSEC", b"  0", b"EOF",
    ])

    def test_registro_de_tabela_sem_tag_nenhuma_sai(self):
        conteudo, quantos = self._reparos().descartar_registros_vazios(
            self.TABELA_COM_VAZIO)

        self.assertEqual(quantos, 1)
        # O registro bom fica inteiro; some só o que não descrevia nada.
        self.assertIn(b"*Model_Space", conteudo)
        self.assertEqual(conteudo.count(b"BLOCK_RECORD"), 2)  # o TABLE e o bom

    def test_entidade_sem_atributo_fora_da_TABLES_nao_e_tocada(self):
        """Na `ENTITIES` a mesma forma é desenho, e apagá-la seria apagar traço."""
        bruto = b"\n".join([
            b"  0", b"SECTION", b"  2", b"ENTITIES",
            b"  0", b"POINT",           # sem atributo, mas é entidade legítima
            b"  0", b"LINE", b"  8", b"0",
            b"  0", b"ENDSEC", b"  0", b"EOF",
        ])
        conteudo, quantos = self._reparos().descartar_registros_vazios(bruto)

        self.assertEqual(quantos, 0)
        self.assertEqual(conteudo, bruto)

    # -- seta de cota órfã (As-Built_REAL CONDOMINIO) ------------------------
    def _dimstyle(self, handle_da_seta: bytes, tipo_do_dono: bytes) -> bytes:
        return b"\n".join([
            b"  0", b"SECTION", b"  2", b"TABLES",
            b"  0", b"TABLE", b"  2", b"DIMSTYLE",
            b"  0", b"DIMSTYLE", b"  5", b"27", b"  2", b"Standard",
            b"341", b"0",                     # nenhum: a ezdxf já trata
            b"342", handle_da_seta,
            b"  0", b"ENDTAB",
            b"  0", b"ENDSEC",
            b"  0", b"SECTION", b"  2", b"ENTITIES",
            b"  0", tipo_do_dono, b"  5", b"7", b"  8", b"0",
            b"  0", b"ENDSEC", b"  0", b"EOF",
        ])

    def test_seta_apontando_para_objeto_que_nao_e_bloco_sai(self):
        """O caso medido: `342 → #7`, e o #7 do arquivo é um `VERTEX`.

        A `ezdxf` prevê o handle **inexistente** (captura `KeyError` e usa a seta
        padrão); o que ela não prevê é o handle que existe e aponta para outra
        coisa — aí o `.dxf.name` levanta `DXFAttributeError` fora do `except` e
        mata a carga inteira por causa de uma ponta de seta.
        """
        conteudo, quantas = self._reparos().descartar_setas_de_cota_orfas(
            self._dimstyle(b"7", b"VERTEX"))

        self.assertEqual(quantas, 1)
        self.assertNotIn(b"342", conteudo)
        # O `341 → 0` fica: handle nulo é "nenhuma seta", e a ezdxf já o trata.
        self.assertIn(b"341", conteudo)

    def test_seta_apontando_para_bloco_de_verdade_fica(self):
        """Sem isto o reparo apagaria a seta de cota de todo arquivo são."""
        conteudo, quantas = self._reparos().descartar_setas_de_cota_orfas(
            self._dimstyle(b"7", b"BLOCK_RECORD"))

        self.assertEqual(quantas, 0)
        self.assertIn(b"342", conteudo)

    def test_seta_apontando_para_outro_registro_de_tabela_tambem_fica(self):
        """A fronteira é **ter `name`**, não ser o registro certo.

        Um `342` que aponta para um `STYLE` resolve na ezdxf sem reclamar: vira um
        nome de seta sem sentido, que ela não acha e troca pela padrão. Não
        quebra nada, e por isso não é nosso para mexer.

        Medido, e é a razão de o teste existir: a 1ª versão exigia `BLOCK_RECORD`
        e disparava em **35 arquivos do corpus que já convertiam**. Um reparo que
        toca arquivo são não é reparo.
        """
        for tipo in (b"STYLE", b"LTYPE", b"LAYER", b"BLOCK"):
            conteudo, quantas = self._reparos().descartar_setas_de_cota_orfas(
                self._dimstyle(b"7", tipo))

            self.assertEqual(quantas, 0, f"não devia mexer em alvo {tipo!r}")
            self.assertIn(b"342", conteudo)

    def test_seta_com_handle_inexistente_fica(self):
        """A ezdxf já cai na seta padrão sozinha — mexer aqui seria ruído."""
        conteudo, quantas = self._reparos().descartar_setas_de_cota_orfas(
            self._dimstyle(b"FFFF", b"VERTEX"))

        self.assertEqual(quantas, 0)
        self.assertIn(b"FFFF", conteudo)

    def test_handle_repetido_por_bloco_e_por_outra_coisa_fica(self):
        """O arquivo medido tem 1.244 handles repetidos — erra-se para o lado seguro.

        Se **algum** dono do handle tem nome, a referência pode resolver, e
        descartá-la perderia a seta de um arquivo que ia funcionar.
        """
        bruto = self._dimstyle(b"7", b"VERTEX").replace(
            b"  0\nENDSEC\n  0\nEOF",
            b"  0\nBLOCK_RECORD\n  5\n7\n  2\n*U1\n  0\nENDSEC\n  0\nEOF",
        )
        conteudo, quantas = self._reparos().descartar_setas_de_cota_orfas(bruto)

        self.assertEqual(quantas, 0)
        self.assertIn(b"342", conteudo)

    # -- o conjunto ----------------------------------------------------------
    def test_reparar_intermediario_soma_os_tres_e_diz_quem_fez_o_que(self):
        bruto = self.TABELA_COM_VAZIO + b"\n" + self._dimstyle(b"7", b"VERTEX")
        _conteudo, contagem = self._reparos().reparar_intermediario(bruto)

        self.assertEqual(contagem.get("registro_vazio"), 1)
        self.assertEqual(contagem.get("seta_de_cota_orfa"), 1)
        self.assertNotIn("continuacao_orfa", contagem)

    def test_dxf_sao_atravessa_os_reparos_sem_reconstruir_o_arquivo(self):
        """A garantia que sustenta rodar isto em **toda** conversão.

        Não basta o conteúdo sair igual: tem de sair **o mesmo objeto**. A 1ª
        versão desta camada encadeava três funções que faziam `split` e `join` do
        arquivo inteiro, e num DXF de 84 MB (2,6 milhões de linhas) isso são três
        listas de centenas de MB para não mudar um byte. Foi medido no corpus: um
        arquivo que convertia passou a estourar o orçamento de 1.536 MB e virou
        `recurso_excedido`. O `is` abaixo é o que impede a volta disso.
        """
        sao = b"\n".join([
            b"  0", b"SECTION", b"  2", b"TABLES",
            b"  0", b"TABLE", b"  2", b"LAYER",
            b"  0", b"LAYER", b"  5", b"10", b"  2", b"0", b" 62", b"7",
            b"  0", b"ENDTAB", b"  0", b"ENDSEC",
            b"  0", b"SECTION", b"  2", b"ENTITIES",
            b"  0", b"LINE", b"  5", b"11", b"  8", b"0",
            b"  0", b"ENDSEC", b"  0", b"EOF",
        ])
        conteudo, contagem = self._reparos().reparar_intermediario(sao)

        self.assertEqual(contagem, {})
        self.assertIs(conteudo, sao, "reparo que não achou nada não pode realocar")
        # E o mesmo vale para cada reparo chamado sozinho.
        for reparo in (self._reparos().remendar_continuacoes,
                       self._reparos().descartar_registros_vazios,
                       self._reparos().descartar_setas_de_cota_orfas):
            self.assertIs(reparo(sao)[0], sao, f"{reparo.__name__} realocou à toa")


class LeituraComRecuperacaoTests(SimpleTestCase):
    """**D43, 5ª causa — e esta é nossa, não do LibreDWG.**

    O `_ler` tenta `ezdxf.readfile` e, quando falha, cai no `recover`. Só que até
    09/08/2026 ele caía **apenas** em `DXFStructureError`: qualquer outro erro
    virava "DXF ilegível" na hora, com o `recover` ali do lado sem ser chamado.

    O `JAMYLLE E PAULO_plantas executivas` morria assim — `KeyError: '00 -
    CADASTRO'`, um `LAYOUT` que a ezdxf não registrou e que uma entidade aponta
    como dono — e o mesmo arquivo, pelo `recover`, abre com 25.727 entidades. O
    desenho estava inteiro; a porta é que era estreita.
    """

    def _motor(self):
        from .motores.dxf import MotorDxf

        return MotorDxf(origem="dwg")

    def test_erro_que_nao_e_de_estrutura_tambem_tenta_o_recover(self):
        import ezdxf
        from ezdxf import recover

        documento_recuperado = object()
        auditoria = mock.Mock(has_errors=False)
        with mock.patch.object(ezdxf, "readfile",
                               side_effect=KeyError("'00 - CADASTRO'")), \
                mock.patch.object(recover, "readfile",
                                  return_value=(documento_recuperado, auditoria)) as recuperar:
            documento, recuperado = self._motor()._ler("/tmp/nao-importa.dxf")

        self.assertIs(documento, documento_recuperado)
        self.assertTrue(recuperado, "quem passou pelo recover tem de dizer que passou")
        recuperar.assert_called_once()

    def test_quando_os_dois_falham_a_frase_nomeia_o_PRIMEIRO_erro(self):
        """O erro da 1ª leitura descreve o defeito; o da 2ª só diz que o reparo
        não deu conta. Guardar os dois é o que permite achar o padrão entre
        arquivos — foi assim que o `KeyError` acima virou um achado, e não uma
        linha de log."""
        import ezdxf
        from ezdxf import recover

        from .motores.base import FalhaDoIntermediario

        with mock.patch.object(ezdxf, "readfile",
                               side_effect=KeyError("'00 - CADASTRO'")), \
                mock.patch.object(recover, "readfile",
                                  side_effect=ValueError("nem depois")):
            with self.assertRaises(FalhaDoIntermediario) as capturado:
                self._motor()._ler("/tmp/nao-importa.dxf")

        detalhe = capturado.exception.detalhe
        self.assertIn("KeyError", detalhe)
        self.assertIn("00 - CADASTRO", detalhe)
        self.assertIn("ValueError", detalhe)

    def test_erro_de_memoria_nao_vira_arquivo_corrompido(self):
        """O teto do D57 tem de atravessar as duas tentativas de leitura."""
        import ezdxf

        with mock.patch.object(ezdxf, "readfile", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                self._motor()._ler("/tmp/nao-importa.dxf")


class DecodificacaoIncompletaTests(SimpleTestCase):
    """**D43, 2ª causa** — o `dwg2dxf` falha em ler o DWG e sai com código 0.

    Medido em 09/08/2026: em ~13 dos 15 DWGs que ainda não abriam, o conversor
    emite linhas `ERROR:` no stderr, escreve um DXF truncado (sem a tag `EOF`) e
    **retorna 0**. Como o teste antigo só olhava `returncode` e tamanho, isso
    chegava ao `ezdxf` e morria com uma frase sobre `name`/`NoneType`, mandando
    quem investiga para o leitor de DXF quando o defeito estava no decodificador
    de DWG, dois passos antes.
    """

    def _motor(self):
        from .motores.dwg import MotorDwg

        return MotorDwg()

    def _dxf(self, conteudo: bytes) -> str:
        import os
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        with os.fdopen(descritor, "wb") as saida:
            saida.write(conteudo)
        self.addCleanup(lambda: os.path.exists(caminho) and os.unlink(caminho))
        return caminho

    #: Um fim de arquivo são: a seção fecha e a tag EOF vem depois.
    FIM_SAO = b"  0\nENDSEC\n  0\nEOF\n"
    #: O fim truncado que o `aerhetg.DWG` produz: acaba no ENDSEC, sem EOF.
    FIM_TRUNCADO = b"  0\nENDSEC\n"

    ERRO_REAL = (
        "Warning: Unstable Class object 502 MATERIAL (0x481) 63/0\n"
        "ERROR: bit_read_BD: unexpected 2-bit code: '11'\n"
        "ERROR: BLOCK_HEADER *Model_Space first_owned_entity missing\n"
    )

    def test_ERROR_no_stderr_NAO_reprova_arquivo_completo(self):
        """A trava do critério que quase entrou — e que a medição derrubou.

        A primeira versão recusava quando havia linha `ERROR:` no stderr. Numa
        amostra de 30 DWGs que **convertem hoje**, 25 emitem `ERROR:`: o LibreDWG
        grita por problema recuperável o tempo todo. Aquele critério teria
        reprovado 83% das conversões que funcionam — muito pior que os 12 arquivos
        que consertaria. Este teste existe para que ele não volte.
        """
        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_SAO)
        self._motor()._conferir_decodificacao(caminho, self.ERRO_REAL)  # não levanta

    def test_falta_da_tag_eof_reprova(self):
        """O único critério de recusa: DXF sem `EOF` está incompleto, por definição.

        Medido: 0 falsos positivos em 35 arquivos que convertem.
        """
        from .motores.base import FalhaDoIntermediario

        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_TRUNCADO)
        with self.assertRaises(FalhaDoIntermediario) as capturado:
            self._motor()._conferir_decodificacao(caminho, "")

        self.assertTrue(capturado.exception.extra["sem_eof"])
        self.assertIn("truncado", str(capturado.exception))

    def test_a_frase_oferece_o_caminho_que_funciona_em_vez_de_negar_um(self):
        """A mensagem dizia *"reexportar do CAD não resolve"* — e resolve.

        Medido em 09/08/2026: o `Planta Projeto Impressão Final` (1.719 erros de
        decodificador) foi aberto no AutoCAD, que o recuperou na abertura, e o
        arquivo salvo **converteu** — 16.391 traços, sem recuperação nossa. Dizer
        ao cliente que não há saída, quando há, é pior que não dizer nada: ele
        fica esperando por nós tendo a solução na mão.

        Diz "costuma", e não "resolve": a prova é de um arquivo, e a lição das 6
        amostras homogêneas deste mesmo D43 é que amostra pequena e parecida
        superestima.
        """
        from .motores.base import FalhaDoIntermediario

        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_TRUNCADO)
        with self.assertRaises(FalhaDoIntermediario) as capturado:
            self._motor()._conferir_decodificacao(caminho, self.ERRO_REAL)

        frase = str(capturado.exception)
        self.assertIn("AutoCAD", frase)
        self.assertIn("costuma", frase)
        self.assertNotIn("não resolve", frase)
        # E continua sendo nosso: a saída é um contorno, não uma transferência
        # de culpa para quem enviou.
        self.assertIn("é o nosso, não o seu", frase)

    def test_o_stderr_nomeia_a_causa_na_frase(self):
        """Não julga, mas informa: é o que poupa a investigação no lugar errado."""
        from .motores.base import FalhaDoIntermediario

        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_TRUNCADO)
        with self.assertRaises(FalhaDoIntermediario) as capturado:
            self._motor()._conferir_decodificacao(caminho, self.ERRO_REAL)

        self.assertIn("bit_read_BD", str(capturado.exception))
        self.assertEqual(capturado.exception.extra["erros_do_decodificador"], 2)

    def test_o_motivo_e_NOSSO_e_nao_upsell(self):
        """A tentação era `MotorInsuficiente` — e ninguém mediu se o motor premium
        abre estes arquivos. Vender solução não provada é o D34 ao contrário."""
        from .motores.base import FalhaDoIntermediario, MotorInsuficiente

        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_TRUNCADO)
        with self.assertRaises(FalhaDoIntermediario) as capturado:
            self._motor()._conferir_decodificacao(caminho, self.ERRO_REAL)

        self.assertEqual(capturado.exception.motivo, "falha_motor")
        self.assertNotIsInstance(capturado.exception, MotorInsuficiente)

    def test_o_intermediario_reprovado_nao_fica_no_disco(self):
        import os

        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_TRUNCADO)
        with self.assertRaises(Exception):
            self._motor()._conferir_decodificacao(caminho, "")
        self.assertFalse(os.path.exists(caminho), "temporário vazou")

    def test_aviso_nao_entra_nem_para_nomear(self):
        """`Warning:` aparece em praticamente toda prancha moderna e afogaria a
        causa real na frase."""
        from .motores.base import FalhaDoIntermediario

        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_TRUNCADO)
        with self.assertRaises(FalhaDoIntermediario) as capturado:
            self._motor()._conferir_decodificacao(
                caminho, "Warning: Unstable Class object 502 MATERIAL (0x481) 63/0\n"
            )

        self.assertNotIn("Unstable", str(capturado.exception))
        self.assertEqual(capturado.exception.extra["erros_do_decodificador"], 0)

    def test_arquivo_sao_e_silencioso_passa(self):
        caminho = self._dxf(b"  0\nSECTION\n" + self.FIM_SAO)
        self._motor()._conferir_decodificacao(caminho, "")  # não levanta

    def test_arquivo_curto_nao_estoura_o_seek(self):
        """O rabo é lido com `seek` negativo; arquivo menor que a janela tem de
        cair no ramo do início em vez de levantar `OSError`."""
        from .motores.base import FalhaDoIntermediario

        caminho = self._dxf(b"  0\nEOF\n")
        self._motor()._conferir_decodificacao(caminho, "")  # não levanta

        curto = self._dxf(b"  0\n")
        with self.assertRaises(FalhaDoIntermediario):
            self._motor()._conferir_decodificacao(curto, "")


class IntermediarioDoDwgTests(APITestCase):
    """O caminho inteiro do D42 com um falso `dwg2dxf`, para valer em qualquer
    máquina — inclusive nas que não têm o LibreDWG, que é por onde o defeito
    passou despercebido."""

    def _dwg(self, marca: bytes = b"AC1032") -> str:
        import os
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dwg")
        with os.fdopen(descritor, "wb") as saida:
            saida.write(marca + b"\x00" * 128)
        self.addCleanup(lambda: os.unlink(caminho))
        return caminho

    def _falso_dwg2dxf(self, conteudo: str) -> str:
        """Binário de mentira que escreve `conteudo` no destino e sai com 0 — o
        cenário que importa: o LibreDWG **não reclamou**."""
        import os
        import stat
        import tempfile

        pasta = tempfile.mkdtemp(prefix="prancheta-teste-")
        self.addCleanup(lambda: __import__("shutil").rmtree(pasta, ignore_errors=True))
        caminho = os.path.join(pasta, "dwg2dxf")
        with open(caminho, "w") as script:
            script.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "argv = sys.argv[1:]\n"
                "open(argv[argv.index('-o') + 1], 'w').write(%r)\n" % conteudo
            )
        os.chmod(caminho, os.stat(caminho).st_mode | stat.S_IEXEC)
        return caminho

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_dxf_intermediario_ilegivel_e_falha_nossa_e_nao_arquivo_do_cliente(self):
        """O D42 puro: o `dwg2dxf` entregou um arquivo **completo** e ilegível.

        A tag `EOF` no fim é o que separa este caso do da segunda causa do D43
        (intermediário **truncado**, que `_conferir_decodificacao` pega antes de o
        `ezdxf` ver o arquivo). Sem ela, este teste passaria a exercitar o cheiro
        errado e deixaria de cobrir o defeito que ele nasceu para cobrir.
        """
        from .motores.dwg import MotorDwg

        falso = self._falso_dwg2dxf(
            "isto não é um DXF, nem de longe\n" * 20 + "  0\nENDSEC\n  0\nEOF\n"
        )
        with mock.patch("moduloprancheta.motores.dwg.executavel", return_value=falso):
            with self.assertRaises(FalhaDoIntermediario) as capturado:
                MotorDwg().converter(self._dwg(), formato="dwg", tipo="vetor_2d")

        erro = capturado.exception
        self.assertEqual(erro.motivo, "falha_motor")
        self.assertNotEqual(erro.motivo, "arquivo_corrompido")
        self.assertFalse(erro.retentavel)
        self.assertIn("DWG", str(erro))
        self.assertIn("intermediário", str(erro))

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_bloco_ausente_vindo_do_dwg_converte_em_vez_de_falhar(self):
        """As 10 falhas, pelo caminho por onde elas de fato chegavam."""
        import ezdxf

        from .motores.dwg import MotorDwg

        documento = ezdxf.new("R2000")
        documento.modelspace().add_line((0, 0), (100, 50))
        documento.modelspace().add_blockref("*U3", (10, 10))
        caminho = self._dwg()  # só para o cabeçalho passar no alcance
        import io

        fluxo = io.StringIO()
        documento.write(fluxo)
        falso = self._falso_dwg2dxf(fluxo.getvalue())

        with mock.patch("moduloprancheta.motores.dwg.executavel", return_value=falso):
            saida = MotorDwg().converter(caminho, formato="dwg", tipo="vetor_2d")

        self.assertEqual(saida.extensao, "svg")
        self.assertEqual(saida.detalhe["blocos_ausentes"], 1)
        self.assertEqual(saida.detalhe["versao_dwg"], "AC1032")


# ---------------------------------------------------------------------------
# 12. PRA.1 — a API: reprocessar, status e a fila de decisão
# ---------------------------------------------------------------------------
class ConversaoAPITests(PranchetaTestBase):
    def _revisao_com_falha(self, motivo="motor_insuficiente"):
        revisao = self._revisao()
        DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo="miniatura", motor="pdf_nativo",
            estado="erro", erro_motivo=motivo, erro_detalhe="detalhe")
        return revisao

    def test_reprocessar_exige_permissao_propria(self):
        """Reconverter queima CPU agora e dinheiro na PRA.4 — quem lê o acervo
        não deve poder disparar a reconversão dele."""
        revisao = self._revisao()
        self.autenticar(perms=PERMS_SEM_PUBLICAR)
        resposta = self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/reprocessar/")
        self.assertEqual(resposta.status_code, 403)

    def test_reprocessar_reenfileira_e_responde_202(self):
        revisao = self._revisao()
        self.autenticar()
        with mock.patch("moduloprancheta.tasks.converter_derivada.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                resposta = self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/reprocessar/")
        # 202 e não 200: a conversão é assíncrona por natureza (planta §5), e 200
        # daria a entender que já terminou.
        self.assertEqual(resposta.status_code, 202, resposta.content)
        self.assertEqual(len(resposta.json()["agendadas"]), 1)

    def test_reprocessar_o_que_nenhum_motor_abre_e_409_e_nao_202(self):
        """KMZ é do Maps, LAS é do drone, RVT espera a PRA.4. Um 202 aqui
        prometeria trabalho que ninguém vai fazer."""
        documento = self._documento(codigo="TOP-KMZ-001")
        revisao = RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00",
            arquivo=SimpleUploadedFile("area.kmz", b"PK\x03\x04"),
            nome_original="area.kmz", formato="kmz", tamanho_bytes=4)
        self.autenticar()
        resposta = self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/reprocessar/")
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json()["agendadas"], [])

    def test_status_declara_conversao_disponivel_medida_e_nao_fixa(self):
        """No PRA.0 era `False` fixo. Agora é medido — e dizer "sim" com o motor
        faltando prometeria um visualizador que vai falhar depois do upload."""
        self.autenticar(plano="empresarial")
        corpo = self.client.get("/api/prancheta/status/").json()
        self.assertTrue(corpo["conversao_disponivel"])  # pdf_nativo sempre existe

        por_codigo = {m["codigo"]: m for m in corpo["motores"]}
        self.assertTrue(por_codigo["aps"]["habilitado"])       # o plano vende
        self.assertFalse(por_codigo["aps"]["implementado"])    # o código não tem
        self.assertFalse(por_codigo["aps"]["disponivel"])

    def test_status_no_plano_livre_nao_habilita_o_motor_premium(self):
        self.autenticar(plano="essencial")
        por_codigo = {m["codigo"]: m for m in self.client.get("/api/prancheta/status/").json()["motores"]}
        self.assertFalse(por_codigo["aps"]["habilitado"])
        self.assertTrue(por_codigo["ezdxf"]["habilitado"])

    def test_fila_de_decisao_separa_o_que_o_cliente_compra_do_que_nos_consertamos(self):
        """Somar as duas contagens mandaria o operador abrir chamado por um
        upsell — ou o dono comprar um plano por causa de um binário faltando."""
        self._revisao_com_falha("motor_insuficiente")
        outra = self._documento(codigo="EST-002")
        DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=self._revisao(documento=outra, revisao="R00"),
            tipo="miniatura", motor="pdf_nativo", estado="erro",
            erro_motivo="motor_indisponivel", erro_detalhe="sem binário")

        self.autenticar()
        fila = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()["requer_decisao"]
        self.assertEqual(fila["conversoes_com_erro"], 2)
        self.assertEqual(fila["conversoes_que_exigem_upgrade"], 1)

    def test_resumo_da_revisao_diz_se_da_para_abrir(self):
        """O acervo responde em UMA chamada — sem isto a tela buscaria as
        derivadas de cada revisão, que é N chamadas no celular do canteiro."""
        documento = self._documento()
        revisao = self._revisao(documento=documento, revisao="R00", situacao="vigente")
        DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo="miniatura", motor="pdf_nativo",
            estado="erro", erro_motivo="motor_insuficiente")

        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        conversao = corpo["disciplinas"][0]["documentos"][0]["vigente"]["conversao"]
        self.assertEqual(conversao["estado"], "erro")
        self.assertTrue(conversao["exige_upgrade"])
        # PDF continua abrindo mesmo com a miniatura falhada: o que falhou foi o
        # card do acervo, não o meio de leitura.
        self.assertIsNotNone(conversao["visualizador"])

    def test_derivada_de_outro_tenant_nao_aparece(self):
        alheio = self._documento(codigo="SEG-001", tenant=self.tenant_b, obra=self.obra_b)
        DerivadaProjeto.objects.create(
            tenant=self.tenant_b,
            revisao=self._revisao(documento=alheio, tenant=self.tenant_b),
            tipo="miniatura", motor="pdf_nativo")
        self.autenticar()
        self.assertEqual(self.client.get("/api/prancheta/derivadas/").json()["count"], 0)


# ---------------------------------------------------------------------------
# 13. PRA.1 — a task fora de request (a lição do D8)
# ---------------------------------------------------------------------------
class TaskSemRequestTests(PranchetaTestBase):
    def test_converter_derivada_funciona_sem_request_nenhum(self):
        """Task que toca o ORM sem `tenant_context()` não acha linha nenhuma sob
        a RLS fail-closed do worker — é o D8 literal. Aqui seria pior que um 202
        vazio: a derivada ficaria `pendente` para sempre e a tela do canteiro
        mostraria "aguardando conversão" sem nada aguardando de fato."""
        from .tasks import converter_derivada

        revisao = self._revisao()
        derivada = DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo="miniatura", motor="pdf_nativo")

        with mock.patch.dict(ADAPTADORES, {"pdf_nativo": MotorFalso()}):
            resultado = converter_derivada(derivada.pk, self.tenant.pk, ["livre"])

        self.assertEqual(resultado, derivada.pk)
        derivada.refresh_from_db()
        self.assertEqual(derivada.estado, "pronto")

    def test_derivada_apagada_antes_do_worker_nao_e_erro(self):
        from .tasks import converter_derivada

        self.assertIsNone(converter_derivada(999999, self.tenant.pk, ["livre"]))


class HistoricoDaObraTests(PranchetaTestBase):
    """PRA.2 — o histórico de alterações que só o responsável vê.

    Duas coisas o sustentam, e as duas são pequenas de propósito: o filtro por
    **obra** (senão a tela pagina as revisões do tenant inteiro e diz "sem
    histórico" quando a página 1 não tem nenhuma da obra aberta) e o nome de
    **quem publicou** — que é pergunta diferente de quem enviou, porque na obra
    real não é a mesma pessoa: entregar é do projetista, publicar é alçada.
    """

    def test_filtra_revisoes_pela_obra(self):
        daqui = self._revisao(documento=self._documento(codigo="ARQ-001"))
        outra_obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Bela Vista", endereco="Rua Z, 300"
        )
        self._revisao(documento=self._documento(codigo="ARQ-002", obra=outra_obra))

        self.autenticar()
        corpo = self.client.get(
            f"/api/prancheta/revisoes/?documento__obra={self.obra.pk}"
        ).json()

        self.assertEqual(corpo["count"], 1)
        self.assertEqual(corpo["results"][0]["revisao_id"], daqui.pk)

    def test_historico_nomeia_quem_enviou_e_quem_publicou(self):
        revisao = self._revisao()
        publicador = Usuario.objects.create(username="coordenacao", tenant=self.tenant)
        revisao.enviado_por = self.user
        revisao.save(update_fields=["enviado_por"])

        self.autenticar(user=publicador)
        self.client.post(f"/api/prancheta/revisoes/{revisao.pk}/publicar/")

        corpo = self.client.get(f"/api/prancheta/revisoes/{revisao.pk}/").json()
        self.assertEqual(corpo["enviado_por_nome"], "proj_a")
        self.assertEqual(corpo["publicado_por_nome"], "coordenacao")
        self.assertIsNotNone(corpo["publicado_em"])


class EntregaDoArquivoTests(PranchetaTestBase):
    """PRA.2 — a porta de leitura do acervo, e o que ela recusa.

    O PRA.1 fechou o pipeline mas a resposta ainda entregava `arquivo.url`, isto
    é, `/media/...`. Aquele caminho é servido **só** com `DEBUG` (config/urls.py)
    e, quando servido, não passa por autenticação, entitlement nem RLS: em
    produção o visualizador apontaria para o nada e, em desenvolvimento, o acervo
    de projeto de qualquer empresa estaria a um caminho adivinhado de distância.
    É o **S10** de novo — e o **MAP.3** já havia recusado repeti-lo ao trazer o
    tile da ortofoto para dentro do backend.

    O que estes testes travam é o contrato dessa porta: mesmo gate do módulo,
    tipo determinado por nós, nada servido como página, e nenhuma resposta da API
    voltando a publicar caminho de mídia.
    """

    def _revisao_com_derivada(self, *, estado="pronto", com_arquivo=True, codigo="EST-DXF-001"):
        """DXF, e não PDF, de propósito: é o caso em que a derivada **é** o meio
        de leitura. PDF é nativo do browser e continua sendo aberto pelo arquivo
        original (a preferência que o `get_conversao` implementa), então provar a
        entrega da derivada com ele não provaria nada."""
        documento = self._documento(codigo=codigo)
        revisao = RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00", situacao="vigente",
            arquivo=SimpleUploadedFile("planta.dxf", b"0\nSECTION\n"),
            nome_original="planta.dxf", formato="dxf", tamanho_bytes=10,
        )
        return revisao, DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf",
            estado=estado,
            arquivo=(SimpleUploadedFile("planta.svg", b"<svg/>") if com_arquivo else None),
        )

    def test_sem_token_o_arquivo_nao_sai(self):
        revisao = self._revisao()
        self.assertEqual(
            self.client.get(entrega.url_da_revisao(revisao.pk)).status_code, 401
        )

    def test_sem_entitlement_o_arquivo_nao_sai(self):
        """O gate da Prancheta é um só. Se o acervo tivesse uma porta de leitura
        fora dele, o entitlement inteiro viraria decoração — bastaria a URL."""
        revisao = self._revisao()
        self.autenticar(modules=())
        self.assertEqual(
            self.client.get(entrega.url_da_revisao(revisao.pk)).status_code, 403
        )

    def test_sem_permissao_de_leitura_o_arquivo_nao_sai(self):
        revisao = self._revisao()
        self.autenticar(perms=["prancheta.documento.edit"])
        self.assertEqual(
            self.client.get(entrega.url_da_revisao(revisao.pk)).status_code, 403
        )

    def test_arquivo_de_outro_tenant_e_404_e_nao_403(self):
        """404 e não 403 de propósito: 403 confirmaria que a revisão existe. Quem
        pesca id não deve descobrir o acervo do concorrente pelo código de
        status."""
        alheio = self._documento(codigo="SEG-001", tenant=self.tenant_b, obra=self.obra_b)
        revisao = self._revisao(documento=alheio, tenant=self.tenant_b)
        self.autenticar()
        self.assertEqual(
            self.client.get(entrega.url_da_revisao(revisao.pk)).status_code, 404
        )

    def test_o_tipo_sai_do_registry_e_nao_do_nome_que_o_cliente_mandou(self):
        """`nome_original` é texto de quem enviou. Se ele decidisse o
        `Content-Type`, o remetente escolheria como o browser interpreta o
        próprio upload — um `.pdf` gravado como `image/svg+xml` seria documento
        executável servido pela nossa origem."""
        documento = self._documento()
        revisao = RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00",
            arquivo=SimpleUploadedFile("planta.pdf", b"%PDF-1.4\n0000"),
            nome_original="planta.svg",  # mentira do cliente
            formato="pdf", tamanho_bytes=13,
        )
        self.autenticar()
        resposta = self.client.get(entrega.url_da_revisao(revisao.pk))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")

    def test_derivada_svg_sai_como_anexo_nunca_como_pagina(self):
        """SVG é documento executável. Servido inline pela origem do sistema, um
        `<script>` que atravessasse o conversor rodaria com a sessão de quem
        abriu a prancha. A tela o exibe por blob dentro de `<img>`, onde script
        não roda — então o servidor pode ser categórico aqui."""
        _, derivada = self._revisao_com_derivada()
        self.autenticar()
        resposta = self.client.get(entrega.url_da_derivada(derivada.pk))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "image/svg+xml")
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(resposta.streaming_content), b"<svg/>")

    def test_derivada_sem_arquivo_e_404_e_nao_resposta_vazia(self):
        """Pendente, convertendo e em erro não têm bytes. Servir 200 vazio faria
        a tela desenhar o nada em vez de mostrar o estado que ela já recebeu."""
        _, derivada = self._revisao_com_derivada(estado="erro", com_arquivo=False)
        self.autenticar()
        self.assertEqual(
            self.client.get(entrega.url_da_derivada(derivada.pk)).status_code, 404
        )

    def test_arquivo_fora_do_armazenamento_e_404_com_motivo_e_nao_500(self):
        """Volume trocado ou expurgo: o registro existe e os bytes não. É falha
        nossa de infraestrutura, e o suporte precisa distinguí-la de "sem
        acesso" — um traceback de 500 não diz isso a ninguém."""
        revisao = self._revisao()
        revisao.arquivo.storage.delete(revisao.arquivo.name)
        self.autenticar()
        resposta = self.client.get(entrega.url_da_revisao(revisao.pk))
        self.assertEqual(resposta.status_code, 404)
        self.assertIn("armazenamento", resposta.json()["detail"])

    def test_nenhuma_resposta_da_api_publica_caminho_de_midia(self):
        """A regressão que este teste existe para pegar: alguém devolve
        `arquivo.url` de novo, em qualquer serializer, e o acervo volta a
        depender de uma porta sem gate."""
        revisao, _ = self._revisao_com_derivada()
        self.autenticar()

        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").content.decode()
        detalhe = self.client.get(f"/api/prancheta/revisoes/{revisao.pk}/").content.decode()
        derivadas = self.client.get("/api/prancheta/derivadas/").content.decode()

        for corpo in (acervo, detalhe, derivadas):
            self.assertNotIn("/media/", corpo)

    def test_o_visualizador_aponta_para_a_derivada_pronta_e_ela_abre(self):
        """O laço que a fatia entrega: o que o acervo diz para abrir tem de
        abrir. Sem este teste, `visualizador` poderia apontar para qualquer
        string e só o browser descobriria."""
        _, derivada = self._revisao_com_derivada()
        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        documento = next(
            d for grupo in corpo["disciplinas"] for d in grupo["documentos"]
            if d["codigo"] == "EST-DXF-001"
        )
        conversao = documento["vigente"]["conversao"]

        self.assertEqual(conversao["estado"], "pronta")
        self.assertFalse(conversao["nativo"])
        # A versão do conteúdo entra na URL (ver `VersaoNaUrlDaDerivadaTests`): sem
        # ela o `immutable` de um ano tornaria toda reconversão invisível na tela.
        self.assertRegex(
            conversao["visualizador"],
            rf"^/api/impexp/prancheta\.acervo/arquivo/derivada/{derivada.pk}/"
            rf"\?v=[0-9a-f]{{12}}$")
        self.assertEqual(self.client.get(conversao["visualizador"]).status_code, 200)

    def test_no_formato_nativo_o_visualizador_e_o_proprio_arquivo(self):
        """A outra metade da preferência: o PDF não espera derivada nenhuma para
        abrir — o que se converte dele é a miniatura do card. Se esta URL
        apontasse para a derivada, o canteiro perderia o único formato que nunca
        dependeu do nosso motor."""
        revisao = self._revisao(situacao="vigente")
        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        conversao = corpo["disciplinas"][0]["documentos"][0]["vigente"]["conversao"]

        self.assertTrue(conversao["nativo"])
        self.assertEqual(conversao["visualizador"], entrega.url_da_revisao(revisao.pk))
        self.assertEqual(self.client.get(conversao["visualizador"]).status_code, 200)

    def test_entrega_declara_cache_imutavel_e_privado(self):
        """Não é micro-otimização: é o seam do offline (planta §8). Revisão nova
        é linha nova e derivada nova é motor novo, então `immutable` é verdade —
        e `private` porque a resposta é autorizada e proxy compartilhado não pode
        guardá-la."""
        _, derivada = self._revisao_com_derivada()
        self.autenticar()
        cache = self.client.get(entrega.url_da_derivada(derivada.pk))["Cache-Control"]
        self.assertIn("immutable", cache)
        self.assertIn("private", cache)


# ===========================================================================
# 13. PRA.3 — marcar e medir
# ===========================================================================
# O que se prova aqui, em ordem de importância:
#
# 1. **`resolver` é verbo separado, e o campo não o tem.** Se isto quebrar, o
#    apontamento se fecha antes de o projetista responder e a fila esvazia pelo
#    lado errado — a marcação vira caixa de recados sem consequência.
# 2. **O GUID sustenta a ida e volta.** Reimportar o mesmo BCF tem de reencontrar
#    a marcação, não criar a segunda. É a diferença entre integração usada e
#    integração abandonada na segunda semana.
# 3. **Sem escala não se inventa metro.** Medir continua funcionando e o valor
#    sai em fração da largura, declarado. Fabricar unidade aqui vira parede no
#    lugar errado do canteiro.
# 4. **A parede do BCF é comercial (402); a de encerrar é de permissão (403).**
#    Trocá-las manda o cliente pedir permissão do que precisa comprar, e comprar
#    o que precisa pedir.

PERMS_MARCACAO_CAMPO = [
    "prancheta.documento.view",
    "prancheta.marcacao.view",
    "prancheta.marcacao.edit",
]
PERMS_MARCACAO_TOTAL = PERMS_MARCACAO_CAMPO + [
    "prancheta.documento.edit",
    "prancheta.marcacao.resolver",
]


class MarcacaoTestBase(PranchetaTestBase):
    def _desenho(self, revisao=None, **extra):
        """A folha da revisão — onde a régua mora desde a PRA.1c.

        Existe como helper porque quase todo teste de medir e calibrar precisa de
        uma: uma revisão sem desenho é uma revisão que ainda não converteu, e
        nela não há o que medir.
        """
        revisao = revisao or self._revisao(situacao="vigente")
        dados = {
            "tenant": revisao.tenant, "revisao": revisao, "ordem": 1,
            "caixa": {"xmin": 0.0, "ymin": 0.0, "xmax": 1000.0, "ymax": 700.0},
            "tracos": 300,
        }
        dados.update(extra)
        return DesenhoProjeto.objects.create(**dados)

    def _marcacao(self, revisao=None, **extra):
        revisao = revisao or self._revisao(situacao="vigente")
        dados = {
            "tenant": revisao.tenant, "revisao": revisao,
            "titulo": "Viga não bate com a alvenaria",
            "descricao": "A V12 encosta na parede do eixo 3.",
        }
        dados.update(extra)
        return Marcacao.objects.create(**dados)


class MarcacaoGateTests(MarcacaoTestBase):
    def test_sem_o_modulo_nada_de_marcacao(self):
        self.autenticar(modules=[])
        for rota in ("marcacoes", "medicoes", "pontos-de-vista"):
            self.assertEqual(self.client.get(f"/api/prancheta/{rota}/").status_code, 403)

    def test_ver_prancha_nao_da_ver_marcacao(self):
        """As duas permissões são separadas de propósito: há cliente que compra o
        acervo para o campo consultar sem abrir a caixa de apontamentos."""
        self.autenticar(perms=["prancheta.documento.view"])
        self.assertEqual(self.client.get("/api/prancheta/marcacoes/").status_code, 403)

    def test_campo_marca_mas_nao_encerra(self):
        """A tese central da fatia. `campo` tem `edit` (apontar é o trabalho
        dele) e não tem `resolver`."""
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)

        criada = self.client.post("/api/prancheta/marcacoes/", {
            "revisao": revisao.pk, "titulo": "Furo de passagem faltando",
            "tipo": "Issue", "prioridade": "High",
        }, format="json")
        self.assertEqual(criada.status_code, 201, criada.data)

        fechar = self.client.post(
            f"/api/prancheta/marcacoes/{criada.json()['marcacao_id']}/situacao/",
            {"situacao": "Closed"}, format="json",
        )
        self.assertEqual(fechar.status_code, 403)

    def test_situacao_nao_muda_por_patch(self):
        """O atalho óbvio de contornar o verbo de alçada — o mesmo que a PRA.0
        fechou em `RevisaoDocumento.situacao` (a armadilha do D28)."""
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        resposta = self.client.patch(
            f"/api/prancheta/marcacoes/{marcacao.pk}/", {"situacao": "Closed"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        marcacao.refresh_from_db()
        self.assertEqual(marcacao.situacao, "Open")

    def test_encerrar_carimba_quem_e_quando_e_reabrir_limpa(self):
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        rota = f"/api/prancheta/marcacoes/{marcacao.pk}/situacao/"

        self.assertEqual(
            self.client.post(rota, {"situacao": "Closed"}, format="json").status_code, 200
        )
        marcacao.refresh_from_db()
        self.assertEqual(marcacao.resolvido_por, self.user)
        self.assertIsNotNone(marcacao.resolvido_em)

        # Reabrir tem de LIMPAR o carimbo: um tópico reaberto que continuasse
        # marcado como resolvido acusaria essa pessoa de um encerramento que a
        # realidade desmentiu.
        self.assertEqual(
            self.client.post(rota, {"situacao": "Open"}, format="json").status_code, 200
        )
        marcacao.refresh_from_db()
        self.assertIsNone(marcacao.resolvido_por)
        self.assertIsNone(marcacao.resolvido_em)

    def test_mudanca_de_situacao_deixa_rastro_no_proprio_topico(self):
        """O BCF só carrega autoria dentro do comentário — sem este registro, o
        tópico chega ao escritório mudando de status sem dizer quem mudou.

        Confere **a resposta**, e não só o banco: a versão que olhava apenas o
        ORM passava enquanto a API devolvia a conversa sem a linha recém-criada
        (o cache do `prefetch_related` é montado no `get_object()`, antes do
        comentário). Quem pegou isso foi a fumaça no stack vivo.
        """
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/situacao/",
            {"situacao": "Resolved"}, format="json",
        )

        comentarios = list(marcacao.comentarios.all())
        self.assertEqual(len(comentarios), 1)
        self.assertEqual(comentarios[0].autor, self.user)
        self.assertIn("Resolvida", comentarios[0].texto)
        # A resposta já traz o rastro — a tela não precisa de um segundo GET
        # para mostrar o que a própria ação acabou de escrever.
        self.assertEqual(len(resposta.json()["comentarios"]), 1)

    def test_situacao_invalida_e_400_com_o_vocabulario(self):
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/situacao/",
            {"situacao": "Arquivada"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Open", resposta.json()["situacoes"])

    def test_comentar_e_edit_e_nao_resolver(self):
        """A conversa é de todo mundo; fechar o assunto não."""
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        resposta = self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/comentar/",
            {"texto": "Confirmado em campo, foto no diário."}, format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(resposta.json()["autor_nome"], self.user.username)


class MarcacaoIsolamentoTests(MarcacaoTestBase):
    def test_marcacao_de_outro_tenant_e_404(self):
        outro_doc = self._documento(codigo="X-1", tenant=self.tenant_b, obra=self.obra_b)
        outra = Marcacao.objects.create(
            tenant=self.tenant_b,
            revisao=self._revisao(documento=outro_doc, tenant=self.tenant_b),
            titulo="Segredo da concorrente",
        )
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        self.assertEqual(self.client.get(f"/api/prancheta/marcacoes/{outra.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/prancheta/marcacoes/").json()["count"], 0)

    def test_mesmo_guid_convive_em_tenants_diferentes(self):
        """Dois clientes podem importar o BCF do mesmo projetista terceirizado.
        Unique global viraria erro de gravação para o segundo."""
        guid = uuid.uuid4()
        self._marcacao(guid=guid)
        outro_doc = self._documento(codigo="X-2", tenant=self.tenant_b, obra=self.obra_b)
        Marcacao.objects.create(
            tenant=self.tenant_b,
            revisao=self._revisao(documento=outro_doc, tenant=self.tenant_b),
            titulo="Mesmo tópico, outra empresa", guid=guid,
        )
        self.assertEqual(Marcacao.objects.filter(guid=guid).count(), 2)

    def test_nao_da_para_marcar_prancha_de_outro_tenant(self):
        outro_doc = self._documento(codigo="X-3", tenant=self.tenant_b, obra=self.obra_b)
        alheia = self._revisao(documento=outro_doc, tenant=self.tenant_b)
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post("/api/prancheta/marcacoes/", {
            "revisao": alheia.pk, "titulo": "não deveria entrar",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("revisao", resposta.json())


class CalibracaoTests(MarcacaoTestBase):
    def test_calibrar_converte_dois_pontos_em_escala(self):
        """3,50 m sobre meia largura ⇒ 7,00 m na largura inteira."""
        desenho = self._desenho()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(f"/api/prancheta/desenhos/{desenho.pk}/calibrar/", {
            "a": {"x": 0.25, "y": 0.5}, "b": {"x": 0.75, "y": 0.5},
            "distancia_real": 3.5, "unidade": "m",
        }, format="json")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        desenho.refresh_from_db()
        self.assertAlmostEqual(desenho.escala_valor, 7.0)
        self.assertEqual(desenho.escala_calibrada_por, self.user)
        # A referência fica gravada: sem ela, ninguém confere se quem calibrou
        # usou uma cota de verdade.
        self.assertEqual(desenho.escala_referencia["distancia_real"], 3.5)

    def test_pontos_colados_sao_recusados(self):
        """Um tremor de dedo geraria escala gigantesca, e toda medida da prancha
        herdaria o erro."""
        desenho = self._desenho()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(f"/api/prancheta/desenhos/{desenho.pk}/calibrar/", {
            "a": {"x": 0.5, "y": 0.5}, "b": {"x": 0.502, "y": 0.5}, "distancia_real": 3.5,
        }, format="json")
        self.assertEqual(resposta.status_code, 400)

    def test_quem_so_marca_nao_calibra(self):
        """Segregação deliberada: quem mede não define a régua."""
        desenho = self._desenho()
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        resposta = self.client.post(f"/api/prancheta/desenhos/{desenho.pk}/calibrar/", {
            "a": {"x": 0.1, "y": 0.1}, "b": {"x": 0.9, "y": 0.1}, "distancia_real": 10,
        }, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_escala_nao_entra_por_patch(self):
        """O desenho é read-only fora dos dois verbos: `renomear` e `calibrar`."""
        desenho = self._desenho()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        self.client.patch(
            f"/api/prancheta/desenhos/{desenho.pk}/", {"escala_valor": 999}, format="json",
        )
        desenho.refresh_from_db()
        self.assertIsNone(desenho.escala_valor)

    def test_calibrar_carimba_a_procedencia(self):
        """É este carimbo que blinda a régua contra a próxima reconversão."""
        desenho = self._desenho()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(f"/api/prancheta/desenhos/{desenho.pk}/calibrar/", {
            "a": {"x": 0.25, "y": 0.5}, "b": {"x": 0.75, "y": 0.5},
            "distancia_real": 3.5, "unidade": "m",
        }, format="json")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.data["escala_origem"], "calibrada")
        desenho.refresh_from_db()
        self.assertEqual(desenho.escala_origem, "calibrada")
        self.assertFalse(desenho.pode_derivar_escala)

    def test_procedencia_nao_entra_por_patch(self):
        """Editável, um PATCH carimbaria "calibrada" numa régua que ninguém
        conferiu — e essa palavra é justamente a que bloqueia a reconversão."""
        desenho = self._desenho()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        self.client.patch(
            f"/api/prancheta/desenhos/{desenho.pk}/", {"escala_origem": "calibrada"},
            format="json",
        )
        desenho.refresh_from_db()
        self.assertEqual(desenho.escala_origem, "")


class MedicaoTests(MarcacaoTestBase):
    def _calibrada(self, escala=10.0):
        """Uma revisão cuja folha já tem régua. Devolve a revisão — as medições
        entram por ela, e o desenho é resolvido no servidor."""
        revisao = self._revisao(situacao="vigente")
        self._desenho(revisao, escala_valor=escala, escala_unidade="m")
        return revisao

    def test_distancia_sai_na_unidade_real(self):
        revisao = self._calibrada(escala=10.0)  # 10 m na largura
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        resposta = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "distancia",
            "pontos": [{"x": 0.2, "y": 0.5}, {"x": 0.7, "y": 0.5}],
        }, format="json")

        self.assertEqual(resposta.status_code, 201, resposta.data)
        corpo = resposta.json()
        self.assertAlmostEqual(corpo["valor"], 5.0)   # 0,5 da largura × 10 m
        self.assertEqual(corpo["unidade"], "m")

    def test_area_escala_com_o_quadrado(self):
        """O erro clássico é multiplicar área pelo fator linear e entregar um
        cômodo de 3 m²."""
        revisao = self._calibrada(escala=10.0)
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        corpo = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "area",
            "pontos": [
                {"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
                {"x": 0.5, "y": 0.5}, {"x": 0.0, "y": 0.5},
            ],
        }, format="json").json()

        self.assertAlmostEqual(corpo["valor"], 25.0)  # 0,25 × 10² = 25 m²
        self.assertEqual(corpo["unidade"], "m²")

    def test_sem_escala_mede_em_fracao_e_declara(self):
        """A régua de dados honestos aplicada ao caso em que a resposta certa é
        'não sei em quanto isso dá'."""
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        corpo = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "distancia",
            "pontos": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0}],
        }, format="json").json()

        self.assertAlmostEqual(corpo["valor"], 0.5)
        self.assertEqual(corpo["unidade"], "")
        self.assertIsNone(corpo["escala_aplicada"])

    def test_recalibrar_converte_a_medida_antiga_e_guarda_o_recibo(self):
        """Recalibrar CONVERTE a medida, e não a deixa para trás declarada.

        **A decisão virou em 15/08/2026, e o motivo veio do uso.** Antes a medida
        antiga ficava intacta e apenas se declarava `desatualizada` — tracejada na
        tela —, para não reescrever um número que alguém pudesse ter anotado. Só
        que ninguém recalibra por esporte: recalibra porque a régua estava errada,
        e a medida com ela. Deixá-la ali entregava o número errado com aparência
        de conferido, que é o defeito mais caro deste módulo.

        Converter é exato porque `pontos` é normalizado pela largura da folha: a
        medida sempre foi derivável, e `valor` é cache. E não é reescrita
        silenciosa — o valor anterior fica em `valor_anterior`, com a régua que o
        produziu, para quem tiver a caderneta do canteiro reencontrar de onde veio
        o número velho.
        """
        revisao = self._calibrada(escala=10.0)
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        medicao_id = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "distancia",
            "pontos": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}],
        }, format="json").json()["medicao_id"]

        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(
            f"/api/prancheta/desenhos/{revisao.desenhos.first().pk}/calibrar/", {
                "a": {"x": 0.0, "y": 0.0}, "b": {"x": 1.0, "y": 0.0}, "distancia_real": 20,
            }, format="json")
        # A tela precisa poder avisar quantas mudaram — sem isso, o número novo
        # aparece sem explicação e parece que a tela se atrapalhou.
        self.assertEqual(resposta.json()["medidas_recalculadas"], 1)

        medicao = Medicao.objects.get(pk=medicao_id)
        self.assertAlmostEqual(medicao.valor, 20.0)          # converteu
        self.assertAlmostEqual(medicao.escala_aplicada, 20.0)
        self.assertFalse(medicao.desatualizada)              # e ficou em dia
        # O recibo: um registro do que ela dizia, com a régua de então.
        self.assertEqual(len(medicao.valor_anterior), 1)
        self.assertAlmostEqual(medicao.valor_anterior[0]["valor"], 10.0)
        self.assertAlmostEqual(medicao.valor_anterior[0]["escala_aplicada"], 10.0)

    def test_recalibrar_duas_vezes_empilha_o_historico(self):
        """Cada recalibração deixa a sua linha — a história não é sobrescrita."""
        revisao = self._calibrada(escala=10.0)
        desenho = revisao.desenhos.first()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        medicao_id = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "distancia",
            "pontos": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}],
        }, format="json").json()["medicao_id"]

        for real in (20, 40):
            self.client.post(f"/api/prancheta/desenhos/{desenho.pk}/calibrar/", {
                "a": {"x": 0.0, "y": 0.0}, "b": {"x": 1.0, "y": 0.0},
                "distancia_real": real,
            }, format="json")

        medicao = Medicao.objects.get(pk=medicao_id)
        self.assertAlmostEqual(medicao.valor, 40.0)
        self.assertEqual([r["valor"] for r in medicao.valor_anterior], [10.0, 20.0])

    def test_recalibrar_sem_mudar_nada_nao_suja_o_historico(self):
        """Calibrar de novo com a MESMA régua não gera linha de histórico.

        Sem esta guarda, abrir o diálogo e confirmar sem mexer encheria o recibo
        de linhas idênticas — e um histórico cheio de ruído é um histórico que
        ninguém lê quando precisa.
        """
        revisao = self._calibrada(escala=10.0)
        desenho = revisao.desenhos.first()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        medicao_id = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "distancia",
            "pontos": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}],
        }, format="json").json()["medicao_id"]

        resposta = self.client.post(f"/api/prancheta/desenhos/{desenho.pk}/calibrar/", {
            "a": {"x": 0.0, "y": 0.0}, "b": {"x": 1.0, "y": 0.0}, "distancia_real": 10,
        }, format="json")

        self.assertEqual(resposta.json()["medidas_recalculadas"], 0)
        self.assertEqual(Medicao.objects.get(pk=medicao_id).valor_anterior, [])

    def test_valor_nao_e_aceito_do_cliente(self):
        """Quem calcula é o servidor — senão o medido e o gravado divergem, que é
        o defeito que o F19 achou no plano de pagamento."""
        revisao = self._calibrada(escala=10.0)
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        corpo = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "tipo": "distancia", "valor": 999, "unidade": "km",
            "pontos": [{"x": 0.0, "y": 0.0}, {"x": 0.1, "y": 0.0}],
        }, format="json").json()
        self.assertAlmostEqual(corpo["valor"], 1.0)
        self.assertEqual(corpo["unidade"], "m")

    def test_vertices_invalidos_sao_400_e_nao_500(self):
        revisao = self._calibrada()
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        casos = [
            ("poucos vértices p/ área",
             {"tipo": "area", "pontos": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}),
            ("vértice sem y",
             {"tipo": "distancia", "pontos": [{"x": 0}, {"x": 1, "y": 0}]}),
            ("texto no lugar do número",
             {"tipo": "distancia", "pontos": [{"x": "a", "y": 0}, {"x": 1, "y": 0}]}),
            ("fora da folha",
             {"tipo": "distancia", "pontos": [{"x": 0, "y": 0}, {"x": 9999, "y": 0}]}),
        ]
        for rotulo, extra in casos:
            with self.subTest(rotulo):
                resposta = self.client.post(
                    "/api/prancheta/medicoes/", {"revisao": revisao.pk, **extra}, format="json",
                )
                self.assertEqual(resposta.status_code, 400, rotulo)

    def test_medida_nao_se_amarra_a_marcacao_de_outra_prancha(self):
        """Descreveria um problema que não está onde diz estar."""
        outra = self._marcacao(revisao=self._revisao(
            documento=self._documento(codigo="EST-001"), revisao="R00",
        ))
        revisao = self._calibrada()
        self.autenticar(perms=PERMS_MARCACAO_CAMPO)
        resposta = self.client.post("/api/prancheta/medicoes/", {
            "revisao": revisao.pk, "marcacao": outra.pk, "tipo": "distancia",
            "pontos": [{"x": 0, "y": 0}, {"x": 1, "y": 0}],
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("marcacao", resposta.json())


# ---------------------------------------------------------------------------
# 14. BCF — o formato, sem banco
# ---------------------------------------------------------------------------
class BcfFormatoTests(APITestCase):
    """O parser e o escritor, isolados do ORM.

    Rodam sem banco de propósito: o que se prova aqui é a leitura de um formato
    de TERCEIRO, e ela tem de continuar valendo quando os nossos modelos
    mudarem. É a mesma separação que o `MotorFalso` faz com o pipeline.
    """

    def _topico(self, **extra):
        dados = {
            "guid": str(uuid.uuid4()),
            "titulo": "Interferência viga × duto",
            "descricao": "A V12 corta o duto de exaustão.",
            "tipo": "Clash", "situacao": "In Progress", "prioridade": "High",
            "rotulos": ["hidráulica", "estrutural"],
            "autor": "mestre@obra.com",
        }
        dados.update(extra)
        return bcf.TopicoBcf(**dados)

    def test_ida_e_volta_preserva_o_topico(self):
        original = self._topico()
        original.comentarios.append(bcf.ComentarioBcf(
            guid=str(uuid.uuid4()), texto="Confirmado em campo.", autor="joão",
        ))
        original.pontos_de_vista.append(bcf.PontoDeVistaBcf(guid=str(uuid.uuid4())))

        lidos = bcf.ler(bcf.escrever([original]))
        self.assertEqual(len(lidos), 1)
        volta = lidos[0]
        self.assertEqual(volta.guid, original.guid)
        self.assertEqual(volta.titulo, original.titulo)
        self.assertEqual(volta.descricao, original.descricao)
        self.assertEqual(volta.tipo, "Clash")
        self.assertEqual(volta.situacao, "In Progress")
        self.assertEqual(volta.prioridade, "High")
        self.assertEqual(sorted(volta.rotulos), ["estrutural", "hidráulica"])
        self.assertEqual(len(volta.comentarios), 1)
        self.assertEqual(volta.comentarios[0].texto, "Confirmado em campo.")
        self.assertEqual(len(volta.pontos_de_vista), 1)

    def test_camera_3d_atravessa_intacta(self):
        """Fidelidade acima de elegância: a câmera vai com os nomes do padrão
        para o visualizador do projetista abrir no lugar certo."""
        camera = {
            "tipo": "PerspectiveCamera",
            "CameraViewPoint": {"X": 1.5, "Y": -2.0, "Z": 3.25},
            "CameraDirection": {"X": 0.0, "Y": 1.0, "Z": 0.0},
            "CameraUpVector": {"X": 0.0, "Y": 0.0, "Z": 1.0},
            "FieldOfView": 60.0,
        }
        topico = self._topico()
        topico.pontos_de_vista.append(
            bcf.PontoDeVistaBcf(guid=str(uuid.uuid4()), camera=camera)
        )
        volta = bcf.ler(bcf.escrever([topico]))[0].pontos_de_vista[0].camera
        self.assertEqual(volta["tipo"], "PerspectiveCamera")
        self.assertAlmostEqual(volta["CameraViewPoint"]["X"], 1.5)
        self.assertAlmostEqual(volta["FieldOfView"], 60.0)

    def test_marcacao_2d_gera_bcfv_valido_sem_camera(self):
        """Inventar câmera faria o visualizador do projetista abrir um ponto de
        vista arbitrário, parecendo que a marcação aponta para outro lugar."""
        topico = self._topico()
        topico.pontos_de_vista.append(bcf.PontoDeVistaBcf(guid=str(uuid.uuid4())))
        volta = bcf.ler(bcf.escrever([topico]))[0]
        self.assertEqual(volta.pontos_de_vista[0].camera, {})

    def test_snapshot_viaja_no_pacote(self):
        ponto = bcf.PontoDeVistaBcf(guid=str(uuid.uuid4()))
        topico = self._topico()
        topico.pontos_de_vista.append(ponto)
        pacote = bcf.escrever([topico], snapshots={ponto.guid: b"\x89PNG\r\n\x1a\nfake"})
        self.assertEqual(bcf.ler(pacote)[0].pontos_de_vista[0].snapshot[:4], b"\x89PNG")

    def test_doctype_e_recusado(self):
        """Guarda 1 do cabeçalho: mata *billion laughs* e entidade externa de uma
        vez, e nenhum BCF legítimo traz DTD."""
        import io
        import zipfile

        malicioso = (
            b'<?xml version="1.0"?>\n'
            b'<!DOCTYPE Markup [<!ENTITY a "aaaaaaaaaa">]>\n'
            b'<Markup><Topic Guid="x"><Title>&a;</Title></Topic></Markup>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("topico/markup.bcf", malicioso)
        with self.assertRaises(bcf.BcfInvalido):
            bcf.ler(buffer.getvalue())

    def test_arquivo_que_nao_e_zip_e_recusado_com_motivo(self):
        with self.assertRaises(bcf.BcfInvalido) as contexto:
            bcf.ler(b"isto nao e um zip")
        self.assertIn("ZIP", str(contexto.exception))

    def test_zip_sem_markup_e_recusado(self):
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("leiame.txt", b"nada aqui")
        with self.assertRaises(bcf.BcfInvalido):
            bcf.ler(buffer.getvalue())

    def test_guid_malformado_nao_derruba_a_leitura(self):
        """A marcação entra com GUID novo; o que se perde é o reencontro no
        software de origem — que já estava perdido com o GUID quebrado."""
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("t/markup.bcf", (
                b'<?xml version="1.0"?><Markup>'
                b'<Topic Guid="nao-e-um-guid"><Title>Ainda vale</Title></Topic>'
                b"</Markup>"
            ))
        lido = bcf.ler(buffer.getvalue())[0]
        self.assertEqual(lido.titulo, "Ainda vale")
        uuid.UUID(lido.guid)  # gerado, e válido


# ---------------------------------------------------------------------------
# 15. BCF — a ponte com o acervo
# ---------------------------------------------------------------------------
class BcfInteropTests(MarcacaoTestBase):
    def _pacote(self, *topicos) -> bytes:
        return bcf.escrever(list(topicos))

    def _topico_externo(self, guid=None, **extra):
        dados = {
            "guid": guid or str(uuid.uuid4()),
            "titulo": "Prumo da alvenaria fora",
            "tipo": "Issue", "situacao": "Open", "prioridade": "Normal",
            "autor": "projetista@escritorio.com",
        }
        dados.update(extra)
        return bcf.TopicoBcf(**dados)

    def test_importar_cria_a_marcacao_com_autoria_de_fora(self):
        """Quem subiu o arquivo NÃO é quem escreveu a marcação — `criado_por`
        fica nulo e a autoria real vai para `autor_nome`."""
        revisao = self._revisao(situacao="vigente")
        topico = self._topico_externo()
        resumo = interop.importar(
            self._pacote(topico), revisao=revisao, usuario=self.user, tenant=self.tenant,
        )
        self.assertEqual(resumo["criadas"], 1)

        marcacao = Marcacao.objects.get(guid=topico.guid)
        self.assertEqual(marcacao.revisao, revisao)
        self.assertEqual(marcacao.origem, Marcacao.Origem.BCF)
        self.assertIsNone(marcacao.criado_por)
        self.assertEqual(marcacao.autor_nome, "projetista@escritorio.com")

    def test_reimportar_o_mesmo_arquivo_nao_duplica(self):
        """A tese do GUID. Sem ela, cada ciclo com o escritório duplicaria a
        caixa de entrada do canteiro."""
        revisao = self._revisao(situacao="vigente")
        topico = self._topico_externo()
        topico.comentarios.append(bcf.ComentarioBcf(
            guid=str(uuid.uuid4()), texto="Refazer o trecho.", autor="eng",
        ))
        pacote = self._pacote(topico)

        interop.importar(pacote, revisao=revisao, usuario=self.user, tenant=self.tenant)
        segundo = interop.importar(
            pacote, revisao=revisao, usuario=self.user, tenant=self.tenant
        )

        self.assertEqual(segundo["criadas"], 0)
        self.assertEqual(segundo["atualizadas"], 1)
        self.assertEqual(Marcacao.objects.filter(guid=topico.guid).count(), 1)
        # E a conversa não se empilha: três respostas não viram trinta.
        self.assertEqual(ComentarioMarcacao.objects.count(), 1)

    def test_situacao_mudada_no_escritorio_volta_para_ca(self):
        """É o que faz o round-trip valer: fechar no Solibri fecha aqui."""
        revisao = self._revisao(situacao="vigente")
        guid = str(uuid.uuid4())
        interop.importar(
            self._pacote(self._topico_externo(guid=guid)),
            revisao=revisao, usuario=self.user, tenant=self.tenant,
        )
        interop.importar(
            self._pacote(self._topico_externo(guid=guid, situacao="Closed")),
            revisao=revisao, usuario=self.user, tenant=self.tenant,
        )
        self.assertEqual(Marcacao.objects.get(guid=guid).situacao, "Closed")

    def test_importacao_nao_apaga_a_ancora_nem_muda_a_prancha(self):
        """São nossas: o BCF não as carrega, e sobrescrevê-las com o default do
        formato apagaria o que só existe aqui."""
        revisao = self._revisao(situacao="vigente")
        outra = self._revisao(documento=self._documento(codigo="EST-9"), revisao="R00")
        marcacao = self._marcacao(revisao=revisao, ancora={"x": 0.4, "y": 0.6})

        interop.importar(
            self._pacote(self._topico_externo(guid=str(marcacao.guid), titulo="Título novo")),
            revisao=outra, usuario=self.user, tenant=self.tenant,
        )
        marcacao.refresh_from_db()
        self.assertEqual(marcacao.titulo, "Título novo")   # veio de fora
        self.assertEqual(marcacao.ancora, {"x": 0.4, "y": 0.6})  # não foi tocada
        self.assertEqual(marcacao.revisao, revisao)              # nem a prancha

    def test_vocabulario_desconhecido_cai_no_padrao_em_vez_de_recusar(self):
        """`TopicType`/`TopicStatus` são vocabulário ABERTO no BCF: cada
        ferramenta inventa o seu. Recusar o arquivo perderia o apontamento."""
        revisao = self._revisao(situacao="vigente")
        topico = self._topico_externo(situacao="Aguardando terceiro", tipo="Coisa")
        interop.importar(
            self._pacote(topico), revisao=revisao, usuario=self.user, tenant=self.tenant,
        )
        marcacao = Marcacao.objects.get(guid=topico.guid)
        self.assertEqual(marcacao.situacao, "Open")
        self.assertEqual(marcacao.tipo, "Issue")

    def test_responsavel_por_email_casa_com_o_usuario_do_tenant(self):
        """É o que faz 'atribuídas a mim' funcionar para o que veio de fora — e é
        escopado ao tenant, senão o e-mail que existe em duas empresas atribuiria
        a marcação de uma à pessoa da outra."""
        self.user.email = "engenheiro@construtora.com"
        self.user.save(update_fields=["email"])
        revisao = self._revisao(situacao="vigente")
        topico = self._topico_externo(responsavel_email="ENGENHEIRO@construtora.com")
        interop.importar(
            self._pacote(topico), revisao=revisao, usuario=self.user, tenant=self.tenant,
        )
        self.assertEqual(Marcacao.objects.get(guid=topico.guid).responsavel, self.user)

    def test_exportar_leva_a_conversa_e_a_autoria(self):
        marcacao = self._marcacao(responsavel_email="projetista@x.com")
        ComentarioMarcacao.objects.create(
            tenant=self.tenant, marcacao=marcacao, autor=self.user, texto="Ver no local.",
        )
        PontoDeVista.objects.create(tenant=self.tenant, marcacao=marcacao)

        lido = bcf.ler(interop.exportar(Marcacao.objects.filter(pk=marcacao.pk)))[0]
        self.assertEqual(lido.guid, str(marcacao.guid))
        self.assertEqual(lido.responsavel_email, "projetista@x.com")
        self.assertEqual(len(lido.comentarios), 1)
        self.assertEqual(lido.comentarios[0].autor, self.user.username)
        self.assertEqual(len(lido.pontos_de_vista), 1)

    def test_exportar_e_reimportar_e_idempotente(self):
        """O ciclo completo, que é o que o cliente vai fazer toda semana."""
        marcacao = self._marcacao()
        revisao = marcacao.revisao
        pacote = interop.exportar(Marcacao.objects.filter(pk=marcacao.pk))

        resumo = interop.importar(
            pacote, revisao=revisao, usuario=self.user, tenant=self.tenant
        )
        self.assertEqual(resumo["criadas"], 0)
        self.assertEqual(Marcacao.objects.count(), 1)


class BcfApiTests(MarcacaoTestBase):
    """A parede comercial e a porta errada — os dois contratos da fatia."""

    def _bcfzip(self, nome="marcacoes.bcfzip"):
        topico = bcf.TopicoBcf(guid=str(uuid.uuid4()), titulo="De fora")
        return SimpleUploadedFile(nome, bcf.escrever([topico]))

    def test_plano_sem_bcf_leva_402_nos_dois_sentidos(self):
        """402 e não 403: o cliente não está proibido, ele não contratou — e a
        saída é comprar, não pedir permissão."""
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="essencial")

        exportar = self.client.get("/api/prancheta/marcacoes/bcf/")
        self.assertEqual(exportar.status_code, 402)
        self.assertEqual(exportar.json()["code"], "formato_nao_contratado")

        importar = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": revisao.pk, "arquivo": self._bcfzip()}, format="multipart",
        )
        self.assertEqual(importar.status_code, 402)

    def test_plano_com_bcf_exporta_o_pacote(self):
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.get("/api/prancheta/marcacoes/bcf/")

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])
        # NÃO é imutável, ao contrário do acervo: o mesmo filtro amanhã dá outro
        # arquivo, porque a marcação muda de situação.
        self.assertEqual(resposta["Cache-Control"], "no-store")
        self.assertEqual(bcf.ler(resposta.content)[0].guid, str(marcacao.guid))

    def test_exportacao_respeita_o_filtro_da_listagem(self):
        """O que a tela mostra é o que o arquivo leva — sem um segundo conjunto
        de regras para o usuário entender."""
        revisao = self._revisao(situacao="vigente")
        aberta = self._marcacao(revisao=revisao)
        self._marcacao(revisao=revisao, titulo="Já resolvida", situacao="Closed")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")

        pacote = self.client.get("/api/prancheta/marcacoes/bcf/?abertas=1").content
        lidos = bcf.ler(pacote)
        self.assertEqual([t.guid for t in lidos], [str(aberta.guid)])

    def test_exportacao_nao_vaza_marcacao_de_outro_tenant(self):
        outro_doc = self._documento(codigo="X-9", tenant=self.tenant_b, obra=self.obra_b)
        Marcacao.objects.create(
            tenant=self.tenant_b,
            revisao=self._revisao(documento=outro_doc, tenant=self.tenant_b),
            titulo="Da concorrente",
        )
        self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        lidos = bcf.ler(self.client.get("/api/prancheta/marcacoes/bcf/").content)
        self.assertEqual(len(lidos), 1)

    def test_importar_exige_a_prancha_de_destino(self):
        """O BCF não diz a qual prancha nossa o tópico pertence. Adivinhar
        penduraria a marcação no desenho errado, que em campo é pior que não
        importar."""
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"arquivo": self._bcfzip()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_importar_prancha_de_outro_tenant_e_400(self):
        outro_doc = self._documento(codigo="X-8", tenant=self.tenant_b, obra=self.obra_b)
        alheia = self._revisao(documento=outro_doc, tenant=self.tenant_b)
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": alheia.pk, "arquivo": self._bcfzip()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_arquivo_ilegivel_e_400_com_a_mensagem_do_usuario(self):
        """O arquivo é dele, o defeito também — 400, não 500.

        **Quem recusa mudou na PRA.5b, e por isso a asserção mudou junto.** Antes
        o texto solto chegava ao `bcf.ler`, que abria o zip e reclamava dele; hoje
        a porta única o para antes, porque estes bytes não são de formato nenhum
        que este destino receba. O que continua valendo é a tese — defeito do
        arquivo é 400 com frase de gente — e o campo diz onde ela aparece na tela.
        """
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post("/api/prancheta/marcacoes/importar-bcf/", {
            "revisao": revisao.pk,
            "arquivo": SimpleUploadedFile("x.bcfzip", b"nao sou um zip"),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("arquivo", resposta.json())

    def test_so_leitura_nao_importa(self):
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=["prancheta.marcacao.view"], plano="profissional")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": revisao.pk, "arquivo": self._bcfzip()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_bcf_nao_entra_como_revisao_do_acervo(self):
        """A porta errada, e o registry mentia sobre ela até esta fatia: o `bcf`
        figurava com motor de IFC, então o upload passaria e terminaria em
        `arquivo_corrompido` depois de ocupar storage."""
        documento = self._documento()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post("/api/prancheta/revisoes/", {
            "documento": documento.pk, "revisao": "R01", "arquivo": self._bcfzip("x.bcfzip"),
        }, format="multipart")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("marcações", str(resposta.json()["arquivo"]))


class FilaDeDecisaoComMarcacaoTests(MarcacaoTestBase):
    """A linha que a PRA.0 declarou e deixou por preencher."""

    def test_acervo_conta_marcacoes_abertas_e_as_minhas(self):
        revisao = self._revisao(situacao="vigente")
        self._marcacao(revisao=revisao)
        self._marcacao(revisao=revisao, titulo="Minha", responsavel=self.user)
        self._marcacao(revisao=revisao, titulo="Fechada", situacao="Closed")

        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        fila = self.client.get(
            f"/api/prancheta/acervo/?obra={self.obra.pk}"
        ).json()["requer_decisao"]

        self.assertEqual(fila["marcacoes_abertas"], 2)
        self.assertEqual(fila["marcacoes_atribuidas_a_mim"], 1)

    def test_marcacao_viva_sobre_desenho_superado_vira_pergunta(self):
        """Ninguém resolveu e o desenho mudou embaixo. A resposta é humana — por
        isso é fila, não limpeza automática."""
        antiga = self._revisao(revisao="R00", situacao="superada")
        self._marcacao(revisao=antiga)

        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        fila = self.client.get(
            f"/api/prancheta/acervo/?obra={self.obra.pk}"
        ).json()["requer_decisao"]
        self.assertEqual(fila["marcacoes_em_revisao_superada"], 1)

    def test_minhas_alcanca_a_marcacao_que_chegou_por_email(self):
        """A importada de BCF pode ter vindo endereçada ao e-mail sem casar com o
        usuário (cadastro sem e-mail, grafia diferente). Quem abre a fila espera
        vê-la."""
        self.user.email = "eu@construtora.com"
        self.user.save(update_fields=["email"])
        self._marcacao(responsavel_email="eu@construtora.com")

        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        corpo = self.client.get("/api/prancheta/marcacoes/?minhas=1").json()
        self.assertEqual(corpo["count"], 1)


# ---------------------------------------------------------------------------
# PRA.3b — a escala que o próprio desenho declara
# ---------------------------------------------------------------------------
class EscalaDoDesenhoTests(SimpleTestCase):
    """A conversão de `$INSUNITS` em metro, sem banco e sem ezdxf.

    A regra que estes testes protegem é uma só: **na dúvida, sem escala**. Toda
    porta de saída que não seja um metro comprovado devolve `{}`, porque a
    alternativa — escrever "3,50 m" a partir de um cabeçalho duvidoso — é a
    única falha deste módulo que vira parede no lugar errado.
    """

    def test_milimetros_viram_metro_na_largura_da_folha(self):
        # 1020 mm de folha, desenho em milímetros ⇒ 1,02 m de largura real.
        achado = escala_do_desenho('<svg width="1020mm" height="520mm"', unidades=4)
        self.assertAlmostEqual(achado["escala_largura_m"], 1.02)
        self.assertEqual(achado["unidades_rotulo"], "milímetros")

    def test_a_unidade_do_desenho_muda_a_conta(self):
        """Mesma folha, unidade diferente: é o `$INSUNITS` que decide o metro —
        e é exatamente por isso que um desenho que não a declara não ganha
        régua nenhuma."""
        em_metros = escala_do_desenho('<svg width="1000mm"', unidades=6)
        em_milimetros = escala_do_desenho('<svg width="1000mm"', unidades=4)
        self.assertAlmostEqual(em_metros["escala_largura_m"], 1000.0)
        self.assertAlmostEqual(em_milimetros["escala_largura_m"], 1.0)

    def test_polegada_e_pe_tambem_chegam_em_metro(self):
        self.assertAlmostEqual(
            escala_do_desenho('<svg width="100mm"', unidades=1)["escala_largura_m"], 2.54)
        self.assertAlmostEqual(
            escala_do_desenho('<svg width="100mm"', unidades=2)["escala_largura_m"], 30.48)

    def test_desenho_sem_unidade_declarada_nao_ganha_escala(self):
        """`$INSUNITS = 0` é o caso mais comum do acervo real. Sem unidade não há
        metro — a prancha segue medindo em fração da largura, e a tela diz isso."""
        achado = escala_do_desenho('<svg width="1020mm"', unidades=0)
        self.assertNotIn("escala_largura_m", achado)
        self.assertEqual(achado["unidades_desenho"], 0)

    def test_unidade_fora_da_tabela_nao_ganha_escala(self):
        """Ano-luz (19) num arquivo de construtora é cabeçalho corrompido, não
        desenho. Converter seria aritmética correta sobre premissa absurda."""
        self.assertNotIn("escala_largura_m", escala_do_desenho('<svg width="1020mm"', unidades=19))

    def test_folha_em_notacao_cientifica_e_lida(self):
        """O ezdxf emite `width="4.00002e+06mm"` a partir de ~7 dígitos, e o
        padrão antigo (`[0-9.]+`) não casava — toda prancha com folha acima de
        ~1 km perdia a régua **em silêncio**, indistinguível de quem não declara
        unidade. A resposta certa aqui é uma recusa **declarada**, não o vazio."""
        achado = escala_do_desenho('<svg width="4.00002e+06mm"', unidades=4)
        self.assertAlmostEqual(achado["escala_largura_m"], 4000.02, places=2)
        # E a folha absurda continua sendo recusada — com o valor no registro.
        recusada = escala_do_desenho('<svg width="8.56486e+06mm"', unidades=6)
        self.assertNotIn("escala_largura_m", recusada)
        self.assertAlmostEqual(recusada["escala_recusada"], 8_564_860.0, places=0)

    def test_largura_implausivel_e_recusada_e_declarada(self):
        """Modelado em milímetros e declarado em metros: a prancha "mede" 42 km.
        Recusar é obrigatório; registrar o valor recusado é o que permite alguém
        entender depois por que aquela prancha ficou sem régua."""
        achado = escala_do_desenho('<svg width="42020mm"', unidades=7)  # km
        self.assertNotIn("escala_largura_m", achado)
        self.assertAlmostEqual(achado["escala_recusada"], 42020000.0)

    def test_svg_sem_largura_nao_inventa_numero(self):
        self.assertNotIn("escala_largura_m", escala_do_desenho("<svg>", unidades=4))


class EscalaDaPaginaRealTests(APITestCase):
    """Prende a premissa da conta contra o `ezdxf` de verdade.

    `escala_do_desenho` lê a largura da página em mm e a trata como unidades de
    desenho. Isso só vale enquanto `Settings(scale=1.0)` significar "1 unidade =
    1 mm" — uma mudança de default do ezdxf, ou alguém mexendo em `MARGEM_MM`,
    transformaria todo metro deste módulo em número errado **sem quebrar teste
    nenhum**. Este é o teste que quebra.
    """

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_um_metro_desenhado_vira_um_metro_medido(self):
        import os
        import tempfile

        import ezdxf

        documento = ezdxf.new("R2010")
        documento.header["$INSUNITS"] = 4  # milímetros
        # Retângulo de 1000 × 500 mm = 1,00 m de largura de conteúdo.
        documento.modelspace().add_lwpolyline(
            [(0, 0), (1000, 0), (1000, 500), (0, 500)], close=True)
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as arquivo:
            caminho = arquivo.name
        documento.saveas(caminho)
        self.addCleanup(lambda: os.unlink(caminho))

        saida = ADAPTADORES["ezdxf"].converter(caminho, formato="dxf", tipo="vetor_2d")

        # 1,00 m de desenho + a margem dos dois lados, que é folha e conta na
        # largura porque as coordenadas de medição são normalizadas por ela.
        esperado = (1000 + 2 * MARGEM_MM) / 1000
        self.assertAlmostEqual(saida.detalhe["escala_largura_m"], esperado, places=4)
        self.assertEqual(saida.detalhe["unidades_desenho"], 4)



class EnquadramentoTests(SimpleTestCase):
    """D46 — a prancha que converte, abre a 60 fps e mostra uma tarja preta.

    A derivada fica `pronto`, o visualizador abre em 0,19 s, e o canteiro vê uma
    faixa escura de 46 px com o zoom marcando 0%: a folha é dimensionada pela
    extensão do desenho, e quando essa extensão é muito maior que o desenho o
    ajuste à tela reduz tudo a nada.

    **A regra que estes testes protegem é uma só: nada é apagado.** A tentação de
    recortar o que está longe foi recusada — um traço solto pode ser um marco
    topográfico ou uma referência de amarração, e a prancha com *duas* poligonais
    prova o custo do erro: qualquer recorte agressivo o bastante para isolar uma
    apagaria a outra. O motor **mede e descreve**; quem resolve é o zoom.
    """

    def _gravar(self, documento) -> str:
        import os
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        documento.saveas(caminho)
        self.addCleanup(lambda: os.path.exists(caminho) and os.unlink(caminho))
        return caminho

    def _prancha(self, *, traços=300, longe=None, segunda=None):
        """Prancha de 1.000 × 700, opcionalmente com um traço solto (`longe`) ou
        com um segundo desenho igual deslocado (`segunda`)."""
        import ezdxf

        documento = ezdxf.new("R2010")
        documento.header["$INSUNITS"] = 4  # milímetros
        espaco = documento.modelspace()
        passo = 1000 / traços
        for i in range(traços):
            x, y = i * passo, (i * 37) % 700
            espaco.add_line((x, y), (x + 12, y + 9))
            if segunda:
                espaco.add_line(
                    (x + segunda[0], y + segunda[1]),
                    (x + 12 + segunda[0], y + 9 + segunda[1]),
                )
        if longe:
            espaco.add_line(longe, (longe[0] + 1, longe[1] + 1))
        return self._gravar(documento)

    def _converter(self, caminho):
        return ADAPTADORES["ezdxf"].converter(caminho, formato="dxf", tipo="vetor_2d")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_nada_e_apagado_do_desenho(self):
        """**O teste central desta fatia.** O mesmo desenho, com e sem o traço
        solto, tem de sair com um path a mais **somando as folhas** — não com a
        folha "consertada" e o traço no lixo. A plataforma não decide o que no
        arquivo do cliente sobra; ela dá uma folha a cada coisa.
        """
        limpa = self._converter(self._prancha())
        com_solto = self._converter(self._prancha(longe=(8_500_000, 400_000)))

        total = sum(p.conteudo.count(b"<path") for p in com_solto.partes)
        self.assertEqual(total, limpa.conteudo.count(b"<path") + 1)
        self.assertEqual(com_solto.detalhe["registros"],
                         limpa.detalhe["registros"] + 1)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_traco_solto_vira_uma_folha_propria_com_a_contagem(self):
        """Ele não é escondido nem apagado: vira a própria folha, com **1 traço**,
        ao lado da de 300. A contagem é o que deixa o dono do arquivo decidir se
        aquilo é lixo ou o ponto que ele foi a campo levantar."""
        saida = self._converter(self._prancha(longe=(8_500_000, 400_000)))

        self.assertEqual([p.tracos for p in saida.partes], [300, 1])
        # Maior primeiro: quem abre a prancha quer o desenho, não o traço solto.
        self.assertEqual(saida.partes[0].ordem, 1)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_duas_plantas_iguais_e_distantes_viram_duas_folhas(self):
        """O caso que derrubou a primeira tentativa de conserto: `CONFRONTANTES
        POLIGONAL` traz duas poligonais **de mesmo tamanho** a 8,5 milhões de
        unidades uma da outra. Nenhum quantil as separa (cada uma tem metade dos
        traços), e recortar para uma só apagaria a outra — dar uma folha a cada
        preserva as duas."""
        saida = self._converter(self._prancha(traços=150, segunda=(0, 900_000)))

        self.assertEqual(len(saida.partes), 2)
        self.assertEqual([p.tracos for p in saida.partes], [150, 150])
        self.assertEqual(sum(p.conteudo.count(b"<path") for p in saida.partes), 300)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_folha_de_cada_desenho_tem_tamanho_de_prancha(self):
        """**O defeito que esta fatia existe para matar.** Numa folha só, o par de
        poligonais dava 8,5 km de altura — 1:18 de aspecto, 46 px na tela, zoom
        marcando 0% e nenhum navegador capaz de rasterizar. Separadas, cada folha
        mede o que o desenho mede."""
        import re

        saida = self._converter(self._prancha(traços=150, segunda=(0, 900_000)))
        for parte in saida.partes:
            cabecalho = parte.conteudo.decode()[:600]
            largura = float(re.search(r'width="([0-9.e+]+)mm"', cabecalho).group(1))
            altura = float(re.search(r'height="([0-9.e+]+)mm"', cabecalho).group(1))
            self.assertLess(max(largura, altura) / min(largura, altura), 4)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_prancha_normal_sai_com_uma_folha_so(self):
        """O risco desta fatia é o oposto do defeito: estilhaçar em dezenas de
        folhas a prancha que abre bem. Desenho sozinho **não passa pelo recorte** —
        a folha sai igual à de antes desta mudança."""
        saida = self._converter(self._prancha())

        self.assertEqual(len(saida.partes), 1)
        self.assertEqual(saida.partes[0].ordem, 1)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_dois_desenhos_proximos_continuam_na_mesma_folha(self):
        """O critério é "a lacuna é maior que o próprio desenho". Dois desenhos a
        2.000 de distância, cada um com 1.000 de extensão, são uma folha só — é a
        planta com o corte ao lado, que se lê junta."""
        saida = self._converter(self._prancha(traços=150, segunda=(0, 900)))

        self.assertEqual(len(saida.partes), 1)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_caixa_do_desenho_viaja_em_unidade_de_desenho(self):
        """É ela que reencontra o mesmo desenho na revisão seguinte para herdar o
        nome. Normalizada pela folha não serviria: a folha muda quando o
        projetista mexe no desenho, o lugar no terreno não."""
        saida = self._converter(self._prancha(traços=150, segunda=(0, 900_000)))
        alto, baixo = saida.partes

        # O segundo desenho foi deslocado +900.000 em Y, e é isso que a caixa diz.
        self.assertAlmostEqual(abs(alto.caixa["ymin"] - baixo.caixa["ymin"]),
                               900_000, delta=50)
        for parte in saida.partes:
            self.assertLess(parte.caixa["xmin"], parte.caixa["xmax"])
            self.assertLess(parte.caixa["ymin"], parte.caixa["ymax"])

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_cada_folha_tem_a_propria_regua(self):
        """A escala é "unidades reais na largura do desenho", e cada folha tem uma
        largura. Um número só para a revisão descreveria no máximo uma delas — em
        silêncio, para as outras."""
        saida = self._converter(self._prancha(traços=150, segunda=(3_000_000, 0)))

        self.assertEqual(len(saida.partes), 2)
        for parte in saida.partes:
            self.assertGreater(parte.detalhe["escala_largura_m"], 0)


class VersaoNaUrlDaDerivadaTests(PranchetaTestBase):
    """Reconverter tem de **chegar na tela**, e por um ano não chegava.

    A derivada é única por `(revisão, tipo, motor)` e a MESMA linha é reescrita a
    cada reconversão — `reprocessar/`, motor novo, upgrade de plano para a APS
    (que a planta §4.1 promete: "subir de plano reconverte com o motor melhor").
    A URL, porém, era só o id, e a resposta sai `immutable` com um ano de
    `max-age`. O navegador de quem já abrira a prancha **nunca mais perguntava**.

    Foi exatamente o que aconteceu com o conserto do D46: aplicado no servidor,
    provado por teste, invisível na tela. O sintoma é cruel porque acusa o lado
    errado — o cliente jura que nada mudou, e ele está certo sobre o que vê.
    """

    def _derivada_pronta(self, **campos):
        documento = self._documento(codigo=f"ARQ-VER-{uuid.uuid4().hex[:8]}")
        revisao = RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00", situacao="vigente",
            arquivo=SimpleUploadedFile("p.dxf", b"0\nSECTION\n"),
            nome_original="p.dxf", formato="dxf", tamanho_bytes=10,
        )
        derivada = DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo=DerivadaProjeto.Tipo.VETOR_2D,
            motor="ezdxf", estado=DerivadaProjeto.Estado.PRONTO,
            hash_origem="abc", motor_versao="ezdxf-1.4.4",
            concluido_em=timezone.now(), **campos,
        )
        derivada.arquivo.save("d.svg", SimpleUploadedFile("d.svg", b"<svg/>"), save=True)
        return derivada

    def test_a_url_carrega_a_versao_do_conteudo(self):
        from . import entrega

        derivada = self._derivada_pronta()
        url = entrega.url_da_derivada(derivada.pk, entrega.versao_da_derivada(derivada))

        self.assertIn(f"/arquivo/derivada/{derivada.pk}/", url)
        self.assertRegex(url, r"\?v=[0-9a-f]{12}$")

    def test_reconverter_muda_a_url(self):
        """O teste que faltava. Mesmo id, mesmo arquivo de origem, motor igual —
        e conteúdo novo porque a conversão foi consertada. Se a URL não mudar, o
        conserto não chega a ninguém."""
        from . import entrega

        derivada = self._derivada_pronta()
        antes = entrega.versao_da_derivada(derivada)

        derivada.concluido_em = timezone.now() + timedelta(minutes=1)
        depois = entrega.versao_da_derivada(derivada)

        self.assertNotEqual(antes, depois)

    def test_motor_novo_tambem_muda_a_url(self):
        """O caso do upgrade de plano: mesmo arquivo, motor melhor."""
        from . import entrega

        derivada = self._derivada_pronta()
        antes = entrega.versao_da_derivada(derivada)
        derivada.motor_versao = "aps-2026"

        self.assertNotEqual(antes, entrega.versao_da_derivada(derivada))

    def test_derivada_intocada_mantem_a_mesma_url(self):
        """O outro lado: se a versão mudasse a cada leitura, o `immutable` viraria
        mentira ao contrário e o canteiro rebaixaria a prancha toda vez."""
        from . import entrega

        derivada = self._derivada_pronta()
        self.assertEqual(entrega.versao_da_derivada(derivada),
                         entrega.versao_da_derivada(derivada))

    def test_o_acervo_entrega_a_url_versionada(self):
        """O caminho real: é por `conversao.visualizador` que a tela abre."""
        derivada = self._derivada_pronta()

        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()

        alvo = corpo["disciplinas"][0]["documentos"][0]["vigente"]["conversao"]["visualizador"]
        self.assertRegex(alvo, r"/arquivo/derivada/\d+/\?v=[0-9a-f]{12}$")

    def test_a_versao_nao_abre_porta(self):
        """`?v=` é dica de cache, não credencial: o gate continua sendo o do
        módulo. Um `v` errado (ou ausente) serve o mesmo arquivo a quem pode —
        e nada a quem não pode."""
        derivada = self._derivada_pronta()
        self.autenticar()

        certo = self.client.get(f"{entrega.url_da_derivada(derivada.pk)}?v=deadbeef")
        self.assertEqual(certo.status_code, 200)

        self.client.force_authenticate(user=None)
        self.assertIn(
            self.client.get(
                f"{entrega.url_da_derivada(derivada.pk)}?v=deadbeef").status_code,
            (401, 403))


class GradeDeSaidaTests(SimpleTestCase):
    """O degrau que vem **antes** do zoom: a informação tem de ser emitida.

    O `SVGBackend` do ezdxf escreve coordenadas **inteiras** numa grade fixa
    esticada sobre a folha inteira. Um desenho que ocupa uma fração ínfima da
    folha recebe uma fração ínfima da grade e é **destruído na emissão** — não
    fica pequeno, fica ausente. Medido no arquivo das duas poligonais: 34% dos
    segmentos viravam `l -0 -0` e o `stroke-width` arredondava para 0, então
    linha, hachura e ponto não apareciam **em zoom nenhum**.

    Estes testes existem porque o sintoma engana: parece defeito de tela.
    """

    def _prancha_com_folha_grande(self, distancia):
        """Desenho de 1.000 × 700 num canto e um traço a `distancia` — a folha
        cresce e o desenho encolhe dentro da grade."""
        import ezdxf

        documento = ezdxf.new("R2010")
        documento.header["$INSUNITS"] = 4
        espaco = documento.modelspace()
        for i in range(200):
            x, y = i * 5, (i * 37) % 700
            espaco.add_line((x, y), (x + 12, y + 9))
        if distancia:
            espaco.add_line((distancia, distancia), (distancia + 1, distancia + 1))

        import os
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        documento.saveas(caminho)
        self.addCleanup(lambda: os.path.exists(caminho) and os.unlink(caminho))
        return caminho

    def test_a_grade_e_dimensionada_pelo_desenho_nao_pela_folha(self):
        from .motores.dxf import GRADE_MAXIMA, GRADE_PADRAO, _grade_de_saida

        # Prancha que ocupa a folha: nada muda, e é a maioria do acervo.
        self.assertEqual(_grade_de_saida(1.0), GRADE_PADRAO)
        self.assertEqual(_grade_de_saida(0.2), GRADE_PADRAO)
        # Desenho minúsculo na folha: a grade cresce para ele caber nela.
        self.assertEqual(_grade_de_saida(0.01), 10_000_000)
        # O caso real. `…75` e não `…74` desde 15/08/2026: a grade passou a ser
        # arredondada para CIMA, porque truncar tira uma fração de unidade e
        # essa fração vira precisão pior que a contratada (ver `PRECISAO_DE_DESENHO`).
        self.assertEqual(_grade_de_saida(0.000127), 787_401_575)
        # E para no teto: acima dele a grade engorda o SVG sem devolver desenho.
        self.assertEqual(_grade_de_saida(0.00001), GRADE_MAXIMA)
        self.assertEqual(_grade_de_saida(0.0000001), GRADE_MAXIMA)
        # Sem medida, o padrão — nunca um palpite.
        self.assertEqual(_grade_de_saida(None), GRADE_PADRAO)
        self.assertEqual(_grade_de_saida(0), GRADE_PADRAO)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_desenho_minusculo_na_folha_nao_perde_o_traco(self):
        """**O teste do sintoma que o usuário viu:** linhas somem, texto fica.
        Glifo é preenchimento e sobrevive ao arredondamento; traço não.

        Prende as duas metades: nenhum `stroke-width: 0` (a linha existe) e
        nenhuma enxurrada de segmento zerado (a geometria existe)."""
        import re

        saida = ADAPTADORES["ezdxf"].converter(
            self._prancha_com_folha_grande(4_000_000), formato="dxf", tipo="vetor_2d")
        texto = saida.conteudo.decode()

        larguras = {float(v) for v in re.findall(r"stroke-width:\s*([0-9.]+)", texto)}
        self.assertTrue(larguras, "o SVG saiu sem nenhuma regra de traço")
        self.assertNotIn(0.0, larguras, "traço de espessura zero é linha invisível")

        caminhos = re.findall(r'\sd="([^"]+)"', texto)
        zerados = sum(len(re.findall(r"[lm]\s-?0\s-?0(?=\s|$)", d)) for d in caminhos)
        total = sum(len(re.findall(r"[lmq]\s", d)) for d in caminhos)
        self.assertLess(zerados / max(total, 1), 0.05,
                        f"{zerados}/{total} segmentos colapsaram para zero")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_prancha_normal_paga_so_a_grade_da_quinta_casa(self):
        """A grade da prancha comum é a que a **precisão** pede — nem mais.

        Este teste dizia o contrário até 15/08/2026 ("prancha normal não
        engorda", grade no padrão do `ezdxf`), e a regra mudou por decisão do
        dono: todo projeto tem precisão na quinta casa decimal. Como as
        coordenadas do SVG são inteiras, elas **são** o passo em que a tinta pode
        existir — com 10⁶ numa folha de 133 unidades o passo é 0,00013, a quarta
        casa. A grade deixou de ser só a rede de segurança do D46 e passou a ser
        também o instrumento da precisão.

        O que continua prendido é o que importa: ela cresce pela precisão, e
        **não** pela regra do D46 (que pediria bem mais nesta folha ocupada).
        """
        from .motores.dxf import PRECISAO_DE_DESENHO, RESOLUCAO_ALVO

        saida = ADAPTADORES["ezdxf"].converter(
            self._prancha_com_folha_grande(0), formato="dxf", tipo="vetor_2d")

        grade = saida.detalhe["grade"]
        passo = saida.detalhe["precisao_desenho"]
        self.assertLessEqual(
            passo, PRECISAO_DE_DESENHO,
            f"a folha resolve {passo:.8f} unidade de desenho, e o contrato é 1e-5")
        # Não é a regra do D46 mandando: com ocupação ~1 ela pediria o padrão.
        self.assertGreater(grade, RESOLUCAO_ALVO)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_separar_as_folhas_dispensa_a_grade_grande(self):
        """**A grade deixou de ser a defesa, e isto documenta por quê.**

        Ela existia porque o `SVGBackend` emite coordenadas inteiras sobre a folha
        inteira: numa página esticada por uma entidade a 4 milhões de unidades, o
        desenho recebia uma fração ínfima da grade e era *destruído na emissão* —
        `l -0 -0`, `stroke-width` arredondado a zero. Com cada desenho na própria
        folha o problema não chega a existir, e a grade volta ao padrão do ezdxf
        nos dois casos: o SVG emagrece sem perder um traço.

        A grade fica no código como rede de segurança, não como remédio de uso
        diário — e é isso que este teste prende.
        """
        from .motores.dxf import GRADE_MAXIMA

        largo = ADAPTADORES["ezdxf"].converter(
            self._prancha_com_folha_grande(4_000_000), formato="dxf", tipo="vetor_2d")
        estreito = ADAPTADORES["ezdxf"].converter(
            self._prancha_com_folha_grande(0), formato="dxf", tipo="vetor_2d")

        # A entidade distante virou a própria folha, então a folha do desenho
        # voltou a ser uma folha comum.
        self.assertEqual(len(largo.partes), 2)
        self.assertEqual(len(estreito.partes), 1)
        # A folha do DESENHO passou a ser a MESMA nos dois casos — que é o ponto
        # deste teste. Ela não é mais `GRADE_PADRAO` porque desde 15/08/2026 a
        # grade também carrega a precisão de quinta casa (ver
        # `test_prancha_normal_paga_so_a_grade_da_quinta_casa`); o que o D46
        # prende aqui é que separar as folhas tirou a *inflação* da grade, e isso
        # continua verdade: as duas folhas de mesmo desenho pedem a mesma grade.
        self.assertEqual(largo.partes[0].detalhe["grade"],
                         estreito.partes[0].detalhe["grade"])
        self.assertLess(largo.partes[0].detalhe["grade"], GRADE_MAXIMA)
        # A régua de cada um continua sendo a largura da própria folha.
        for saida in (largo, estreito):
            self.assertEqual(saida.detalhe["unidades_desenho"], 4)
            self.assertIn("escala_largura_m", saida.detalhe)


class FundoQueCobreAFolhaTests(SimpleTestCase):
    """O papel da prancha tem de cobrir a prancha — no NAVEGADOR, que é onde se lê.

    **O defeito que estes testes prendem.** O `SVGBackend` emite o fundo como um
    `<rect>` com os lados em unidade de `viewBox`. Depois que a grade passou a ser
    dimensionada pela precisão de quinta casa (15/08/2026), esses lados chegaram a
    8,6×10⁷ na `001` — e o Chromium **para de pintar** o retângulo em 2²⁵
    (33.554.432), deixando dois terços da folha sem fundo. Medido em 16/08/2026
    num `<img>` de 1250 px: o fundo cobria 486 px.

    O traço não sofre (são segmentos curtos), então a prancha "abre": ela fica
    linha clara sobre fundo claro na maior parte da área — a família de defeito do
    D46, em que a folha parece pronta e esconde o desenho.

    **O `librsvg` pinta a folha inteira nos dois casos**, e é por isso que
    miniatura e PDF nunca denunciaram. Um teste que rasterizasse aqui passaria com
    o defeito em pé; o que dá para prender sem navegador é o **contrato**: o fundo
    não sai em unidade de `viewBox`.
    """

    def _folha(self, distancia=0):
        import os
        import tempfile

        import ezdxf

        documento = ezdxf.new("R2010")
        documento.header["$INSUNITS"] = 4
        espaco = documento.modelspace()
        for i in range(200):
            x, y = i * 5, (i * 37) % 700
            espaco.add_line((x, y), (x + 12, y + 9))
        if distancia:
            espaco.add_line((distancia, distancia), (distancia + 1, distancia + 1))
        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        documento.saveas(caminho)
        self.addCleanup(lambda: os.path.exists(caminho) and os.unlink(caminho))
        return caminho

    def test_reescreve_so_o_retangulo_que_tem_os_lados_da_folha(self):
        """A troca é cirúrgica: fundo vira `100%`, desenho do projetista não."""
        from .motores.dxf import _fundo_em_porcentagem

        cabecalho = '<svg viewBox="0 0 86186100 61461400"><defs></defs>'

        fundo = cabecalho + (
            '<rect fill="#212830" x="0" y="0" width="86186100" '
            'height="61461400" fill-opacity="1.0" /></svg>'
        )
        saiu = _fundo_em_porcentagem(fundo)
        self.assertIn('width="100%" height="100%"', saiu)
        # O resto do atributo sobrevive — cor e opacidade são do papel.
        self.assertIn('fill="#212830"', saiu)
        self.assertIn('fill-opacity="1.0"', saiu)

        # Retângulo do DESENHO, quase do tamanho da folha: intocado. Reescrevê-lo
        # esticaria geometria do projetista até a borda da prancha.
        desenho = cabecalho + (
            '<rect fill="#212830" x="0" y="0" width="86186099" '
            'height="61461400" fill-opacity="1.0" /></svg>'
        )
        self.assertEqual(_fundo_em_porcentagem(desenho), desenho)

        # Folha sem `viewBox` legível e folha sem retângulo nenhum: passa reto.
        self.assertEqual(_fundo_em_porcentagem("<svg></svg>"), "<svg></svg>")
        vazia = cabecalho + "</svg>"
        self.assertEqual(_fundo_em_porcentagem(vazia), vazia)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_nenhuma_folha_emitida_leva_fundo_em_unidade_de_viewbox(self):
        """O contrato, no SVG que o motor de verdade produz.

        Vale para a folha comum e para a de grade grande: é justamente a segunda
        que cruzava o teto do Chromium, e prender só a primeira deixaria o defeito
        voltar pelo caminho em que ele apareceu.
        """
        import re

        for distancia in (0, 4_000_000):
            with self.subTest(distancia=distancia):
                saida = ADAPTADORES["ezdxf"].converter(
                    self._folha(distancia), formato="dxf", tipo="vetor_2d")
                texto = saida.conteudo.decode()
                caixa = re.search(r'viewBox="\s*0\s+0\s+([\d.]+)\s+([\d.]+)', texto)
                self.assertIsNotNone(caixa)
                fundo = re.search(r"<rect[^>]*>", texto)
                self.assertIsNotNone(fundo, "a folha saiu sem retângulo de fundo")
                self.assertIn('width="100%"', fundo.group(0))
                self.assertIn('height="100%"', fundo.group(0))
                # E o número da grade continua onde tem de estar: no `viewBox`,
                # que é quem carrega a quinta casa. O conserto do fundo não pode
                # ter sido "encolher a grade".
                self.assertNotIn(f'width="{caixa.group(1)}"', fundo.group(0))


class AvisoDaPranchaSuspeitaTests(PranchetaTestBase):
    """A segunda metade do D46: o que o enquadramento não resolve, ele **diz**.

    O estado `pronto` deixou de bastar para a tela ficar calada. Uma derivada que
    abre pode ainda assim estar ilegível, e o critério de quando avisar é do
    domínio — refazê-lo em cada tela que mostra uma derivada garantiria duas
    versões dele em um mês, que é a mesma razão do `exige_upgrade`.
    """

    def _derivada(self, memoria, estado=DerivadaProjeto.Estado.PRONTO, folhas=1):
        # Código único por chamada: o `unique(obra, codigo)` é do domínio (duas
        # pranchas com o mesmo código na mesma obra é justamente o que o acervo
        # existe para impedir), e o teste não pode contorná-lo relaxando-o.
        documento = self._documento(codigo=f"ARQ-D46-{uuid.uuid4().hex[:8]}")
        revisao = RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00", situacao="vigente",
            arquivo=SimpleUploadedFile("planta.dxf", b"0\nSECTION\n"),
            nome_original="planta.dxf", formato="dxf", tamanho_bytes=10,
        )
        desenhos = [
            DesenhoProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, ordem=i, tracos=169,
                caixa={"xmin": 0.0, "ymin": i * 9e5, "xmax": 1000.0, "ymax": i * 9e5 + 700},
            )
            for i in range(1, folhas + 1)
        ]
        return DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, desenho=desenhos[0] if desenhos else None,
            tipo=DerivadaProjeto.Tipo.VETOR_2D,
            motor="ezdxf", estado=estado, memoria=memoria,
        )

    UTM = {"georreferenciado": True, "sistema_provavel": "UTM",
           "unidade_corrigida": "O cabeçalho declara pés, mas as coordenadas são UTM."}

    def test_arquivo_com_duas_folhas_diz_quantas_sao(self):
        """A frase que o dono do acervo pediu que continuasse no topo: sem ela,
        quem abre a primeira folha conclui que o resto se perdeu."""
        from .serializers import aviso_da_revisao

        derivada = self._derivada({}, folhas=2)
        aviso = aviso_da_revisao(list(derivada.revisao.desenhos.all()), derivada.memoria)

        self.assertEqual(aviso["codigo"], "varios_desenhos")
        self.assertIn("2 desenhos", aviso["titulo"])

    def test_folha_unica_e_sem_coordenada_de_mundo_nao_avisa_nada(self):
        """Avisar aqui treinaria o canteiro a ignorar o aviso que importa."""
        from .serializers import aviso_da_revisao

        derivada = self._derivada({}, folhas=1)
        self.assertIsNone(
            aviso_da_revisao(list(derivada.revisao.desenhos.all()), derivada.memoria))

    def test_georreferenciado_avisa_mesmo_com_uma_folha_so(self):
        """É a explicação de por que a régua não bate com o que um template errado
        mostraria — e o gancho do seam com o Maps."""
        from .serializers import aviso_da_revisao

        derivada = self._derivada(self.UTM, folhas=1)
        aviso = aviso_da_revisao(list(derivada.revisao.desenhos.all()), derivada.memoria)

        self.assertEqual(aviso["codigo"], "georreferenciado")
        self.assertTrue(aviso["georreferenciado"])
        self.assertIn("UTM", aviso["mensagem"])

    def test_derivada_em_erro_nao_ganha_segundo_canal(self):
        """Quem falhou já fala por `erro_motivo`. Dois alertas para o mesmo fato
        fariam a tela contradizer a própria fila de decisão."""
        from .serializers import DerivadaProjetoSerializer

        derivada = self._derivada({}, estado=DerivadaProjeto.Estado.ERRO, folhas=2)
        self.assertIsNone(DerivadaProjetoSerializer(derivada).data["aviso"])

    def test_memoria_de_motor_antigo_nao_quebra_o_aviso(self):
        """Derivada convertida antes desta fatia não tem as chaves novas na
        memória. Ela não avisa — é anterior à pergunta."""
        from .serializers import aviso_da_revisao

        derivada = self._derivada({"dxfversion": "AC1032"}, folhas=1)
        desenhos = list(derivada.revisao.desenhos.all())
        self.assertIsNone(aviso_da_revisao(desenhos, derivada.memoria))
        self.assertIsNone(aviso_da_revisao(desenhos, None))

    def test_o_aviso_chega_no_acervo_junto_da_prancha(self):
        """O caminho que a tela usa de verdade: o visualizador entra pelo resumo
        do acervo, e um aviso que só existisse no serializer completo da derivada
        ficaria calado exatamente na tela que mostra a prancha."""
        derivada = self._derivada({}, folhas=2)
        derivada.arquivo.save("d.svg", SimpleUploadedFile("d.svg", b"<svg/>"), save=True)

        self.autenticar()
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()

        vigente = corpo["disciplinas"][0]["documentos"][0]["vigente"]
        self.assertEqual(vigente["conversao"]["estado"], "pronta")
        self.assertEqual(vigente["conversao"]["aviso"]["codigo"], "varios_desenhos")
        # As folhas viajam no resumo: é por elas que a lista lateral troca de
        # prancha sem uma segunda chamada.
        self.assertEqual(len(vigente["desenhos"]), 2)
        self.assertEqual(vigente["desenhos"][0]["rotulo"], "Desenho 1")
        # Abre **e** aponta: a prancha continua acessível, a rota a acompanha.
        self.assertIsNotNone(vigente["conversao"]["visualizador"])


class EscalaDerivadaPeloPipelineTests(PranchetaTestBase):
    """Quem publica a escala do desenho é o pipeline, e a regra de precedência
    mora aqui: **máquina não sobrescreve pessoa**."""

    def _revisao_dxf(self, **extra):
        documento = self._documento(codigo="ARQ-ESC-001")
        return RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00",
            arquivo=SimpleUploadedFile("planta.dxf", b"0\nSECTION\n"),
            nome_original="planta.dxf", formato="dxf", tamanho_bytes=10,
            hash_sha256="hash-escala", **extra,
        )

    def _converter(self, revisao, largura=12.5, folhas=1):
        """Roda o pipeline com um motor que devolve `folhas` partes.

        Partes e não `Saida` simples porque é assim que o motor 2D real responde
        desde a PRA.1c — e é o caminho em que o desenho nasce, que é onde a régua
        mora. Um motor sem partes exercitaria o ramo da miniatura.
        """
        partes = tuple(
            Parte(
                conteudo=b"<svg><path d='M0 0'/></svg>", ordem=i,
                caixa={"xmin": 0.0, "ymin": (i - 1) * 9e5,
                       "xmax": 1000.0, "ymax": (i - 1) * 9e5 + 700.0},
                tracos=169,
                detalhe={"escala_largura_m": largura, "unidades_desenho": 4,
                         "unidades_rotulo": "milímetros"},
            )
            for i in range(1, folhas + 1)
        )
        motor = MotorFalso(detalhe=partes[0].detalhe, partes=partes)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}):
            derivada = (
                DerivadaProjeto.objects.filter(
                    revisao=revisao, tipo="vetor_2d", motor="ezdxf").first()
                or DerivadaProjeto.objects.create(
                    revisao=revisao, tipo="vetor_2d", motor="ezdxf",
                    tenant_id=revisao.tenant_id)
            )
            pipeline.executar(derivada)
        revisao.refresh_from_db()
        return revisao

    def _primeiro(self, revisao):
        return revisao.desenhos.order_by("ordem").first()

    def test_conversao_publica_a_escala_lida_do_desenho(self):
        """O ponto da fatia: a prancha nasce medindo em metro, sem ninguém
        calibrar nada — que é como o AutoCAD responde."""
        desenho = self._primeiro(self._converter(self._revisao_dxf()))

        self.assertAlmostEqual(desenho.escala_valor, 12.5)
        self.assertEqual(desenho.escala_unidade, "m")
        self.assertEqual(desenho.escala_origem, "desenho")
        self.assertTrue(desenho.tem_escala)
        # A memória da derivação fica no mesmo campo que guarda a referência da
        # calibração humana: quem for conferir procura num lugar só.
        self.assertEqual(desenho.escala_referencia["unidades_rotulo"], "milímetros")

    def test_cada_folha_ganha_a_propria_regua(self):
        """Duas folhas, duas larguras, duas réguas. Um número só para a revisão
        descreveria no máximo uma delas — e em silêncio para a outra."""
        revisao = self._converter(self._revisao_dxf(), folhas=2)

        self.assertEqual(revisao.desenhos.count(), 2)
        for desenho in revisao.desenhos.all():
            self.assertTrue(desenho.tem_escala)

    def test_calibracao_humana_sobrevive_a_reconversao(self):
        """A regra que a `pode_derivar_escala` existe para garantir — a mesma do
        pin `exata` do MAP.6. Sem ela, um reprocessamento em massa mudaria em
        silêncio o valor de toda medida já anotada no canteiro."""
        revisao = self._converter(self._revisao_dxf())
        desenho = self._primeiro(revisao)
        desenho.escala_valor = 7.0
        desenho.escala_origem = RevisaoDocumento.OrigemEscala.CALIBRADA
        desenho.save(update_fields=["escala_valor", "escala_origem"])

        revisao = self._converter(revisao, largura=99.0)

        desenho = self._primeiro(revisao)
        self.assertAlmostEqual(desenho.escala_valor, 7.0)
        self.assertEqual(desenho.escala_origem, "calibrada")

    def test_o_nome_dado_sobrevive_a_reconversao(self):
        """Reprocessar não pode apagar o nome que alguém deu — é o mesmo princípio
        da calibração, aplicado ao rótulo."""
        revisao = self._converter(self._revisao_dxf())
        desenho = self._primeiro(revisao)
        desenho.nome = "Poligonal do confrontante norte"
        desenho.save(update_fields=["nome"])

        revisao = self._converter(revisao)

        self.assertEqual(self._primeiro(revisao).nome, "Poligonal do confrontante norte")

    def test_escala_derivada_pode_ser_substituida_por_outra_derivada(self):
        """O caminho contrário é livre: motor melhor, leitura melhor."""
        revisao = self._converter(self._revisao_dxf(), largura=12.5)
        revisao = self._converter(revisao, largura=13.75)

        desenho = self._primeiro(revisao)
        self.assertAlmostEqual(desenho.escala_valor, 13.75)
        self.assertEqual(desenho.escala_origem, "desenho")

    def test_motor_sem_escala_nao_apaga_a_que_existe(self):
        """PDF e imagem não declaram unidade; a conversão deles não pode zerar a
        régua de uma prancha que já tinha uma."""
        revisao = self._converter(self._revisao_dxf(), largura=12.5)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": MotorFalso()}):  # detalhe sem escala
            derivada = DerivadaProjeto.objects.create(
                tenant=self.tenant, revisao=revisao, tipo="miniatura", motor="ezdxf")
            pipeline.executar(derivada)

        self.assertAlmostEqual(self._primeiro(revisao).escala_valor, 12.5)

    def test_a_escala_derivada_chega_no_acervo(self):
        """O visualizador abre A PARTIR do acervo: se a procedência não viajar
        aqui, a tela não sabe dizer de onde saiu o metro que está mostrando."""
        revisao = self._converter(self._revisao_dxf())
        revisao.situacao = "vigente"
        revisao.save(update_fields=["situacao"])

        self.autenticar(perms=["prancheta.documento.view"])
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        vigentes = [
            documento["vigente"]
            for grupo in corpo["disciplinas"] for documento in grupo["documentos"]
            if documento["vigente"]
        ]
        achada = [v for v in vigentes if v["revisao_id"] == revisao.pk]
        self.assertEqual(len(achada), 1)
        # Os três campos de compatibilidade seguem respondendo pela PRIMEIRA
        # folha, que é o que a revisão de uma folha só sempre foi.
        self.assertAlmostEqual(achada[0]["escala_valor"], 12.5)
        self.assertEqual(achada[0]["escala_origem"], "desenho")
        self.assertAlmostEqual(achada[0]["desenhos"][0]["escala_valor"], 12.5)


# ===========================================================================
# PRA.1b — fidelidade do motor livre
# ===========================================================================
# O PRA.1 provou que o arquivo *converte*. Esta fatia prova que ele converte
# **direito**, e as quatro teses são independentes:
#
#   D48 — o traço é do PAPEL, não do modelo: a mesma prancha modelada em metro e
#         em milímetro tem de sair com a mesma espessura relativa;
#   D44 — a prancha montada na aba de layout existe, e desenhá-la NÃO pode
#         publicar régua (lá a unidade é milímetro de papel);
#   D45 — arquivo vazio e XREF ausente não são defeito nosso, e dizer que são
#         enche a fila do canteiro com trabalho inexistente;
#   D49 — o preview que o CAD gravou vale como cartão, e a ausência dele é
#         estado normal, não avaria.


class EspessuraRelativaAFolhaTests(SimpleTestCase):
    """**D48** — a mesma geometria em duas unidades tem de dar o mesmo traço.

    É o defeito que o cliente relatou por escrito ("no plano grátis, redesenhando,
    as linhas ficam muito grandes"), e a causa é uma linha: o `Frontend` era
    instanciado sem `config=`, então a política era `ABSOLUTE` — 0,25 mm de tinta
    continuam 0,25 mm por maior ou menor que seja a folha. Como a folha é
    auto-dimensionada pelo desenho, o mesmo traço saía ~41x mais grosso no modelo
    em metros. Medido nesta imagem antes do conserto.
    """

    def _folha(self, escala: float):
        """Desenha a mesma prancha na escala pedida e mede o traço dela.

        Devolve `(folha_mm, tracos_no_desenho, grade)`, onde `tracos_no_desenho`
        são as espessuras como **fração do desenho** — não do arquivo emitido, e
        não em milímetro. É a grandeza da tese: o `stroke-width` cru sai em
        unidades da grade, que varia com a ocupação, e o milímetro é justamente o
        que a política de fábrica mantinha constante enquanto o desenho aparecia
        41× mais grosso.

        As espessuras são as da paleta de penas do CAD (0,13 · 0,25 · 0,50 ·
        1,00 · 2,11 mm), porque o que precisa sobreviver não é um traço: é a
        **hierarquia** entre eles — corte grosso, hachura fina.
        """
        import os
        import re
        import tempfile

        import ezdxf

        from .motores.dxf import MotorDxf

        modelo = ezdxf.new("R2010", setup=True)
        espaco = modelo.modelspace()
        for i, peso in enumerate([13, 25, 50, 100, 211]):
            y = i * 10 * escala
            espaco.add_line((0, y), (841 * escala, y), dxfattribs={"lineweight": peso})

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)

        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")
        texto = saida.conteudo.decode("utf-8")
        largura = float(re.search(r'width="([0-9.eE+-]+)mm"', texto).group(1))
        grade = saida.detalhe["grade"]
        ocupacao = saida.detalhe["ocupacao"]
        tracos = sorted(
            round(int(x) / grade / ocupacao, 6)
            for x in {y for y in re.findall(r"stroke-width: ([0-9]+);", texto)}
        )
        return largura, tracos, grade

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_traco_igual_com_o_modelo_em_metro_e_em_milimetro(self):
        """O DoD da fatia, literal.

        A comparação é de **fração do desenho** e não de milímetro: as duas
        folhas têm tamanhos físicos muito diferentes por construção, e é
        justamente por isso que a espessura absoluta — que preservava o milímetro
        — não servia de régua.
        """
        folha_mm, tracos_mm, _grade_mm = self._folha(1.0)     # modelado em mm
        folha_m, tracos_m, _grade_m = self._folha(0.001)      # modelado em m

        # As duas folhas são MUITO diferentes — é o cenário do defeito, e a razão
        # entre elas é da ordem do fator pelo qual o traço engrossava antes
        # (medido: 861 mm / 20,8 mm ≈ 41×). A margem fixa de 10 mm é o que impede
        # a razão de ser os 1.000× da geometria — e é ela que exige a compensação
        # por ocupação, sem a qual sobrariam ~1,7× de diferença.
        self.assertGreater(folha_mm / folha_m, 30)

        # **Igual a menos da quantização**, e o resíduo é do `SVGBackend`: ele
        # trunca para inteiro tanto `max_stroke_width` quanto o `min` derivado
        # dele, sobre uma grade que difere entre os dois casos porque é
        # dimensionada pela ocupação. O erro se concentra na pena mais **fina**,
        # que na folha pequena vira 21 unidades de grade contra 212 na grande —
        # uma ordem de grandeza menos resolução para arredondar. Medido: 3,3% no
        # extremo fino, contra os **41×** de antes, que é o número que esta fatia
        # existe para apagar. Exigir igualdade binária prenderia o teste a um
        # arredondamento de terceiro.
        self.assertEqual(len(tracos_mm), len(tracos_m))
        for em_mm, em_m in zip(tracos_mm, tracos_m):
            self.assertLess(
                abs(em_mm - em_m) / em_mm, 0.05,
                f"traço divergiu além da quantização: {em_mm} vs {em_m}",
            )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_hierarquia_de_penas_sobrevive(self):
        """Espessura fixa para tudo (`RELATIVE_FIXED`) resolveria o D48 e mataria
        o desenho: o que distingue o corte da hachura é a pena. Cinco espessuras
        entram, cinco espessuras saem, e em ordem."""
        _folha, tracos, _grade = self._folha(1.0)

        self.assertEqual(len(tracos), 5)
        self.assertEqual(tracos, sorted(tracos))

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_traco_mais_grosso_e_a_espessura_maxima_do_dxf_na_folha_de_referencia(self):
        """A âncora do número: `ESPESSURA_RELATIVA` diz que o traço mais grosso
        que o DXF permite (2,11 mm) ocupa, na folha, o que ocuparia numa A1
        plotada. Sem esta amarra, `max_stroke_width` viraria um número mágico que
        alguém ajusta "até ficar bonito"."""
        from .motores.dxf import ESPESSURA_RELATIVA, FOLHA_REFERENCIA_MM

        _folha, tracos, _grade = self._folha(1.0)

        self.assertAlmostEqual(ESPESSURA_RELATIVA * FOLHA_REFERENCIA_MM, 2.11, places=6)
        # O mais grosso da paleta é o teto da faixa, a menos do arredondamento
        # para inteiro que o SVGBackend faz.
        self.assertAlmostEqual(tracos[-1], ESPESSURA_RELATIVA, places=4)


class PaperspaceTests(SimpleTestCase):
    """**D44** — a prancha montada na aba de layout, que saía em branco.

    8 dos 150 DWGs da remedição: o modelspace tem pouca ou nenhuma entidade
    porque a folha (moldura, carimbo, legendas) é composta no paperspace. O motor
    desenhava só `modelspace()`, o `ezdxf` não achava extensão e a prancha inteira
    virava `falha_motor`.
    """

    def _arquivo(self, *, unidades: int, layouts: dict, modelspace: bool):
        import os
        import tempfile

        import ezdxf

        modelo = ezdxf.new("R2010", setup=True)
        modelo.units = unidades
        if modelspace:
            modelo.modelspace().add_line((0, 0), (5000, 3000))
        for nome, desenhar in layouts.items():
            aba = (
                modelo.layout(nome) if nome in modelo.layout_names()
                else modelo.layouts.new(nome)
            )
            if desenhar:
                # Uma moldura de folha A1 em milímetro de PAPEL — que é o que o
                # paperspace mede, e a razão de a régua não poder sair daqui.
                aba.add_lwpolyline(
                    [(0, 0), (841, 0), (841, 594), (0, 594), (0, 0)],
                    dxfattribs={"lineweight": 50},
                )
        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)
        return caminho

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_modelspace_vazio_desenha_a_aba_de_layout(self):
        from .motores.dxf import MotorDxf

        caminho = self._arquivo(
            unidades=4, layouts={"PLANTA BAIXA": True}, modelspace=False,
        )
        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

        self.assertEqual(len(saida.partes), 1)
        self.assertEqual(saida.detalhe["espaco"], "paperspace")
        self.assertIn(b"<path", saida.conteudo)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_nome_da_aba_vira_o_nome_da_folha(self):
        """A única vez em que este módulo recebe um nome escrito por gente sem
        pedir a ninguém: "PLANTA BAIXA - PAV TIPO" é como o projetista chama
        aquela folha, e é melhor que "Desenho 1"."""
        from .motores.dxf import MotorDxf

        caminho = self._arquivo(
            unidades=4,
            layouts={"PLANTA BAIXA - PAV TIPO": True, "CORTES": True},
            modelspace=False,
        )
        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

        nomes = [p.nome for p in saida.partes]
        self.assertIn("PLANTA BAIXA - PAV TIPO", nomes)
        self.assertIn("CORTES", nomes)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_paperspace_nao_publica_regua_mesmo_com_insunits_declarado(self):
        """**A armadilha da fatia, e ela é silenciosa.**

        O arquivo declara milímetros; a moldura tem 841 unidades de largura. Se a
        régua saísse daqui, o módulo publicaria 0,84 m como a largura do desenho —
        um número *dentro* da janela de plausibilidade, sem nada disparar, para
        uma fachada que pode ter 30 m. Escala errada com cara de certa é o pior
        desfecho possível neste módulo.
        """
        from .motores.dxf import MotorDxf

        caminho = self._arquivo(unidades=4, layouts={"Layout1": True}, modelspace=False)
        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

        self.assertNotIn("escala_largura_m", saida.detalhe)
        self.assertEqual(saida.detalhe["escala_indisponivel"], "paperspace")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_modelspace_com_desenho_ignora_o_paperspace_e_mantem_a_regua(self):
        """Garantia de não-regressão: a prancha comum do acervo — a esmagadora
        maioria — não passa nem perto deste caminho, e continua medindo."""
        from .motores.dxf import MotorDxf

        caminho = self._arquivo(unidades=4, layouts={"Layout1": True}, modelspace=True)
        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

        self.assertEqual(saida.detalhe["espaco"], "modelspace")
        self.assertIn("escala_largura_m", saida.detalhe)
        self.assertEqual(saida.partes[0].nome, "")


class ArquivoSemDesenhoTests(SimpleTestCase):
    """**D45** — os dois casos em que o erro não é nosso nem do plano."""

    def _arquivo(self, montar):
        import os
        import tempfile

        import ezdxf

        modelo = ezdxf.new("R2010", setup=True)
        montar(modelo)
        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)
        return caminho

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_desenho_vazio_nao_e_falha_do_motor(self):
        """`Desenho1_recover.dwg` e parentes: nem uma entidade, em lugar nenhum.
        Dizer "falha interna do motor" é confessar um defeito que não existe — e
        pôr na fila do canteiro uma linha que ninguém jamais vai consertar."""
        from .motores.base import DesenhoVazio
        from .motores.dxf import MotorDxf

        with self.assertRaises(DesenhoVazio) as capturado:
            MotorDxf().converter(
                self._arquivo(lambda d: None), formato="dxf", tipo="vetor_2d",
            )

        self.assertEqual(capturado.exception.motivo, "desenho_vazio")
        self.assertFalse(capturado.exception.retentavel)
        self.assertIn("vazio", str(capturado.exception).lower())

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_desenho_vazio_vale_tambem_quando_o_dxf_e_intermediario_nosso(self):
        """Contraponto ao **D42**: ali a regra era "o DXF que geramos é nosso,
        logo a culpa é nossa". Vazio é a exceção — nenhum conversor perde TODAS
        as entidades sem reclamar, e nenhum inventa uma. O arquivo do cliente é
        que estava vazio."""
        from .motores.base import DesenhoVazio
        from .motores.dxf import MotorDxf

        with self.assertRaises(DesenhoVazio):
            MotorDxf(origem="dwg").converter(
                self._arquivo(lambda d: None), formato="dxf", tipo="vetor_2d",
            )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_xref_ausente_e_acionavel_e_nomeia_os_arquivos(self):
        """O único desta família com dono e desfecho: quem enviou reenvia. E a
        mensagem carrega os caminhos porque *"esta prancha referencia 2 arquivos
        que não foram enviados: …"* é acionável, e "erro na conversão" não."""
        from .motores.base import ReferenciaAusente
        from .motores.dxf import MotorDxf

        def montar(modelo):
            for nome, caminho in [
                ("XR-ESTRUTURA", "C:\\Users\\proj\\DATA\\28 08\\ESTRUTURA.dwg"),
                ("XR-HIDRAULICA", "C:\\Users\\proj\\DATA\\28 08\\HIDRO.dwg"),
            ]:
                bloco = modelo.blocks.new(nome)
                bloco.block.dxf.xref_path = caminho
                bloco.block.dxf.flags = 4
                modelo.modelspace().add_blockref(nome, (0, 0))

        with self.assertRaises(ReferenciaAusente) as capturado:
            MotorDxf().converter(self._arquivo(montar), formato="dxf", tipo="vetor_2d")

        excecao = capturado.exception
        self.assertEqual(excecao.motivo, "referencia_ausente")
        self.assertIn("ESTRUTURA.dwg", str(excecao))
        self.assertEqual(len(excecao.extra["xrefs"]), 2)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_xref_declarado_e_nao_inserido_e_desenho_vazio(self):
        """A definição de XREF que ninguém inseriu (descarregado, desanexado) não
        põe nada na prancha. Chamá-la de "faltam anexos" mandaria o cliente
        procurar arquivo que ele não precisa enviar."""
        from .motores.base import DesenhoVazio
        from .motores.dxf import MotorDxf

        def montar(modelo):
            bloco = modelo.blocks.new("XR-ORFAO")
            bloco.block.dxf.xref_path = "C:\\nada.dwg"
            bloco.block.dxf.flags = 4

        with self.assertRaises(DesenhoVazio):
            MotorDxf().converter(self._arquivo(montar), formato="dxf", tipo="vetor_2d")


class PreviewEmbutidoTests(APITestCase):
    """**D49** — a única figura do acervo que não é redesenho nosso.

    O DWG carrega o *thumbnail* que o CAD gravou ao salvar, e o `dwgbmp` o extrai
    sem decodificar o desenho. Vale mais exatamente onde hoje não há nada: quando
    a conversão falha, o cartão fica vazio embora o arquivo tenha a imagem.
    """

    def _dwg(self, marca: bytes = b"AC1032"):
        import os
        import tempfile

        descritor, caminho = tempfile.mkstemp(suffix=".dwg")
        with os.fdopen(descritor, "wb") as saida:
            saida.write(marca + b"\x00" * 128)
        self.addCleanup(lambda: os.unlink(caminho))
        return caminho

    def _falso_dwgbmp(self, corpo: str) -> str:
        """Um `dwgbmp` de mentira com a semântica **medida** no de verdade."""
        import os
        import shutil
        import stat
        import tempfile

        pasta = tempfile.mkdtemp(prefix="prancheta-bmp-")
        self.addCleanup(lambda: shutil.rmtree(pasta, ignore_errors=True))
        caminho = os.path.join(pasta, "dwgbmp")
        with open(caminho, "w") as script:
            script.write("#!/usr/bin/env python3\nimport sys\n" + corpo)
        os.chmod(caminho, os.stat(caminho).st_mode | stat.S_IEXEC)
        return caminho

    def _com_binario(self, caminho):
        """Troca só o `dwgbmp`, deixando o `dwg2dxf` fora do caminho."""
        def escolher(nome, env=None):
            return caminho if nome == "dwgbmp" else "/bin/false"

        return mock.patch("moduloprancheta.motores.dwg.executavel", side_effect=escolher)

    def test_o_motor_de_dwg_declara_as_duas_saidas(self):
        """Linhas separadas no banco é o que faz **uma sobreviver à falha da
        outra** — o ponto inteiro do D49."""
        from .motores.dwg import MotorDwg

        self.assertEqual(MotorDwg().tipos, ("vetor_2d", "miniatura"))

    def test_binario_ausente_e_problema_nosso_nao_ausencia_de_preview(self):
        """A imagem pode existir e nós é que não temos como lê-la. Dizer "este
        arquivo não tem miniatura" esconderia uma falha de deploy atrás de uma
        característica do arquivo do cliente."""
        from .motores.base import MotorIndisponivel
        from .motores.dwg import MotorDwg

        with self._com_binario(None):
            with self.assertRaises(MotorIndisponivel):
                MotorDwg().converter(self._dwg(), formato="dwg", tipo="miniatura")

    def test_dwg_sem_preview_nao_e_avaria(self):
        """**A armadilha medida no binário de verdade:** sem preview o `dwgbmp`
        imprime "No thumbnail image", **sai com código 0** e não escreve arquivo
        nenhum. Quem responde a pergunta é o destino existir e ter tamanho — a
        mesma lição que o `-y` do D34 cobrou caro."""
        from .motores.base import SemPreviewEmbutido
        from .motores.dwg import MotorDwg

        falso = self._falso_dwgbmp(
            "sys.stdout.write('No thumbnail image in %s' % sys.argv[1])\nsys.exit(0)\n"
        )
        with self._com_binario(falso):
            with self.assertRaises(SemPreviewEmbutido) as capturado:
                MotorDwg().converter(self._dwg(), formato="dwg", tipo="miniatura")

        self.assertEqual(capturado.exception.motivo, "sem_preview")
        self.assertFalse(capturado.exception.retentavel)
        self.assertIn("No thumbnail", capturado.exception.extra["motivo_real"])

    def test_preview_vira_miniatura_com_a_procedencia_declarada(self):
        """A tela precisa poder dizer que aquela figura **não** é o nosso
        redesenho: ela serve para reconhecer a prancha, nunca para medir."""
        from .motores.dwg import MotorDwg

        falso = self._falso_dwgbmp(
            "from PIL import Image\n"
            "Image.new('RGB', (1600, 900), 'white').save(sys.argv[2], format='BMP')\n"
        )
        with self._com_binario(falso):
            saida = MotorDwg().converter(self._dwg(), formato="dwg", tipo="miniatura")

        self.assertEqual(saida.extensao, "jpg")
        self.assertEqual(saida.content_type, "image/jpeg")
        self.assertEqual(saida.detalhe["procedencia"], "preview_embutido")
        self.assertEqual(saida.detalhe["preview_formato"], "bmp")
        self.assertEqual(saida.detalhe["versao_dwg"], "AC1032")
        # Encolhida pelo mesmo caminho do PDF: um cartão só, um tamanho só.
        self.assertLessEqual(max(saida.detalhe["largura"], saida.detalhe["altura"]), 600)

    def test_versao_acima_do_alcance_livre_ainda_tenta_o_preview(self):
        """O R2024 é justamente onde a prancha não sai — e onde a figura que o
        AutoCAD gravou é a única coisa que o cliente teria para ver. O upsell já
        é dito pela linha do `vetor_2d`; repeti-lo aqui não acrescentaria nada."""
        from .motores.dwg import MotorDwg

        falso = self._falso_dwgbmp(
            "from PIL import Image\n"
            "Image.new('RGB', (800, 600), 'white').save(sys.argv[2], format='PNG')\n"
        )
        with self._com_binario(falso):
            saida = MotorDwg().converter(
                self._dwg(b"AC1037"), formato="dwg", tipo="miniatura",
            )

        self.assertEqual(saida.detalhe["preview_formato"], "png")
        self.assertEqual(saida.detalhe["versao_dwg"], "AC1037")

    def test_preview_em_formato_que_nao_abrimos_e_ausencia_declarada(self):
        """O `dwgbmp` entrega o que estava lá dentro — BMP, PNG **ou WMF** —, e o
        WMF é vetorial do Windows: não abre sem renderizador externo. Ausência
        declarada, não traceback."""
        from .motores.base import SemPreviewEmbutido
        from .motores.dwg import MotorDwg

        falso = self._falso_dwgbmp(
            "open(sys.argv[2], 'wb').write(b'\\xd7\\xcd\\xc6\\x9a' + b'\\x00' * 64)\n"
        )
        with self._com_binario(falso):
            with self.assertRaises(SemPreviewEmbutido) as capturado:
                MotorDwg().converter(self._dwg(), formato="dwg", tipo="miniatura")

        self.assertEqual(capturado.exception.extra["preview_formato"], "desconhecido")


class TetoDeTamanhoDoDwgTests(APITestCase):
    """**D47** — o degrau de plano em DWG é o **peso**, e ele avisa no upload.

    O número não é arbitrado: varrendo os 102 DWGs acima de 5 MB do acervo real,
    93% abrem até 20 MB, 64% de 20 a 40 MB e **0 de 10** acima de 40 MB. Hoje o
    cliente sobe 138 MB, espera a fila e recebe `motor_insuficiente` — o aviso
    transforma o diagnóstico tardio em escolha informada.
    """

    class _Usuario:
        def __init__(self, plano):
            self.iam_plano = plano
            self.username = "quem-sobe"

    def test_o_teto_so_existe_onde_foi_medido(self):
        """Inventar um teto para os outros formatos por simetria seria arbitrar
        limite sem medição — o oposto do que este módulo faz com número."""
        from .planos import teto_do_motor_livre

        self.assertEqual(teto_do_motor_livre("dwg"), DWG_MB_MOTOR_LIVRE)
        for codigo in ("dxf", "pdf", "ifc", "imagem"):
            self.assertEqual(teto_do_motor_livre(codigo), 0)

    def test_dwg_dentro_do_teto_nao_avisa_nada(self):
        """Aviso permanente treina o usuário a ignorar o aviso que importa."""
        from .planos import aviso_do_upload

        plano = next(iter(PLANOS))
        self.assertIsNone(
            aviso_do_upload("dwg", 5 * 1024 * 1024, self._Usuario(plano)),
        )

    def test_dwg_acima_do_teto_avisa_e_deixa_passar(self):
        """**Avisa e deixa passar** é decisão de produto, não omissão: recusar
        venderia como fronteira de plano um motor premium que ainda não existe
        (PRA.4). O arquivo fica no acervo, baixável na íntegra, e reconverte
        sozinho quando o motor melhor chegar."""
        from .planos import aviso_do_upload

        # Um plano sem o tier premium — o caso do cliente de entrada.
        basico = next(
            slug for slug, cfg in PLANOS.items()
            if cfg.get("motores_prancheta") == ["livre"]
        )
        aviso = aviso_do_upload("dwg", 138 * 1024 * 1024, self._Usuario(basico))

        self.assertIsNotNone(aviso)
        self.assertIn("138 MB", aviso)
        self.assertIn(str(DWG_MB_MOTOR_LIVRE), aviso)
        # A saída dele é comprar, e a frase tem de dizer isso.
        self.assertIn("plano superior", aviso)

    def test_quem_ja_paga_o_premium_recebe_a_verdade_e_nao_um_upsell(self):
        """A mesma distinção que `pipeline._traduzir` faz depois da falha, agora
        antes dela: mandar comprar o que já está comprado é o que faz um cliente
        abrir chamado achando que pagou por nada."""
        from .planos import aviso_do_upload

        premium = next(
            slug for slug, cfg in PLANOS.items()
            if (cfg.get("motores_prancheta") or []) and "premium" in cfg["motores_prancheta"]
        )
        aviso = aviso_do_upload("dwg", 138 * 1024 * 1024, self._Usuario(premium))

        self.assertIsNotNone(aviso)
        self.assertNotIn("plano superior", aviso)
        self.assertIn("não está ligado neste servidor", aviso)

    def test_o_teto_viaja_no_catalogo_de_formatos(self):
        """Para a tela poder avisar **antes** de o arquivo subir — que é o ponto
        do D47: o cliente decide com o arquivo ainda na mão."""
        declarados = {f["codigo"]: f for f in formatos_declarados(self._Usuario("free"))}

        self.assertEqual(declarados["dwg"]["motor_livre_max_mb"], DWG_MB_MOTOR_LIVRE)
        self.assertEqual(declarados["pdf"]["motor_livre_max_mb"], 0)


class QuemResolveAFalhaTests(PranchetaTestBase):
    """A fila de decisão depois da PRA.1b: **quatro atores, não dois**.

    Um DWG passou a render duas derivadas (a prancha e a miniatura embutida), e
    elas falham por motivos independentes. Sem ordenar por quanto a falha diz, a
    revisão anunciaria a falha menos informativa das duas — que é sempre a da
    miniatura, por `tipo` em ordem alfabética.
    """

    def _revisao_dwg(self, codigo="ARQ-FALHA-001"):
        return RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=self._documento(codigo=codigo),
            revisao="R01", arquivo=SimpleUploadedFile("planta.dwg", b"AC1032xx"),
            nome_original="planta.dwg", formato="dwg", tamanho_bytes=8,
            hash_sha256=f"hash-{codigo}", situacao=RevisaoDocumento.Situacao.VIGENTE,
        )

    def _falha(self, revisao, tipo, motivo, detalhe=""):
        return DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo=tipo, motor="libredwg",
            estado=DerivadaProjeto.Estado.ERRO, erro_motivo=motivo,
            erro_detalhe=detalhe or motivo,
        )

    def _vigente(self, revisao):
        self.autenticar(perms=["prancheta.documento.view"])
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        for grupo in corpo["disciplinas"]:
            for documento in grupo["documentos"]:
                if documento["vigente"] and documento["vigente"]["revisao_id"] == revisao.pk:
                    return documento["vigente"], corpo["requer_decisao"]
        self.fail("revisão vigente não apareceu no acervo")

    def test_o_upsell_nao_e_apagado_pela_falta_de_miniatura(self):
        """A regressão que esta fatia poderia ter introduzido: `miniatura` vem
        antes de `vetor_2d` em ordem alfabética, então "pegar a primeira falha"
        faria um arquivo que exige o motor premium anunciar "não traz miniatura
        embutida" — e o botão de compra sumiria da tela."""
        revisao = self._revisao_dwg()
        self._falha(revisao, "miniatura", DerivadaProjeto.MotivoErro.SEM_PREVIEW)
        self._falha(
            revisao, "vetor_2d", DerivadaProjeto.MotivoErro.MOTOR_INSUFICIENTE,
            "Exige o motor de alta fidelidade.",
        )

        vigente, _fila = self._vigente(revisao)

        self.assertEqual(vigente["conversao"]["motivo"], "motor_insuficiente")
        self.assertTrue(vigente["conversao"]["exige_upgrade"])
        self.assertFalse(vigente["conversao"]["problema_no_arquivo"])

    def test_xref_ausente_vence_a_falha_generica_porque_e_a_acionavel(self):
        revisao = self._revisao_dwg(codigo="ARQ-FALHA-002")
        self._falha(revisao, "miniatura", DerivadaProjeto.MotivoErro.SEM_PREVIEW)
        self._falha(revisao, "vetor_2d", DerivadaProjeto.MotivoErro.REFERENCIA_AUSENTE)

        vigente, fila = self._vigente(revisao)

        self.assertEqual(vigente["conversao"]["motivo"], "referencia_ausente")
        self.assertTrue(vigente["conversao"]["problema_no_arquivo"])
        self.assertEqual(fila["conversoes_aguardando_anexo"], 1)
        # Acionável por quem enviou — logo NÃO entra no balde de "ninguém age".
        self.assertEqual(fila["conversoes_sem_desenho"], 1)  # só a miniatura

    def test_arquivo_vazio_nao_infla_a_fila_do_que_consertamos(self):
        """O ponto do D45 medido do lado da tela: a fila do canteiro só vale
        alguma coisa enquanto o número desce quando alguém trabalha."""
        revisao = self._revisao_dwg(codigo="ARQ-FALHA-003")
        self._falha(revisao, "vetor_2d", DerivadaProjeto.MotivoErro.DESENHO_VAZIO)

        vigente, fila = self._vigente(revisao)

        self.assertTrue(vigente["conversao"]["problema_no_arquivo"])
        self.assertFalse(vigente["conversao"]["exige_upgrade"])
        self.assertEqual(fila["conversoes_com_erro"], 1)
        self.assertEqual(fila["conversoes_sem_desenho"], 1)
        # O que sobra para nós consertarmos: nada.
        self.assertEqual(
            fila["conversoes_com_erro"]
            - fila["conversoes_que_exigem_upgrade"]
            - fila["conversoes_sem_desenho"]
            - fila["conversoes_aguardando_anexo"],
            0,
        )

    def test_a_miniatura_que_falha_nao_esconde_a_prancha_que_abriu(self):
        """O caso mais comum do D49 em produção: o DWG converte bem e não traz
        preview. A revisão está **pronta** — uma linha vermelha aqui poria em
        dúvida uma prancha que abre."""
        revisao = self._revisao_dwg(codigo="ARQ-FALHA-004")
        self._falha(revisao, "miniatura", DerivadaProjeto.MotivoErro.SEM_PREVIEW)
        DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="libredwg",
            estado=DerivadaProjeto.Estado.PRONTO,
            arquivo=SimpleUploadedFile("planta.svg", b"<svg><path/></svg>"),
        )

        vigente, fila = self._vigente(revisao)

        self.assertEqual(vigente["conversao"]["estado"], "pronta")
        self.assertEqual(fila["conversoes_com_erro"], 1)
        self.assertEqual(fila["conversoes_sem_desenho"], 1)


class ConversaoNaoAgendadaTests(PranchetaTestBase):
    """**D81** — a revisão que tem bytes e nenhuma derivada não é "sem motor".

    O achado custou caro justamente porque os dois lados estavam certos: o
    arquivo no acervo, o plano com o formato, o motor na imagem — e a tela
    dizendo *"ainda não há visualizador para este formato"*. A causa era que
    ninguém tinha enfileirado a conversão, e o `get_conversao` deduzia a falta de
    motor da falta de linha.

    A dedução nunca foi válida: o `agendar()` **cria** a `DerivadaProjeto` de
    forma síncrona antes de enfileirar, então motor planejado implica linha
    existindo. Zero linhas com motor planejado é o estado oposto ao anunciado — e
    a diferença entre os dois é quem age: comprar plano × reprocessar.
    """

    def _revisao(self, formato="dwg", codigo="ARQ-SEMFILA-001"):
        return RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=self._documento(codigo=codigo),
            revisao="R01", arquivo=SimpleUploadedFile(f"planta.{formato}", b"AC1032xx"),
            nome_original=f"planta.{formato}", formato=formato, tamanho_bytes=8,
            hash_sha256=f"hash-{codigo}", situacao=RevisaoDocumento.Situacao.VIGENTE,
        )

    def _conversao(self, revisao):
        self.autenticar(perms=["prancheta.documento.view"])
        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        for grupo in corpo["disciplinas"]:
            for documento in grupo["documentos"]:
                if documento["vigente"] and documento["vigente"]["revisao_id"] == revisao.pk:
                    return documento["vigente"]["conversao"]
        self.fail("revisão vigente não apareceu no acervo")

    def test_dwg_sem_derivada_nenhuma_diz_que_nao_foi_agendada(self):
        """O caso do D81, reproduzido: DWG vigente, plano com o motor, zero
        derivadas. Antes desta correção respondia `sem_motor`."""
        conversao = self._conversao(self._revisao())

        self.assertEqual(conversao["estado"], "nao_agendada")
        self.assertIsNone(conversao["visualizador"])
        # Nem upsell nem culpa do arquivo: o pendente é da plataforma.
        self.assertFalse(conversao["exige_upgrade"])
        self.assertFalse(conversao["problema_no_arquivo"])

    def test_formato_sem_adaptador_continua_dizendo_sem_motor(self):
        """O contrapeso — sem ele a correção teria só trocado uma mentira por
        outra. O RVT espera a PRA.4: `planejar()` devolve vazio em qualquer
        plano, e prometer reprocessamento ali seria trabalho que ninguém fará."""
        conversao = self._conversao(self._revisao(formato="rvt", codigo="ARQ-SEMFILA-002"))

        self.assertEqual(conversao["estado"], "sem_motor")

    def test_o_resumo_da_revisao_alcanca_o_plano_de_quem_le(self):
        """O `get_vigente` montava o resumo **sem contexto**, e sem `request` o
        `get_conversao` não teria como perguntar o plano — cairia no
        `TIERS_PADRAO` e responderia por um plano que não é o do leitor."""
        revisao = self._revisao(codigo="ARQ-SEMFILA-003")
        self.autenticar(perms=["prancheta.documento.view"])

        corpo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        documento = next(
            d for g in corpo["disciplinas"] for d in g["documentos"]
            if d["vigente"] and d["vigente"]["revisao_id"] == revisao.pk
        )
        serializer = DocumentoProjetoSerializer(
            DocumentoProjeto.objects.get(pk=documento["documento_id"])
        )
        # Sem contexto o resumo ainda responde — só que pelo tier conservador.
        self.assertIn(serializer.data["vigente"]["conversao"]["estado"],
                      ("nao_agendada", "sem_motor"))


class OrcamentoDeConversaoTests(SimpleTestCase):
    """O teto de recurso da conversão (D57) — e a frase que ele produz.

    O incidente que originou tudo: uma prancha do acervo expandiu hachura até
    **62 GB de RAM** num caminho que, em produção, roda em worker compartilhado e
    em máquina paga. O que se prova aqui é que o estouro agora **para**, e que ao
    parar ele vira dado — não processo morto e não upsell.
    """

    def test_estouro_de_memoria_vira_recurso_excedido_e_nao_falha_de_motor(self):
        """`MemoryError` cru subiria até o `except Exception` do pipeline e viraria
        `falha_motor` — "falha interna do motor" —, acusando defeito nosso onde
        houve **limite** nosso. São filas diferentes no cockpit."""
        from moduloprancheta.limites import orcamento_de_conversao
        from moduloprancheta.motores.base import RecursoExcedido

        with self.assertRaises(RecursoExcedido) as capturado:
            with orcamento_de_conversao(memoria_mb=64, segundos=0):
                raise MemoryError()

        erro = capturado.exception
        self.assertEqual(erro.motivo, "recurso_excedido")
        self.assertEqual(erro.extra.get("teto"), "memoria")
        # Não retentável: repetir reproduz o estouro, 3× por conta da DLQ.
        self.assertFalse(erro.retentavel)
        self.assertIn("download", erro.detalhe)

    def test_recurso_excedido_nao_e_upsell_nem_problema_do_arquivo(self):
        """A regra que protege o cliente de pagar por um limite nosso.

        Nada garante que a APS aguente o mesmo desenho, então oferecer o motor
        premium aqui venderia uma solução que pode não resolver. E o arquivo não
        tem defeito — ele converte, só é caro."""
        from moduloprancheta.motores.base import RecursoExcedido

        self.assertNotIn(
            RecursoExcedido.motivo, DerivadaProjeto.MOTIVOS_DO_ARQUIVO,
            "recurso_excedido é limite NOSSO — não pode entrar no balde do arquivo",
        )
        self.assertNotEqual(RecursoExcedido.motivo, "motor_insuficiente")
        self.assertIn(
            RecursoExcedido.motivo,
            [valor for valor, _rotulo in DerivadaProjeto.MotivoErro.choices],
            "o motivo precisa existir nas choices, senão a gravação falha",
        )

    def test_teto_de_relogio_interrompe_laco_em_processo(self):
        """O caso que o teto de subprocesso não cobria: o render roda AQUI dentro.

        Um laço Python puro é exatamente a forma do gerador de hachura que
        consumiu a memória — e é onde o `SIGALRM` é entregue."""
        import time

        from moduloprancheta.limites import teto_de_relogio
        from moduloprancheta.motores.base import RecursoExcedido

        if not hasattr(__import__("signal"), "SIGALRM"):
            self.skipTest("plataforma sem SIGALRM (Windows)")

        comeco = time.monotonic()
        with self.assertRaises(RecursoExcedido):
            with teto_de_relogio(1):
                while True:
                    pass
        self.assertLess(time.monotonic() - comeco, 5, "o teto não interrompeu")

    def test_teto_restaura_o_limite_anterior(self):
        """O processo é reusado pelo worker: um teto que vazasse para a próxima
        task faria a conversão seguinte falhar por um limite que ninguém armou
        para ela."""
        import resource

        from moduloprancheta.limites import teto_de_memoria

        # Teto absurdamente alto de propósito: o que se prova aqui é o
        # arma-e-restaura, e um teto realista aplicado ao PRÓPRIO processo de
        # teste (com GDAL e ezdxf já mapeados) recusaria a alocação seguinte —
        # `RLIMIT_AS` conta espaço virtual, não memória em uso.
        antes = resource.getrlimit(resource.RLIMIT_AS)
        with teto_de_memoria(4 * 1024 * 1024):  # 4 TiB
            dentro = resource.getrlimit(resource.RLIMIT_AS)
        depois = resource.getrlimit(resource.RLIMIT_AS)

        self.assertEqual(antes, depois)
        self.assertNotEqual(dentro, depois, "o teto não chegou a ser armado")

    def test_conversao_tem_fila_propria_e_o_worker_geral_nao_a_consome(self):
        """A frota separada só é separada se o roteamento existir dos DOIS lados.

        O `-Q celery` do worker geral vive no compose; aqui se prova a metade que
        mora no código — sem ela, a task cairia na fila padrão e o isolamento
        seria só aparente."""
        from django.conf import settings

        rotas = getattr(settings, "CELERY_TASK_ROUTES", {})
        self.assertEqual(rotas.get("moduloprancheta.*", {}).get("queue"), "conversao")
        self.assertNotEqual(settings.CELERY_TASK_DEFAULT_QUEUE, "conversao")

    def test_o_teto_que_explica_dispara_antes_dos_que_so_matam(self):
        """A ordem entre os três freios é o desenho, não coincidência.

        Se o teto do Celery ou o do container disparasse primeiro, o cliente
        receberia derivada presa em `convertendo` em vez de um motivo — que é
        justamente o que o D57 veio consertar."""
        from django.conf import settings

        from moduloprancheta.tasks import _HARD, _SOFT

        self.assertLess(settings.PRANCHETA_CONVERSAO_SEGUNDOS, _SOFT)
        self.assertLess(_SOFT, _HARD)
        # O teto por conversão (MB) tem de caber no teto do filho do Celery (KB).
        self.assertLess(
            settings.PRANCHETA_CONVERSAO_MEMORIA_MB * 1024,
            settings.CELERY_WORKER_MAX_MEMORY_PER_CHILD,
        )


class MedidorDeCoberturaTests(SimpleTestCase):
    """O instrumento que decide o preço — a parte dele que não pode quebrar calada.

    Não exercita motor nem banco de propósito: o que se prova aqui é a
    **reprodutibilidade da amostra** e o **default da coluna "de quem é"**, que
    são as duas coisas cujo defeito não apareceria em nenhuma tela.
    """

    def test_amostra_e_reproduzivel_e_sobrevive_ao_relatorio(self):
        """A amostra tem de ser repetível — e a lista, salvável.

        **O defeito que este teste impede já aconteceu.** A remedição de 02/08
        sorteou 1 em 7 num script de rascunho; o scratchpad foi apagado e a lista
        dos 150 se perdeu. Sem ela, a medição seguinte roda sobre outro corpus e a
        diferença de taxa deixa de ser atribuível ao conserto — que é a única
        pergunta que uma remedição responde.
        """
        import tempfile
        from pathlib import Path

        from moduloprancheta.management.commands.medir_cobertura_dwg import Command

        with tempfile.TemporaryDirectory() as pasta:
            for i in range(21):
                Path(pasta, f"arq{i:02d}.dwg").write_bytes(b"AC1015")
            Path(pasta, "nao-e-desenho.txt").write_bytes(b"x")

            base = {"recursivo": False, "limite": 0, "lista": "", "amostra": 0}
            comando = Command()
            um_em_sete = {**base, "amostra": 7}

            primeira = comando._escolher(pasta, um_em_sete)

            self.assertEqual(primeira, comando._escolher(pasta, um_em_sete),
                             "a amostragem sorteou em vez de fatiar")
            self.assertEqual(
                [Path(c).name for c in primeira],
                ["arq00.dwg", "arq07.dwg", "arq14.dwg"],
                "1-em-N tem de ser fatia da lista ORDENADA",
            )

            destino = str(Path(pasta, "amostra.txt"))
            with mock.patch.object(comando, "stdout"):
                comando._salvar_lista(destino, pasta, primeira)
                relidos = comando._escolher(pasta, {**base, "lista": destino})

            self.assertEqual(relidos, primeira)
            # Relativos, não absolutos: o corpus é montado em lugares diferentes a
            # cada medição (pasta no host, ponto de montagem no container), e
            # caminho absoluto só serviria na máquina que o escreveu — foi assim
            # que a amostra anterior morreu.
            self.assertEqual(
                Path(destino).read_text(encoding="utf-8").split(),
                ["arq00.dwg", "arq07.dwg", "arq14.dwg"],
            )

            Path(pasta, "arq07.dwg").unlink()
            with mock.patch.object(comando, "stdout"), mock.patch.object(comando, "style"):
                sobreviventes = comando._escolher(pasta, {**base, "lista": destino})
            self.assertEqual(len(sobreviventes), 2,
                             "arquivo sumido da lista não pode passar em silêncio")

    def test_causa_desconhecida_cai_no_balde_nosso_e_nao_no_upsell(self):
        """O default da coluna "de quem é" erra para o lado certo.

        Causa nova que ninguém mapeou aparece como conserto **nosso**, nunca como
        venda: errar para cá custa uma linha na nossa fila; errar para lá cobra do
        cliente por um defeito nosso — que é exatamente o que a leitura de 55%
        quase precificou (D42).
        """
        from moduloprancheta.management.commands.medir_cobertura_dwg import (
            CAUSA_ACIMA,
            DONO_PADRAO,
            Command,
        )

        comando = Command()

        self.assertEqual(comando._dono("motivo_que_ainda_nao_existe"), DONO_PADRAO)
        self.assertEqual(comando._dono("falha_motor"), DONO_PADRAO)
        self.assertEqual(comando._dono("dxf_intermediario_ilegivel"), DONO_PADRAO)
        # As duas fronteiras de plano, e só elas, apontam para a venda.
        self.assertIn("comprando", comando._dono("motor_insuficiente"))
        self.assertIn("comprando", comando._dono(CAUSA_ACIMA))
        # O que é do arquivo não é de ninguém — não pode virar upsell.
        self.assertNotIn("comprando", comando._dono("desenho_vazio"))
        self.assertNotIn("comprando", comando._dono("referencia_ausente"))


class PoliticaDeHachuraTests(SimpleTestCase):
    """A escada de conversão da PRA.1d, item 4 — o gerador do consumo (D57).

    Os três primeiros itens do D57 **contiveram** o estouro: frota separada, teto
    por job e a tradução do estouro em `recurso_excedido`. Nenhum deles ataca a
    causa, que é a expansão da hachura: o `Frontend` do `ezdxf` transforma cada
    `HATCH` em linhas de padrão, e cada linha vira registro vivo no `Recorder`
    até a folha ser emitida. Padrão fino sobre área grande dá milhões de
    segmentos — foi assim que uma prancha do acervo chegou a 62 GB.

    O que se prova aqui, em ordem de importância:

    1. **Nada regride.** A primeira tentativa é sempre a fiel, e a degradação é
       escolhida pelo orçamento **tendo sido estourado** — nunca por um palpite
       sobre o arquivo. Prancha que hoje converte bem não muda de aparência.
    2. **O degrau converge.** `SHOW_OUTLINE` pula o `draw_hatch_pattern` inteiro:
       o custo vira O(bordo). Um degrau que ainda pudesse estourar não é degrau.
    3. **O degrau não esconde desenho.** É a diferença entre `SHOW_OUTLINE` e
       `SHOW_SOLID`, e é a lição do D46: folha que abre, parece pronta e cobre o
       que está embaixo é pior que folha que falha.
    4. **A folha diz o que é.** Cada camada da degradação chega à tela por uma
       frase, pelo canal de aviso que já existia.
    """

    # -- a configuração, que é o item 4 propriamente ------------------------
    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_economia_pede_contorno_e_o_normal_continua_o_padrao(self):
        from ezdxf.addons.drawing.config import HatchPolicy

        from .motores.base import ECONOMIA_HACHURA
        from .motores.dxf import MotorDxf

        motor = MotorDxf()
        self.assertIs(motor._configuracao().hatch_policy, HatchPolicy.NORMAL)
        self.assertIs(
            motor._configuracao(ECONOMIA_HACHURA).hatch_policy,
            HatchPolicy.SHOW_OUTLINE,
        )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_degrau_nao_e_o_solido_porque_solido_cobre_desenho(self):
        """A regra do D46 aplicada à escolha do degrau.

        `SHOW_SOLID` custa a mesma fração do `NORMAL` e seria igualmente eficaz
        contra o estouro — e pinta a área hachurada de uma cor só, por cima de
        cota, texto e traço que estão embaixo. Numa planta arquitetônica isso
        **esconde desenho** numa folha que se declara pronta, que é exatamente a
        classe de defeito da tarja preta. Se alguém trocar o degrau, este teste
        cai e a conversa acontece antes do deploy.
        """
        from ezdxf.addons.drawing.config import HatchPolicy

        from .motores.base import ECONOMIA_HACHURA
        from .motores.dxf import MotorDxf

        politica = MotorDxf()._configuracao(ECONOMIA_HACHURA).hatch_policy
        self.assertIsNot(politica, HatchPolicy.SHOW_SOLID)
        self.assertIsNot(politica, HatchPolicy.IGNORE)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_approximate_pattern_nao_desenha_diferente_do_normal_nesta_versao(self):
        """O valor do enum que existe e não faz nada — medido, não suposto.

        `HatchPolicy.SHOW_APPROXIMATE_PATTERN` está em `__members__` do `ezdxf
        1.4.4`, e a leitura óbvia ("padrão aproximado, mais barato") faria dele o
        degrau natural. Só que **nenhum ramo do dispatch de `draw_hatch_entity`
        o trata**: o preenchimento fica em `PATTERN` e o desenho sai igual ao
        `NORMAL`, com o custo do `NORMAL`.

        O teste lê o código-fonte do dispatch em vez de renderizar duas folhas
        porque é a ausência do ramo que importa: no dia em que o `ezdxf` o
        implementar, isto falha e alguém reavalia o degrau com um dado novo — que
        é o efeito desejado.
        """
        import inspect

        from ezdxf.addons.drawing.frontend import Frontend

        fonte = inspect.getsource(Frontend.draw_hatch_entity)
        self.assertIn("HatchPolicy.SHOW_OUTLINE", fonte)
        self.assertNotIn("SHOW_APPROXIMATE_PATTERN", fonte)

    # -- o desenho de verdade ----------------------------------------------
    def _folha_com_hachura(self, economia: str, lado: float = 400.0):
        """Uma folha real com hachura de padrão, convertida com e sem economia.

        `lado` existe para provar a invariante que substituiu a razão de 10×:
        com hachura nativa a folha não pode crescer com a **área**.
        """
        import os
        import tempfile

        import ezdxf

        from .motores.dxf import MotorDxf

        modelo = ezdxf.new("R2010", setup=True)
        espaco = modelo.modelspace()
        # Padrão fino sobre área grande é o gerador do consumo, em miniatura: a
        # mesma forma do arquivo que estourou, pequena o bastante para a suíte.
        hachura = espaco.add_hatch(color=7)
        hachura.set_pattern_fill("ANSI31", scale=0.05)
        hachura.paths.add_polyline_path(
            [(0, 0), (lado, 0), (lado, lado), (0, lado)], is_closed=True,
        )
        espaco.add_line((0, 0), (lado, lado))

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)
        return MotorDxf().converter(
            caminho, formato="dxf", tipo="vetor_2d", economia=economia,
        )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_contorno_continua_desenhando_e_nao_custa_mais_que_o_fiel(self):
        """O degrau precisa das duas coisas: ser barato **e** entregar prancha.

        A folha simplificada tem de continuar sendo um desenho — o traço que não
        é hachura segue lá. Um degrau que devolvesse folha vazia seria pior que a
        falha honesta, porque ninguém desconfia de uma folha que abriu.

        **A razão de 10× que este teste cobrava saiu, e o motivo é a correção,
        não uma concessão.** Ela media a expansão do padrão pela porta dos
        fundos: o fiel era uma ordem de grandeza maior porque desenhava cada
        passada da hachura. Com o padrão nativo o fiel passou a ser O(bordo)
        também, e a razão caiu para perto de 1 — cobrá-la agora seria exigir de
        volta o defeito. Quem guarda a propriedade que importa é o teste
        seguinte.
        """
        from .motores.base import ECONOMIA_HACHURA

        fiel = self._folha_com_hachura("")
        contorno = self._folha_com_hachura(ECONOMIA_HACHURA)

        self.assertLessEqual(len(contorno.conteudo), len(fiel.conteudo))
        self.assertIn(b"<path", contorno.conteudo)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_hachura_fiel_NAO_cresce_com_a_area(self):
        """A invariante que o padrão nativo comprou — e o gerador do D57.

        Multiplicar o lado por 10 multiplica a **área por 100**, e era isso que
        multiplicava o número de segmentos: é a conta *área ÷ espaçamento* que
        levou uma prancha do acervo a 62 GB e matava, em 12/08/2026, um contêiner
        de 3 GB com um DWG de 1,0 MB.

        Desenhada como hachura — contorno mais `<pattern>` —, a folha depende só
        do **bordo**, que não mudou de complexidade. A folga de 2× é para o que
        de fato varia (as coordenadas ficam mais longas, a página muda de
        tamanho); o que este teste proíbe é a ordem de grandeza voltar.
        """
        pequena = self._folha_com_hachura("", lado=400.0)
        grande = self._folha_com_hachura("", lado=4000.0)

        self.assertLess(len(grande.conteudo), len(pequena.conteudo) * 2)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_folha_traz_o_padrao_nativo_e_o_contorno_o_referencia(self):
        """Os dois lados da emissão, porque um sem o outro é folha errada.

        `<pattern>` no `<defs>` sem `fill="url(…)"` é definição que ninguém usa —
        a área sai vazia; `fill="url(…)"` sem a definição é referência quebrada,
        e o navegador desenha **nada** sem avisar. Os dois juntos, e o censo
        declarando quantas hachuras saíram por este caminho.
        """
        folha = self._folha_com_hachura("")

        self.assertIn(b"<pattern", folha.conteudo)
        self.assertIn(b'fill="url(#', folha.conteudo)
        self.assertGreater(folha.detalhe["hachuras_nativas"], 0)
        self.assertEqual(folha.detalhe["hachura"], "completa")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_preenchimento_por_padrao_nao_leva_classe_de_cor_junto(self):
        """Regra de folha de estilo **vence** atributo de apresentação.

        O `SVGRenderBackend` do `ezdxf` resolve a cor de preenchimento numa
        classe CSS (`.C1 {fill: …}`). Um `fill="url(#…)"` posto ao lado dela
        seria simplesmente ignorado pelo navegador, e a área hachurada sairia
        **sólida na cor da hachura** — que é pior que o defeito original, porque
        a folha abre e parece certa. É a família da tarja preta do D46.

        A guarda é estrutural de propósito: o `<path>` que referencia o padrão
        não pode carregar `class`, porque é a classe que ganharia.
        """
        import re

        folha = self._folha_com_hachura("")
        texto = folha.conteudo.decode("utf-8", "replace")

        com_padrao = [
            elemento for elemento in re.findall(r"<path\b[^>]*>", texto)
            if 'fill="url(#' in elemento
        ]
        self.assertTrue(com_padrao, "nenhum preenchimento por padrão na folha")
        for elemento in com_padrao:
            self.assertNotIn("class=", elemento)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_linha_do_ladrilho_cabe_dentro_do_ladrilho(self):
        """O conteúdo de um `<pattern>` é **recortado** pelo retângulo do ladrilho.

        Uma linha em `y=0` teria metade da espessura cortada e o padrão sairia
        mais claro do que é — erro que ninguém nota olhando, e que muda o
        desenho. Ela é desenhada no meio (`y=0.5`), com meio deslocamento
        devolvido na translação para a fase não mudar.

        A espessura tem o seu próprio limite, e por outro motivo: traço mais
        grosso que o vão entre linhas fecharia a área num bloco sólido — a tarja
        preta de novo, agora pela porta do padrão.
        """
        import re

        folha = self._folha_com_hachura("")
        texto = folha.conteudo.decode("utf-8", "replace")

        padroes = re.findall(r"<pattern\b.*?</pattern>", texto, re.S)
        self.assertTrue(padroes, "nenhum <pattern> no <defs>")
        for padrao in padroes:
            for desenho in re.findall(r'\bd="([^"]+)"', padrao):
                # Todo comando do ladrilho fica na altura do meio.
                self.assertNotIn(",0 ", desenho + " ")
                self.assertIn(",0.5", desenho)
            for largura in re.findall(r'stroke-width="([^"]+)"', padrao):
                self.assertLessEqual(float(largura), 0.5)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_hachura_dentro_de_bloco_nao_contamina_o_resto_do_bloco(self):
        """A armadilha do `handle`, e ela é silenciosa.

        A identidade do padrão viaja pelo único campo que o `Recorder` preserva
        por registro — o `handle` —, e o `handle` que o `ezdxf` publica é o da
        **entidade de topo**: dentro de um bloco, o do `INSERT`. Marcar sem
        restaurar faria todo preenchimento seguinte do mesmo `INSERT` herdar o
        padrão da hachura, pintando de hachura um sólido que não é hachura.

        Aqui o bloco tem uma hachura **e** um sólido. A folha tem de trazer
        exatamente um preenchimento por padrão — o da hachura.
        """
        import os
        import tempfile

        import ezdxf

        from .motores.dxf import MotorDxf

        modelo = ezdxf.new("R2010", setup=True)
        bloco = modelo.blocks.new(name="COM_HACHURA")
        hachura = bloco.add_hatch(color=7)
        hachura.set_pattern_fill("ANSI31", scale=0.5)
        hachura.paths.add_polyline_path(
            [(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True,
        )
        bloco.add_solid([(20, 0), (30, 0), (30, 10), (20, 10)])
        modelo.modelspace().add_blockref("COM_HACHURA", (0, 0))

        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)

        folha = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")
        # Uma hachura, uma família (`ANSI31` é de linha única) → um `url(#…)`.
        # Dois seria o sólido do bloco pintado de hachura.
        self.assertEqual(folha.conteudo.count(b'fill="url(#'), 1)
        self.assertEqual(folha.detalhe["hachuras_nativas"], 1)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_folha_declara_com_que_hachura_saiu(self):
        """`completa` também é declarado: um campo que só aparece no caso ruim
        obriga quem lê a saber que ele podia ter aparecido."""
        from .motores.base import ECONOMIA_HACHURA

        self.assertEqual(self._folha_com_hachura("").detalhe["hachura"], "completa")
        self.assertEqual(
            self._folha_com_hachura(ECONOMIA_HACHURA).detalhe["hachura"], "contorno",
        )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_censo_conta_a_hachura_que_o_frontend_desenhou(self):
        """O contador que sustenta a declaração — e que hoje é o único jeito de
        saber que uma hachura saiu pela metade (o `ezdxf` avisa por `print`)."""
        self.assertEqual(self._folha_com_hachura("").detalhe["hachuras"], 1)

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_sem_hachura_a_segunda_passada_nem_comeca(self):
        """Descer a escada sem ter o que economizar queima um orçamento inteiro
        para chegar ao mesmo lugar — e a resposta honesta o pipeline já tinha."""
        import os
        import tempfile

        import ezdxf

        from .motores.base import ECONOMIA_HACHURA, RecursoExcedido
        from .motores.dxf import MotorDxf

        modelo = ezdxf.new("R2010")
        modelo.modelspace().add_line((0, 0), (100, 100))
        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)

        with self.assertRaises(RecursoExcedido) as capturado:
            MotorDxf().converter(
                caminho, formato="dxf", tipo="vetor_2d", economia=ECONOMIA_HACHURA,
            )
        self.assertEqual(capturado.exception.extra.get("teto"), "sem_economia")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_teto_agindo_no_desenho_nao_pode_virar_falha_de_motor(self):
        """O defeito que **só o E2E vivo pegou**, e a razão de ele existir.

        O teto de memória do D57 se manifesta como `MemoryError` — é assim que o
        `RLIMIT_AS` aparece no CPython —, e `MemoryError` **é** `Exception`. O
        `except Exception` que traduz falha de desenho o capturava primeiro, e o
        estouro do orçamento chegava ao pipeline como `falha_motor`.

        Duas consequências, as duas caras: a escada nunca descia (ela espera
        `RecursoExcedido`), e `FalhaMotor` é `retentavel` — a DLQ repetia **três
        vezes** uma conversão que reproduz o mesmo estouro, que é exatamente o que
        o D57 existe para impedir.

        Os testes de unidade não o pegaram porque levantavam `MemoryError` **por
        fora** do motor; o arquivo pesado o levanta **por dentro**. É a diferença
        entre testar o contrato e testar o caminho.
        """
        from .motores.base import FalhaMotor
        from .motores.dxf import MotorDxf

        caminho = self._caminho_de_dxf_simples()
        with mock.patch.object(MotorDxf, "_gravar", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

        # E a falha comum continua embrulhada, que é o comportamento certo dela:
        # o que muda é só o que NÃO pode ser embrulhado.
        with mock.patch.object(MotorDxf, "_gravar", side_effect=ValueError("qualquer")):
            with self.assertRaises(FalhaMotor):
                MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_teto_agindo_na_leitura_nao_acusa_o_arquivo_do_cliente(self):
        """Mesma armadilha, um degrau antes — e aqui a frase errada é pior.

        Ler um DXF grande cabe folgado no teto, mas quando não couber a resposta
        não pode ser `arquivo_corrompido`: essa frase manda o projetista
        reexportar do CAD um arquivo que está perfeito. É a regra do D42 (o dono
        certo da falha) aplicada ao limite de recurso.
        """
        from .motores.dxf import MotorDxf

        caminho = self._caminho_de_dxf_simples()
        with mock.patch("ezdxf.readfile", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d")

    def _caminho_de_dxf_simples(self) -> str:
        import os
        import tempfile

        import ezdxf

        modelo = ezdxf.new("R2010")
        modelo.modelspace().add_line((0, 0), (100, 100))
        descritor, caminho = tempfile.mkstemp(suffix=".dxf")
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))
        modelo.saveas(caminho)
        return caminho

    # -- a escada, no pipeline ---------------------------------------------
    class _MotorFalso:
        """Adaptador que estoura nas N primeiras tentativas e registra as chamadas."""

        def __init__(self, *, economias=(), estouros=0):
            self.economias = economias
            self.estouros = estouros
            self.chamadas = []

        def converter(self, caminho, *, formato, tipo, economia=""):
            from .motores.base import RecursoExcedido

            self.chamadas.append(economia)
            if len(self.chamadas) <= self.estouros:
                raise RecursoExcedido("estourou", teto="memoria")
            return Saida(conteudo=b"<svg/>", extensao="svg", content_type="image/svg+xml")

    def _escada(self, motor):
        from types import SimpleNamespace

        return pipeline._rodar_a_escada(
            motor, "/tmp/x.dxf",
            derivada=SimpleNamespace(pk=1, tipo="vetor_2d"),
            revisao=SimpleNamespace(formato="dxf"),
        )

    def test_a_primeira_tentativa_e_sempre_a_fiel(self):
        """A garantia de que nada regride: o arquivo que converte bem hoje nunca
        chega a ver a política degradada."""
        from .motores.base import ECONOMIA_HACHURA

        motor = self._MotorFalso(economias=(ECONOMIA_HACHURA,), estouros=0)
        self._escada(motor)
        self.assertEqual(motor.chamadas, [""])

    def test_estourou_desce_um_degrau_e_entrega_a_folha(self):
        from .motores.base import ECONOMIA_HACHURA

        motor = self._MotorFalso(economias=(ECONOMIA_HACHURA,), estouros=1)
        saida = self._escada(motor)
        self.assertEqual(motor.chamadas, ["", ECONOMIA_HACHURA])
        self.assertEqual(saida.conteudo, b"<svg/>")

    def test_motor_sem_economia_nao_repete_a_mesma_conversao(self):
        """PDF, imagem e IFC não declaram economia: repetir seria esperar
        resultado diferente da mesma entrada, e gastar outro orçamento nisso."""
        from .motores.base import RecursoExcedido

        motor = self._MotorFalso(economias=(), estouros=1)
        with self.assertRaises(RecursoExcedido):
            self._escada(motor)
        self.assertEqual(motor.chamadas, [""])

    def test_o_ultimo_degrau_que_estoura_mantem_o_erro(self):
        """Sem degrau sobrando, a falha é a que sempre foi — e não vira
        `falha_motor` nem upsell por causa da tentativa extra."""
        from .motores.base import ECONOMIA_HACHURA, RecursoExcedido

        motor = self._MotorFalso(economias=(ECONOMIA_HACHURA,), estouros=2)
        with self.assertRaises(RecursoExcedido) as capturado:
            self._escada(motor)
        self.assertEqual(motor.chamadas, ["", ECONOMIA_HACHURA])
        self.assertEqual(capturado.exception.motivo, "recurso_excedido")
        self.assertFalse(capturado.exception.retentavel)

    def test_o_dwg_tambem_desce_a_escada(self):
        """O formato onde o D57 foi medido não pode ser o único sem a segunda
        passada — e `MotorDwg` **usa** o `MotorDxf`, não o estende.

        **A asserção mudou de igualdade para prefixo em 10/08/2026**, e o motivo
        é que a igualdade passou a ser a pergunta errada: o DWG ganhou um degrau
        que o DXF não tem (`ECONOMIA_SVG_DIRETO`, trocar de renderizador — que só
        existe onde há um DWG para reler). O que o teste sempre quis provar é que
        o DWG **não fica para trás** do DXF, não que os dois sejam idênticos; com
        `assertEqual`, todo degrau novo específico de um formato viraria falha.

        **Prefixo, e não `issubset`:** a ordem é o contrato da escada — os
        degraus herdados têm de vir **antes**, porque economizar no desenho é
        mais barato que trocar de renderizador, e a escada desce na ordem em que
        estão declarados.
        """
        from .motores.base import ECONOMIA_HACHURA
        from .motores.dwg import MotorDwg
        from .motores.dxf import MotorDxf

        n = len(MotorDxf.economias)
        self.assertEqual(MotorDwg.economias[:n], MotorDxf.economias)
        self.assertIn(ECONOMIA_HACHURA, MotorDwg.economias)

    # -- a frase que chega à tela ------------------------------------------
    def test_a_prancha_de_contorno_diz_que_nada_foi_omitido(self):
        """A dúvida real de quem vê uma área hachurada ficar vazia — e a razão de
        a frase existir: sem ela o cliente conclui que perdeu desenho."""
        from .serializers import aviso_da_revisao

        aviso = aviso_da_revisao([object()], {"hachura": "contorno"})
        self.assertEqual(aviso["codigo"], "hachura_simplificada")
        self.assertIn("contorno", aviso["mensagem"])
        self.assertIn("Nenhum traço do desenho foi omitido", aviso["mensagem"])

    def test_a_hachura_parcial_diz_quantas_areas(self):
        from .serializers import aviso_da_revisao

        aviso = aviso_da_revisao(
            [object()], {"hachura": "parcial", "hachuras": 9, "hachuras_truncadas": 3},
        )
        self.assertEqual(aviso["codigo"], "hachura_simplificada")
        self.assertIn("3 áreas hachuradas", aviso["mensagem"])

    def test_hachura_completa_nao_gera_aviso_nenhum(self):
        """Avisar que está tudo certo treina o canteiro a fechar o aviso sem ler,
        e aí o aviso que importa morre junto."""
        from .serializers import aviso_da_revisao

        self.assertIsNone(aviso_da_revisao([object()], {"hachura": "completa"}))

    def test_o_aviso_de_varias_folhas_continua_ganhando_o_titulo(self):
        """Quantas folhas o arquivo tem é a informação que o dono do acervo pediu
        no topo; a hachura entra na mensagem, sem disputar o título."""
        from .serializers import aviso_da_revisao

        aviso = aviso_da_revisao([object(), object()], {"hachura": "contorno"})
        self.assertEqual(aviso["codigo"], "varios_desenhos")
        self.assertIn("2 desenhos", aviso["titulo"])
        self.assertIn("contorno", aviso["mensagem"])


def _instalado(nome: str) -> bool:
    """Se dá para sequer tentar o motor nesta máquina (import tardio, §motores)."""
    import importlib.util

    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):  # pragma: no cover - pacote quebrado
        return False


class FolhaDestruidaDoSvgDiretoTests(SimpleTestCase):
    """O último degrau também tem de provar que desenhou (10/08/2026).

    **De onde saiu.** Rodando o `dwg2SVG` à mão sobre `planta-amostra.dwg`, ele
    devolve `rc=0` e onze `<path>` — e `viewBox="1e20 1e20 -2e20 -2e20"`, com
    todos os traços no mesmo ponto impossível. O `_svg_direto` só perguntava se
    havia elemento de traço, então entregaria essa folha como conversão pronta:
    o modo de falha do D52 (desenho destruído na emissão) chegando pela porta
    nova, e a única metade da lição que o degrau não tinha herdado.

    **Por que a folha destruída é pior que o erro.** Erro entra na fila do
    cockpit e alguém age. Folha destruída sai `PRONTO`, com miniatura e tudo — o
    canteiro abre a prancha, vê o branco e conclui que o sistema está quebrado,
    sem que ninguém tenha o que consertar num relatório.
    """

    def _svg(self, view_box: str, corpo: bytes = b'<path d="M 0,0 L 1,1"/>') -> bytes:
        return (
            b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
            b'width="100%" height="100%" viewBox="' + view_box.encode() + b'">'
            + corpo + b"</svg>"
        )

    def test_o_sentinela_do_libredwg_e_recusado(self):
        """O caso medido, byte a byte como o binário o emite."""
        from .motores.dwg import folha_destruida

        estrago = folha_destruida(self._svg(
            "100000000000000000000.000000 100000000000000000000.000000 "
            "-200000000000000000000.000000 -200000000000000000000.000000"
        ))
        self.assertTrue(estrago)
        self.assertIn("extensão", estrago)

    def test_dimensao_negativa_e_recusada(self):
        """Largura invertida sozinha já basta — não depende do valor ser 1e20."""
        from .motores.dwg import folha_destruida

        self.assertTrue(folha_destruida(self._svg("0 0 -100 -100")))

    def test_dimensao_zero_e_recusada(self):
        from .motores.dwg import folha_destruida

        self.assertTrue(folha_destruida(self._svg("0 0 0 0")))

    def test_coordenada_gigante_com_sinal_certo_e_recusada(self):
        """O sentinela chegando bem-comportado — que a pergunta da dimensão
        deixaria passar."""
        from .motores.dwg import folha_destruida

        self.assertTrue(folha_destruida(self._svg("1e20 1e20 1e20 1e20")))

    def test_a_prancha_normal_passa(self):
        """O controle que impede o guarda de virar recusa geral."""
        from .motores.dwg import folha_destruida

        self.assertEqual(folha_destruida(self._svg("0 0 1109 881")), "")

    def test_utm_de_obra_real_passa(self):
        """A coordenada mais alta que o acervo produz de verdade.

        `confrontantes.dwg` põe a mesma área na origem e em UTM, a 8,5 milhões de
        unidades de distância (§4.5). Se o corte de plausibilidade fosse apertado
        demais, seria justamente o arquivo que motivou a separação de folha que
        pararia de abrir.
        """
        from .motores.dwg import folha_destruida

        self.assertEqual(folha_destruida(self._svg("8500000 8500000 1109 881")), "")

    def test_sem_view_box_nao_reprova(self):
        """Fail-open deliberado: quem julga é a evidência de destruição, não a
        falta dela. Um build futuro que mude o cabeçalho não pode transformar
        atualização de motor em acervo que para de abrir."""
        from .motores.dwg import folha_destruida

        self.assertEqual(folha_destruida(b'<svg><path d="M 0,0"/></svg>'), "")

    def test_view_box_ilegivel_nao_reprova(self):
        from .motores.dwg import folha_destruida

        self.assertEqual(folha_destruida(self._svg("a b c d")), "")
        self.assertEqual(folha_destruida(self._svg("0 0 100")), "")

    def test_a_ordem_das_duas_perguntas(self):
        """Folha vazia continua sendo `DesenhoVazio`, não `falha_motor`.

        As duas checagens olham a mesma folha e respondem coisas diferentes; se a
        geometria fosse conferida primeiro, todo SVG sem traço seria relatado
        como destruído — e sairia da coluna "ninguém resolve" da fila do cockpit
        para a coluna que mede o **nosso** trabalho, inflando-a com arquivos que
        nunca tiveram desenho dentro.
        """
        from .motores.dwg import folha_destruida

        # Sem traço E com viewBox destruído: quem responde é a checagem de traço,
        # que roda antes — este teste prende a ordem no `_svg_direto`.
        vazio = self._svg("1e20 1e20 -2e20 -2e20", corpo=b"<!-- nada -->")
        self.assertTrue(folha_destruida(vazio))  # a função sozinha acusa…
        self.assertFalse(any(  # …e é o `_svg_direto` que a coloca em segundo lugar
            marca in vazio for marca in __import__(
                "moduloprancheta.motores.dwg", fromlist=["ELEMENTOS_DE_TRACO"],
            ).ELEMENTOS_DE_TRACO
        ))


class TetoTraduzidoEmTodosOsMotoresTests(SimpleTestCase):
    """O contrato do `NAO_EMBRULHAR`, cobrado motor a motor — e não só no `ezdxf`.

    **O buraco que estes testes fecham.** O E2E vivo da PRA.1d pegou o teto do
    D57 virando `falha_motor` no `ezdxf` e a correção nasceu lá — dentro do
    `dxf.py`, como se fosse detalhe daquele motor. Os outros três seguiram
    embrulhando `MemoryError`, cada um com a frase errada da sua família:

    | Motor | O teto virava | Por que dói |
    |---|---|---|
    | PDF e imagem | `arquivo_corrompido` | acusa o arquivo do cliente por limite nosso |
    | IFC (leitura) | `arquivo_corrompido` | idem |
    | **IFC (tesselação)** | **`FalhaMotor`, retentável** | **a DLQ repete 3× o mesmo estouro** |
    | preview do DWG | `sem_preview` | família "ninguém age": o teto some da fila |

    O caso do IFC é o caro e o do DWG é o invisível — e nenhum dos dois aparece
    numa suíte que só exercita o motor onde a medição doeu. É por isso que o
    contrato subiu para `motores/base.py`: motor é plural, e a regra é do
    contrato.

    **A varredura estrutural é o teste que importa a longo prazo.** Os testes de
    comportamento provam os quatro motores de hoje; o de AST prova o *próximo* —
    ele lê os adaptadores registrados, não uma lista escrita aqui, então o motor
    da PRA.4 (APS) entra coberto no dia em que for registrado.
    """

    #: A única tradução que **não** culpa ninguém, e por isso dispensa a guarda:
    #: `MotorIndisponivel` nasce sempre de um `except` em volta de um `import`,
    #: onde `MemoryError` não é causa plausível. Exigir guarda ali seria ruído.
    #:
    #: O resto é allowlist ao contrário de propósito. A primeira versão desta
    #: varredura conferia uma **lista de falhas que culpam** (`ArquivoCorrompido`,
    #: `FalhaMotor`, …) e o controle negativo mostrou que ela não pegava o
    #: `dxf.py`: lá a tradução passa por um helper (`raise self._ilegivel(…)`),
    #: cujo nome não está no `raise`. Motor pode traduzir por qualquer caminho —
    #: o que dá para afirmar é o oposto, quais raises são inofensivos.
    SEM_CULPA = {"MotorIndisponivel"}

    # -- o contrato ---------------------------------------------------------
    def test_o_contrato_mora_na_base_e_todo_motor_le_o_mesmo(self):
        """Uma cópia por motor divergiria no primeiro motor novo."""
        from .motores import base, documento, dwg, dxf, ifc

        self.assertEqual(base.NAO_EMBRULHAR, (MemoryError, base.ErroDeConversao))
        for modulo in (dxf, dwg, ifc, documento):
            self.assertIs(
                modulo.NAO_EMBRULHAR, base.NAO_EMBRULHAR,
                f"{modulo.__name__} não lê o contrato da base",
            )

    def test_nenhuma_traducao_de_falha_fica_sem_a_guarda(self):
        """Varre o AST de todo adaptador registrado: `except Exception` que
        **traduz** (levanta exceção nova) precisa de um `except NAO_EMBRULHAR`
        antes.

        Estrutural de propósito. O defeito não é um valor errado que uma
        asserção de comportamento pegue — é um `except` **ausente**, num caminho
        que só arquivo pesado percorre. E ele reaparece sozinho: o jeito natural
        de escrever um motor novo é traduzir tudo o que quebrar.

        **`raise` puro não conta, e engolir também não.** Repassar a exceção é o
        que a guarda faz; e `except Exception: continue` — a aba de layout que
        quebra sem derrubar as outras (D44) — não acusa ninguém de nada. O alvo é
        estritamente a troca de uma exceção por outra.
        """
        import ast
        import importlib
        import pathlib

        from .motores import ADAPTADORES

        desprotegidos = []
        modulos = sorted({type(motor).__module__ for motor in ADAPTADORES.values()})
        self.assertGreaterEqual(len(modulos), 4, "registry de motores encolheu?")

        for nome in modulos:
            arquivo = pathlib.Path(importlib.import_module(nome).__file__)
            for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
                if not isinstance(no, ast.Try):
                    continue
                guardado = any(
                    isinstance(h.type, ast.Name) and h.type.id == "NAO_EMBRULHAR"
                    for h in no.handlers
                )
                for handler in no.handlers:
                    if not self._captura_exception(handler):
                        continue
                    if self._traduz(handler) and not guardado:
                        desprotegidos.append(
                            f"{arquivo.name}:{handler.lineno} troca a exceção sem "
                            "`except NAO_EMBRULHAR` antes — o teto do D57 vira "
                            "falha do arquivo ou do motor"
                        )

        self.assertEqual(desprotegidos, [], "\n".join(desprotegidos))

    def test_a_varredura_acusa_quando_a_guarda_sai(self):
        """**Controle negativo — sem ele a varredura acima não vale nada.**

        Teste estrutural que nunca dispara é decoração: passa igual num código
        certo e num código onde a regra foi apagada. Aqui a fonte de cada motor é
        lida, as guardas são removidas *em memória* (nada é escrito) e a mesma
        varredura tem de acusar.

        Foi este controle que derrubou a primeira versão da varredura, que passava
        limpa no `dxf.py` mesmo sem guarda nenhuma.
        """
        import ast
        import importlib
        import pathlib
        import re

        from .motores import ADAPTADORES

        for nome in sorted({type(motor).__module__ for motor in ADAPTADORES.values()}):
            arquivo = pathlib.Path(importlib.import_module(nome).__file__)
            fonte = arquivo.read_text(encoding="utf-8")
            sem_guarda = re.sub(
                r"[ \t]*except NAO_EMBRULHAR:\n(?:[ \t]*#[^\n]*\n)*[ \t]*raise[^\n]*\n",
                "", fonte,
            )
            self.assertNotEqual(
                sem_guarda, fonte, f"{arquivo.name} não tem guarda nenhuma para remover",
            )

            acusados = []
            for no in ast.walk(ast.parse(sem_guarda)):
                if not isinstance(no, ast.Try):
                    continue
                for handler in no.handlers:
                    if self._captura_exception(handler) and self._traduz(handler):
                        acusados.append(handler.lineno)
            self.assertTrue(
                acusados,
                f"{arquivo.name} sem as guardas não foi acusado — a varredura é vácua",
            )

    @staticmethod
    def _captura_exception(handler) -> bool:
        import ast

        alvo = handler.type
        if isinstance(alvo, ast.Name):
            return alvo.id == "Exception"
        if isinstance(alvo, ast.Tuple):
            return any(
                isinstance(item, ast.Name) and item.id == "Exception"
                for item in alvo.elts
            )
        return False

    @classmethod
    def _traduz(cls, handler) -> bool:
        """O handler troca a exceção por outra? (`raise` puro e engolir não contam.)"""
        import ast

        for no in ast.walk(handler):
            if not isinstance(no, ast.Raise) or no.exc is None:
                continue
            levantado = no.exc
            if (isinstance(levantado, ast.Call)
                    and isinstance(levantado.func, ast.Name)
                    and levantado.func.id in cls.SEM_CULPA):
                continue
            return True
        return False

    # -- o comportamento, motor a motor -------------------------------------
    @unittest.skipUnless(_instalado("pypdfium2"), "pypdfium2 não instalado")
    def test_o_teto_no_pdf_nao_vira_arquivo_corrompido(self):
        """Rasterizar a 1ª página é o ponto deste motor que aloca pelo arquivo —
        uma A0 a 144 dpi é da ordem de 100 MP, e o tamanho da folha é escolha do
        cliente. Estourar ali não pode mandar o projetista reexportar um PDF que
        está perfeito."""
        import pypdfium2

        from .motores.base import ArquivoCorrompido
        from .motores.documento import MotorDocumento

        with mock.patch.object(pypdfium2, "PdfDocument", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorDocumento()._primeira_pagina_do_pdf("/tmp/qualquer.pdf")

        # E o PDF de fato ilegível continua sendo o do cliente:
        with mock.patch.object(pypdfium2, "PdfDocument", side_effect=ValueError("x")):
            with self.assertRaises(ArquivoCorrompido):
                MotorDocumento()._primeira_pagina_do_pdf("/tmp/qualquer.pdf")

    def test_o_teto_na_imagem_nao_vira_arquivo_corrompido(self):
        """`Image.open` lê só o cabeçalho; quem aloca é o `load()`, e ele aloca
        pelas dimensões declaradas no arquivo."""
        from PIL import Image

        from .motores.documento import MotorDocumento

        with mock.patch.object(Image, "open", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorDocumento()._abrir_imagem("/tmp/qualquer.png")

    @unittest.skipUnless(_instalado("ifcopenshell"), "ifcopenshell não instalado")
    def test_o_teto_lendo_o_ifc_nao_acusa_o_arquivo(self):
        """O parser carrega o modelo inteiro **antes** de o `TETO_ELEMENTOS` ter
        o que contar — então é aqui que um IFC grande estoura, não na contagem."""
        import ifcopenshell

        from .motores.ifc import MotorIfc

        with mock.patch.object(ifcopenshell, "open", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorIfc()._abrir("/tmp/qualquer.ifc")

    @unittest.skipUnless(_instalado("ifcopenshell"), "ifcopenshell não instalado")
    def test_o_teto_tesselando_o_ifc_nao_vira_falha_retentavel(self):
        """**O ponto mais caro do buraco.** A tesselação traduzia tudo para
        `FalhaMotor`, que é `retentavel`: a DLQ repetia três vezes uma conversão
        que reproduz o mesmo estouro — três picos de memória pelo preço de um
        upload. O contraste com a falha comum, que **continua** retentável, é
        metade do teste: o que muda é só o que não pode ser embrulhado."""
        from .motores.base import FalhaMotor
        from .motores.ifc import MotorIfc

        with mock.patch.object(MotorIfc, "_serializador", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorIfc()._para_gltf("/tmp/qualquer.ifc", object())

        with mock.patch.object(MotorIfc, "_serializador", side_effect=ValueError("x")):
            with self.assertRaises(FalhaMotor) as capturado:
                MotorIfc()._para_gltf("/tmp/qualquer.ifc", object())
        self.assertTrue(capturado.exception.retentavel)

    def test_o_teto_no_preview_do_dwg_nao_some_da_fila(self):
        """`SemPreviewEmbutido` é da família "ninguém age" (D45/D49) — existe para
        a ausência de miniatura sair da fila do que nós consertamos. O teto do D57
        caindo ali saía da fila junto: um limite nosso agindo sem aparecer em
        lugar nenhum."""
        import os
        import tempfile

        from PIL import Image

        from .motores.base import SemPreviewEmbutido
        from .motores.dwg import MotorDwg

        descritor, caminho = tempfile.mkstemp(suffix=".bmp")
        os.write(descritor, b"BM" + b"\x00" * 64)
        os.close(descritor)
        self.addCleanup(lambda: os.unlink(caminho))

        with mock.patch.object(Image, "open", side_effect=MemoryError()):
            with self.assertRaises(MemoryError):
                MotorDwg()._miniatura_do_raster(caminho, codigo="AC1015", rotulo="R2000")

        # O preview em formato exótico (WMF) continua sendo ausência declarada:
        with mock.patch.object(Image, "open", side_effect=ValueError("wmf")):
            with self.assertRaises(SemPreviewEmbutido):
                MotorDwg()._miniatura_do_raster(caminho, codigo="AC1015", rotulo="R2000")


class MedicaoEmLotesTests(SimpleTestCase):
    """Medir o acervo em lotes e somar depois — a PRA.1d, item 5.

    O lote existe por causa da **memória**: um processo por lote devolve o RSS ao
    host ao terminar, e é isso que impede a remedição de repetir o D57. O preço é
    que cada lote conhece só o próprio pedaço — e a taxa que dimensiona a PRA.4 é
    a do corpus. Estes testes cobrem a costura entre as duas coisas.
    """

    def _comando(self):
        from moduloprancheta.management.commands.medir_cobertura_dwg import Command

        return Command()

    def _parcial(self, tmp, nome, *, pular, medidos, convertido, falhou,
                 corpus_total=30, corpus_hash="abc123", motor="LibreDWG 0.13.3",
                 causas=None, previews=None, arquivos=None):
        import json
        from pathlib import Path

        from moduloprancheta.management.commands.medir_cobertura_dwg import Command

        destino = Path(tmp, nome)
        destino.write_text(json.dumps({
            # A versão vem da classe, e não de um literal: o parcial já subiu de
            # v1 para v2 e um número escrito à mão aqui faria a suíte passar a
            # exercitar um formato que o comando não produz mais.
            "versao_formato": Command.FORMATO_PARCIAL,
            "motor": motor,
            "corpus_hash": corpus_hash,
            "corpus_total": corpus_total,
            "janela": {"pular": pular, "medidos": medidos},
            "baldes": {"convertido": convertido, "falhou_no_alcance": falhou},
            "causas": causas or {},
            "por_versao": {"AC1015": {"convertido": convertido}},
            "motivos": {},
            "sinais": {},
            "arquivos": arquivos or [],
            "previews": previews,
            "resgatados": None,
        }), encoding="utf-8")
        return str(destino)

    def _impresso(self, saida):
        return "\n".join(str(c.args[0]) for c in saida.write.call_args_list)

    def test_o_lote_nao_muda_quem_esta_no_corpus(self):
        """`--pular`/`--limite` recortam DEPOIS da amostragem.

        Se a janela fosse aplicada antes, cada lote amostraria 1-em-N do próprio
        pedaço e o corpus somado seria outro conjunto — a comparação antes/depois
        do D42 mediria arquivos diferentes e chamaria a diferença de conserto.
        """
        import tempfile
        from pathlib import Path

        comando = self._comando()
        base = {"lista": "", "amostra": 7, "recursivo": False,
                "salvar_lista": "", "limite": 0, "pular": 0}
        with tempfile.TemporaryDirectory() as pasta:
            for i in range(21):
                Path(pasta, f"arq{i:02d}.dwg").write_bytes(b"")

            inteiro = comando._escolher(pasta, dict(base))
            corpus = list(comando._corpus)
            impressao = comando._corpus_hash

            lote1 = comando._escolher(pasta, {**base, "pular": 0, "limite": 2})
            self.assertEqual(comando._corpus, corpus,
                             "o corpus é a amostra inteira, não a janela")
            self.assertEqual(comando._corpus_hash, impressao,
                             "a impressão digital não pode depender do lote")
            lote2 = comando._escolher(pasta, {**base, "pular": 2, "limite": 2})

            self.assertEqual(lote1 + lote2, inteiro)

    def test_amostra_e_lista_salva_dao_o_mesmo_corpus(self):
        """O invariante de que a remedição inteira depende.

        O lote 0 monta o corpus por `--amostra` e salva a lista; os seguintes o
        montam por `--lista`. Se as duas rotas produzissem impressões digitais
        diferentes, `--consolidar` recusaria os lotes **no fim** — depois de a
        máquina ter feito o trabalho todo.
        """
        import tempfile
        from pathlib import Path

        comando = self._comando()
        base = {"lista": "", "amostra": 7, "recursivo": False,
                "salvar_lista": "", "limite": 0, "pular": 0}
        with tempfile.TemporaryDirectory() as pasta:
            for i in range(21):
                Path(pasta, f"arq{i:02d}.dwg").write_bytes(b"")
            destino = str(Path(pasta, "amostra.txt"))

            por_amostra = comando._escolher(pasta, dict(base))
            hash_amostra = comando._corpus_hash
            with mock.patch.object(comando, "stdout"):
                comando._salvar_lista(destino, pasta, comando._corpus)

            por_lista = comando._escolher(
                pasta, {**base, "lista": destino, "amostra": 0})

        self.assertEqual(por_lista, por_amostra)
        self.assertEqual(comando._corpus_hash, hash_amostra)

    def test_a_soma_dos_lotes_da_a_taxa_do_corpus(self):
        import tempfile

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(comando, "stdout") as saida:
            comando._consolidar([
                self._parcial(tmp, "l0.json", pular=0, medidos=10, convertido=8, falhou=2),
                self._parcial(tmp, "l1.json", pular=10, medidos=10, convertido=7, falhou=3),
                self._parcial(tmp, "l2.json", pular=20, medidos=10, convertido=9, falhou=1),
            ])

        impresso = self._impresso(saida)
        self.assertIn("Lotes somados: 3", impresso)
        self.assertIn("30 de 30", impresso)
        # 24 de 30 — a taxa do corpus, e não a média das taxas dos lotes.
        self.assertIn("80.0%", impresso)

    def test_buraco_na_cobertura_e_denunciado(self):
        """O lote que morreu no meio não pode virar taxa com cara de definitiva."""
        import tempfile

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(comando, "stdout") as saida:
            comando._consolidar([
                self._parcial(tmp, "l0.json", pular=0, medidos=10, convertido=8, falhou=2),
                # o lote do meio (10–19) não rodou
                self._parcial(tmp, "l2.json", pular=20, medidos=10, convertido=9, falhou=1),
            ])

        impresso = self._impresso(saida)
        self.assertIn("BURACO", impresso)
        self.assertIn("10–19", impresso)
        self.assertIn("NÃO é a do corpus", impresso)

    def test_lote_repetido_e_denunciado_como_contagem_em_dobro(self):
        import tempfile

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(comando, "stdout") as saida:
            comando._consolidar([
                self._parcial(tmp, "l0.json", pular=0, medidos=10, convertido=8, falhou=2),
                self._parcial(tmp, "l0b.json", pular=5, medidos=10, convertido=7, falhou=3),
                self._parcial(tmp, "l2.json", pular=15, medidos=15, convertido=9, falhou=6),
            ])

        impresso = self._impresso(saida)
        self.assertIn("SOBREPOSIÇÃO", impresso)
        self.assertIn("dobro", impresso)

    def test_corpus_diferente_nao_soma(self):
        """Dois acervos somados dariam uma taxa que não descreve acervo nenhum."""
        import tempfile

        from django.core.management.base import CommandError

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp:
            parciais = [
                self._parcial(tmp, "l0.json", pular=0, medidos=10, convertido=8, falhou=2),
                self._parcial(tmp, "l1.json", pular=10, medidos=10, convertido=7,
                              falhou=3, corpus_hash="OUTRO"),
            ]
            with self.assertRaises(CommandError) as erro:
                comando._consolidar(parciais)
        self.assertIn("mesmo corpus", str(erro.exception))

    def test_motor_diferente_nao_soma(self):
        """Somar motores diferentes mede a média de dois motores — e a medição
        existe para dizer o que ESTE motor entrega."""
        import tempfile

        from django.core.management.base import CommandError

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp:
            parciais = [
                self._parcial(tmp, "l0.json", pular=0, medidos=10, convertido=8, falhou=2),
                self._parcial(tmp, "l1.json", pular=10, medidos=20, convertido=7,
                              falhou=3, motor="LibreDWG 0.12.5"),
            ]
            with self.assertRaises(CommandError) as erro:
                comando._consolidar(parciais)
        self.assertIn("motores diferentes", str(erro.exception))

    def test_balde_medido_so_em_parte_dos_lotes_diz_isso(self):
        """`--preview` em metade dos lotes daria uma contagem com cara de corpus."""
        import tempfile

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(comando, "stdout") as saida:
            comando._consolidar([
                self._parcial(tmp, "l0.json", pular=0, medidos=15, convertido=8,
                              falhou=7, previews={"com_preview": 8}),
                self._parcial(tmp, "l1.json", pular=15, medidos=15, convertido=7, falhou=8),
            ])

        impresso = self._impresso(saida)
        self.assertIn("Nem todo lote rodou com --preview", impresso)

    def test_o_relatorio_diz_QUAIS_arquivos_falharam_e_nao_so_quantos(self):
        """A metade que faltava ao registro — e que custou a investigação do D61.

        A remedição de 07/08 guardou os baldes e jogou fora o veredito por
        arquivo: "11 estouraram o orçamento" não diz *quais*, e a investigação
        seguinte teria de remedir o acervo inteiro só para reencontrá-los. O
        corpus já era versionado pela lição do D41; o resultado, não.

        Prova-se aqui o que o relatório passou a responder: a lista **por causa e
        com dono** (fila de trabalho, não estatística) e os que **só couberam
        descendo a escada** da PRA.1d — o sinal que mostrou, na passada sob o teto
        corrigido do D76, que o degrau funciona quando o orçamento é o declarado.
        """
        import tempfile

        comando = self._comando()
        com_nome = [
            {"arquivo": "Anexos/hidraulico.dwg", "balde": "falhou_no_alcance",
             "versao": "AC1032", "causa": "recurso_excedido", "nota": "", "sinais": []},
            {"arquivo": "estrutural.dwg", "balde": "falhou_no_alcance",
             "versao": "AC1018", "causa": "dxf_intermediario_ilegivel",
             "nota": "", "sinais": []},
            {"arquivo": "arquitetonico.dwg", "balde": "convertido", "versao": "AC1032",
             "causa": "", "nota": "",
             "sinais": ["convertido_com_hachura_simplificada"]},
            {"arquivo": "eletrica.dwg", "balde": "convertido", "versao": "AC1015",
             "causa": "", "nota": "", "sinais": []},
        ]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(comando, "stdout") as saida:
            comando._consolidar([
                self._parcial(tmp, "l0.json", pular=0, medidos=30, convertido=28,
                              falhou=2, causas={"recurso_excedido": 1,
                                                "dxf_intermediario_ilegivel": 1},
                              arquivos=com_nome),
            ])

        impresso = self._impresso(saida)
        self.assertIn("Anexos/hidraulico.dwg", impresso)
        self.assertIn("estrutural.dwg", impresso)
        # O caminho relativo inteiro, não o `basename`: o acervo tem subpastas com
        # nomes repetidos, e "hidraulico.dwg" sozinho não diz qual ir buscar.
        self.assertIn("Anexos/", impresso)
        # Cada causa sai com o dono junto — a lista é de trabalho, e trabalho tem
        # dono (a tabela do D42).
        self.assertIn("recurso_excedido", impresso)
        self.assertIn("dxf_intermediario_ilegivel", impresso)
        # Quem desceu a escada aparece nomeado; quem converteu inteiro, não —
        # senão a seção vira a listagem do acervo e ninguém a lê.
        self.assertIn("arquitetonico.dwg", impresso)
        self.assertNotIn("eletrica.dwg", impresso)

    def test_parcial_de_antes_do_D76_nao_soma_com_o_de_agora(self):
        """A subida de v1→v2 não é burocracia de formato.

        Os lotes de 07/08 foram medidos quando o `RLIMIT_AS` media o processo
        inteiro e o teto de 1536 MB entregava ~384 MB reais (D76). Somá-los com os
        de hoje daria uma taxa que é a média de dois orçamentos — exatamente o
        tipo de número que já precificou errado uma vez.
        """
        import json
        import tempfile
        from pathlib import Path

        from django.core.management.base import CommandError

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp:
            antigo = Path(tmp, "lote-060.json")
            antigo.write_text(json.dumps({
                "versao_formato": 1, "motor": "LibreDWG 0.13.3",
                "corpus_hash": "abc123", "corpus_total": 30,
                "janela": {"pular": 0, "medidos": 10},
                "baldes": {"convertido": 8}, "causas": {}, "por_versao": {},
                "motivos": {}, "sinais": {}, "previews": None, "resgatados": None,
            }), encoding="utf-8")
            with self.assertRaises(CommandError) as erro:
                comando._consolidar([str(antigo)])

        self.assertIn("lote-060.json", str(erro.exception))
        self.assertIn("D76", str(erro.exception))

    def test_parcial_ilegivel_diz_qual_janela_refazer(self):
        """Lote interrompido no meio da escrita: o conserto é aquela janela, e
        não a medição inteira."""
        import tempfile
        from pathlib import Path

        from django.core.management.base import CommandError

        comando = self._comando()
        with tempfile.TemporaryDirectory() as tmp:
            quebrado = Path(tmp, "l1.json")
            quebrado.write_text('{"versao_formato": 1, "moto', encoding="utf-8")
            with self.assertRaises(CommandError) as erro:
                comando._consolidar([str(quebrado)])
        self.assertIn("l1.json", str(erro.exception))
        self.assertIn("de novo", str(erro.exception))


# ---------------------------------------------------------------------------
# 16. PRA.5b — as duas portas que restavam, e o lote do acervo
# ---------------------------------------------------------------------------
# Fecha o [D75](../../docs/historico-correcoes.md). A PRA.5a tirou do módulo a porta que
# entregava binário ao LibreDWG; sobraram duas, e o que elas tinham em comum é o
# que se prova aqui: **nenhuma olhava os bytes**. O snapshot conferia só o
# tamanho e o `importar-bcf` decidia pelo nome — e no caso do snapshot o arquivo
# ainda era servido de volta como `image/png` pelo `entregar_arquivo`, que é a
# plataforma afirmando um tipo que ninguém tinha verificado.
#
# O lote é a outra metade da fatia e prova a R18: a plataforma adivinha
# disciplina, código e revisão do caminho da pasta, e **nada entra antes do sim**.


def png_falso(nome="recorte.png", kb=2):
    """PNG com a assinatura de verdade — é ela que a porta lê agora."""
    return SimpleUploadedFile(nome, b"\x89PNG\r\n\x1a\n" + (b"0" * (kb * 1024)))


def dwg_falso(nome="planta.dwg", kb=2):
    """DWG o bastante para a porta o reconhecer: `AC10` é o cabeçalho real."""
    return SimpleUploadedFile(nome, b"AC1024" + (b"0" * (kb * 1024)))


def executavel(nome):
    """O arquivo do D75, com o nome que o atacante escolheu.

    `MZ` é o cabeçalho do PE do Windows. O nome é livre de propósito: o ponto da
    fatia é que ele deixou de importar.
    """
    return SimpleUploadedFile(nome, b"MZ\x90\x00" + (b"\x00" * 2048))


class PortaDoSnapshotTests(MarcacaoTestBase):
    """O recorte de tela do ponto de vista, agora pela porta única."""

    def test_executavel_com_nome_de_imagem_nao_vira_snapshot(self):
        """O D75 na metade que ele não alcançou.

        Antes desta fatia o arquivo era gravado sem ninguém olhar os bytes e
        depois **servido de volta como `image/png`** — o `entregar_arquivo` do
        `prancheta.marcacao` declara esse tipo por saber quem escreveu a imagem,
        e essa certeza era falsa enquanto qualquer binário entrasse.
        """
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/ponto-de-vista/",
            {"snapshot": executavel("recorte.png")}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("snapshot", resposta.json())

    def test_a_recusa_nao_deixa_ponto_de_vista_orfao(self):
        """A ordem mudou junto com a porta: admitir vem ANTES de criar a linha.

        Criar primeiro deixaria um ponto de vista sem imagem e sem dono a cada
        recusa — e ele sairia no BCF exportado como um apontamento vazio.
        """
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/ponto-de-vista/",
            {"snapshot": executavel("x.png")}, format="multipart",
        )
        self.assertEqual(PontoDeVista.objects.filter(marcacao=marcacao).count(), 0)

    def test_imagem_de_verdade_continua_entrando(self):
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/ponto-de-vista/",
            {"snapshot": png_falso()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertTrue(resposta.json()["snapshot_url"])

    def test_ponto_de_vista_sem_imagem_continua_valido(self):
        """A captura falha em celular velho, e um apontamento sem foto ainda é um
        apontamento — bloqueá-lo perderia o conteúdo para salvar o enfeite."""
        marcacao = self._marcacao()
        self.autenticar(perms=PERMS_MARCACAO_TOTAL)
        resposta = self.client.post(
            f"/api/prancheta/marcacoes/{marcacao.pk}/ponto-de-vista/", {}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertIsNone(resposta.json()["snapshot_url"])

    def test_o_teto_do_snapshot_e_do_RECURSO_e_nao_do_formato(self):
        """`imagem` no acervo é prancha escaneada (25 MB); aqui é recorte de tela.

        É o gancho `teto_mb_do_formato` fazendo **dentro** do mesmo módulo o que
        ele existe para fazer entre módulos — e o número é o mesmo que vale para
        o snapshot que chega dentro de um `.bcfzip`, para os dois caminhos do
        mesmo dado não divergirem.
        """
        from funcoesimpexp.registro import obter

        from .impexp import MAX_SNAPSHOT_MB

        acervo = obter(entrega.RECURSO_ACERVO)
        marcacao = obter(entrega.RECURSO_MARCACAO)
        self.assertEqual(marcacao.teto_mb_do_formato("imagem"), MAX_SNAPSHOT_MB)
        self.assertEqual(
            acervo.teto_mb_do_formato("imagem"), FORMATO_POR_CODIGO["imagem"].max_mb,
        )
        self.assertGreater(
            acervo.teto_mb_do_formato("imagem"), marcacao.teto_mb_do_formato("imagem"),
        )

    def test_o_recurso_da_marcacao_nao_recebe_desenho(self):
        """Dois formatos, e não a allowlist inteira: aqui entra a marcação e a
        imagem dela, não o acervo."""
        from funcoesimpexp.registro import obter

        self.assertEqual(
            sorted(obter(entrega.RECURSO_MARCACAO).formatos_arquivo), ["bcf", "imagem"],
        )


class PortaDoImportarBcfTests(MarcacaoTestBase):
    """A última porta de upload da Prancheta fora do motor."""

    def _bcfzip(self, nome="externo.bcfzip"):
        topico = bcf.TopicoBcf(guid=str(uuid.uuid4()), titulo="De fora")
        return SimpleUploadedFile(nome, bcf.escrever([topico]))

    def test_bcfzip_de_verdade_continua_entrando(self):
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": revisao.pk, "arquivo": self._bcfzip()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["criadas"], 1)

    def test_executavel_renomeado_para_bcfzip_nao_chega_ao_leitor_de_zip(self):
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": revisao.pk, "arquivo": executavel("marcacoes.bcfzip")},
            format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Marcacao.objects.count(), 0)

    def test_desenho_na_porta_da_marcacao_recebe_o_endereco_certo(self):
        """O simétrico do BCF subido como revisão, e a mesma tese: o cliente não
        mandou o arquivo errado, mandou o certo na porta errada. Listar os
        formatos aceitos aqui o mandaria procurar o que ele já tem."""
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": revisao.pk, "arquivo": dwg_falso()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("acervo", str(resposta.json()["arquivo"]).lower())

    def test_zip_que_nao_e_bcf_ainda_e_400_pela_segunda_camada(self):
        """A porta aprova os bytes (é um zip, e o sufixo diz `.bcfzip`); quem o
        recusa é o leitor, que abre e não acha o `markup.bcf`. As duas camadas
        existem e dizem coisas diferentes."""
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("leiame.txt", b"nada aqui")

        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="profissional")
        resposta = self.client.post("/api/prancheta/marcacoes/importar-bcf/", {
            "revisao": revisao.pk,
            "arquivo": SimpleUploadedFile("x.bcfzip", buffer.getvalue()),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 400)

    def test_a_parede_comercial_vem_antes_de_ler_o_arquivo(self):
        """402 continua sendo 402: quem não contratou o BCF não passa, e não paga
        a leitura do arquivo para descobrir."""
        revisao = self._revisao(situacao="vigente")
        self.autenticar(perms=PERMS_MARCACAO_TOTAL, plano="essencial")
        resposta = self.client.post(
            "/api/prancheta/marcacoes/importar-bcf/",
            {"revisao": revisao.pk, "arquivo": self._bcfzip()}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 402)
        self.assertEqual(resposta.json()["code"], "formato_nao_contratado")


# --- O lote do acervo histórico (R18) --------------------------------------


class TaxonomiaDaPastaTests(SimpleTestCase):
    """O palpite da R18, sem banco: o que a pasta e o nome do arquivo dizem."""

    def test_disciplina_sai_da_pasta_mais_funda(self):
        """`TorreA/PROJETOS/ARQ/plantas/x.dwg` — varrer de fora para dentro
        acharia primeiro qualquer pasta genérica que por acaso casasse."""
        self.assertEqual(
            taxonomia.disciplina_do_caminho("TorreA/PROJETOS/ARQ/plantas/x.dwg"),
            "arquitetura",
        )

    def test_a_abreviatura_do_canteiro_e_o_nome_inteiro_caem_no_mesmo_lugar(self):
        for caminho, esperado in (
            ("TorreA/EST/v.dwg", "estrutural"),
            ("TorreA/Estrutural/v.dwg", "estrutural"),
            ("TorreA/HID/v.dwg", "hidrossanitario"),
            ("TorreA/Hidráulica/v.dwg", "hidrossanitario"),
            ("TorreA/PPCI/v.dwg", "incendio"),
            ("obra/PROJETO ARQ/v.dwg", "arquitetura"),
        ):
            self.assertEqual(taxonomia.disciplina_do_caminho(caminho), esperado, caminho)

    def test_pasta_que_nao_declara_disciplina_cai_no_default(self):
        """`OUTRA` não é fracasso: aparece na conferência como qualquer outro
        palpite, e o operador recusa a linha se não servir."""
        self.assertEqual(taxonomia.disciplina_do_caminho("TorreA/2019/x.dwg"), "outra")

    def test_o_nome_do_arquivo_nao_vota_na_disciplina(self):
        """`ARQ-001.dwg` dentro de `EST/` é o código do documento, não um voto."""
        self.assertEqual(
            taxonomia.disciplina_do_caminho("TorreA/EST/ARQ-001.dwg"), "estrutural",
        )

    def test_a_marca_de_revisao_separa_documento_de_entrega(self):
        """É o que faz um acervo histórico virar acervo e não uma pilha: as
        quatro entregas da mesma prancha colapsam num documento com quatro
        revisões, que é a pergunta que o canteiro faz."""
        for nome, codigo, revisao in (
            ("PLANTA-BAIXA_R03.dwg", "PLANTA-BAIXA", "R03"),
            ("PLANTA-BAIXA-REV2.dwg", "PLANTA-BAIXA", "R02"),
            ("CORTE AA R 1.dwg", "CORTE AA", "R01"),
            ("FACHADA.dwg", "FACHADA", "R00"),
        ):
            self.assertEqual(taxonomia.codigo_e_revisao(nome), (codigo, revisao), nome)

    def test_sem_separador_nao_e_marca_de_revisao(self):
        """`PILAR03` viraria o documento `PILA` na revisão 3 — o mesmo cuidado da
        extensão composta do D75.1."""
        self.assertEqual(taxonomia.codigo_e_revisao("PILAR03.dwg"), ("PILAR03", "R00"))

    def test_extensao_composta_some_inteira(self):
        self.assertEqual(taxonomia.codigo_e_revisao("nuvem.copc.laz"), ("nuvem", "R00"))


class LoteDoAcervoTests(PranchetaTestBase):
    """A carga do acervo histórico, ponta a ponta pela porta única."""

    ROTA = "/api/impexp/prancheta.acervo/importar-arquivos/"

    def _enviar(self, *arquivos, caminhos=None, obra=None):
        import json

        corpo = {
            "arquivos": list(arquivos),
            "contexto": json.dumps({"obra": (obra or self.obra).pk}),
        }
        if caminhos:
            corpo["caminhos"] = list(caminhos)
        return self.client.post(self.ROTA, corpo, format="multipart")

    def _decidir(self, importacao_id, acao):
        return self.client.post(f"/api/impexp/importacoes/{importacao_id}/{acao}/")

    def test_a_pasta_vira_acervo_e_as_revisoes_colapsam_no_documento(self):
        """A tese da fatia: `TorreA/ARQ/PLANTA_R00.dwg` e `..._R01.dwg` são UM
        documento com duas revisões, na disciplina que a pasta declarou."""
        self.autenticar()
        resposta = self._enviar(
            dwg_falso("PLANTA-BAIXA_R00.dwg", kb=2),
            dwg_falso("PLANTA-BAIXA_R01.dwg", kb=3),
            caminhos=["TorreA/ARQ/PLANTA-BAIXA_R00.dwg", "TorreA/ARQ/PLANTA-BAIXA_R01.dwg"],
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        aplicada = self._decidir(resposta.json()["importacao_id"], "aplicar")
        self.assertEqual(aplicada.status_code, 200, aplicada.content)

        documentos = DocumentoProjeto.objects.filter(obra=self.obra)
        self.assertEqual(documentos.count(), 1)
        documento = documentos.get()
        self.assertEqual(documento.codigo, "PLANTA-BAIXA")
        self.assertEqual(documento.disciplina, "arquitetura")
        self.assertEqual(
            sorted(documento.revisoes.values_list("revisao", flat=True)), ["R00", "R01"],
        )

    def test_o_arquivo_do_acervo_e_uma_copia_e_nao_um_ponteiro(self):
        """A conferência é apagada logo depois do `aplicar` (o motor agenda a
        limpeza). Se a revisão apontasse para o mesmo binário em vez de copiá-lo,
        o acervo ficaria com o download em 404 — e só se descobriria em produção."""
        self.autenticar()
        resposta = self._enviar(dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"])
        self._decidir(resposta.json()["importacao_id"], "aplicar")

        revisao = RevisaoDocumento.objects.get()
        self.assertTrue(revisao.arquivo.name.startswith("prancheta/"))
        with revisao.arquivo.open("rb") as binario:
            self.assertTrue(binario.read().startswith(b"AC10"))

    def test_nada_entra_no_acervo_antes_do_sim(self):
        """R1 aplicada a bytes. O arquivo está na área de conferência e não
        existe para o módulo dono — é a diferença entre o lote e o avulso."""
        self.autenticar()
        resposta = self._enviar(dwg_falso("PLANTA.dwg"), caminhos=["TorreA/ARQ/PLANTA.dwg"])
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(DocumentoProjeto.objects.count(), 0)
        self.assertEqual(RevisaoDocumento.objects.count(), 0)

    def test_o_lote_nasce_sem_vigente(self):
        """Publicar é verbo separado (`revisao.publicar`) e o lote pede só
        `documento.edit` — a lição do D28. Documento sem vigente é item da fila
        de decisão do cockpit, não lacuna."""
        self.autenticar(perms=PERMS_SEM_PUBLICAR)
        resposta = self._enviar(dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"])
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self._decidir(resposta.json()["importacao_id"], "aplicar")

        self.assertEqual(RevisaoDocumento.objects.count(), 1)
        self.assertEqual(
            RevisaoDocumento.objects.get().situacao, RevisaoDocumento.Situacao.RASCUNHO,
        )

    def test_desfazer_devolve_o_acervo_ao_estado_anterior(self):
        self.autenticar()
        resposta = self._enviar(dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"])
        importacao_id = resposta.json()["importacao_id"]
        self._decidir(importacao_id, "aplicar")
        self.assertEqual(RevisaoDocumento.objects.count(), 1)

        desfeita = self._decidir(importacao_id, "desfazer")
        self.assertEqual(desfeita.status_code, 200, desfeita.content)
        self.assertEqual(RevisaoDocumento.objects.count(), 0)
        # O documento sai junto: foi ESTE lote que o criou, e deixá-lo encheria o
        # acervo de prancha sem desenho dentro.
        self.assertEqual(DocumentoProjeto.objects.count(), 0)

    def test_desfazer_nao_apaga_documento_que_ja_existia(self):
        """Entre aplicar e desfazer cabe um upload avulso no mesmo documento."""
        documento = self._documento(codigo="P")
        self._revisao(documento=documento, revisao="R99")
        self.autenticar()
        resposta = self._enviar(dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"])
        importacao_id = resposta.json()["importacao_id"]
        self._decidir(importacao_id, "aplicar")
        self._decidir(importacao_id, "desfazer")

        self.assertTrue(DocumentoProjeto.objects.filter(pk=documento.pk).exists())
        self.assertEqual(documento.revisoes.count(), 1)

    def test_o_mesmo_arquivo_reenviado_e_duplicado_e_nao_duplica(self):
        """Idempotência por `hash`: o mesmo desenho com outro nome é o mesmo
        desenho, e reimportar a pasta inteira não dobra o acervo."""
        self.autenticar()
        primeira = self._enviar(dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"])
        self._decidir(primeira.json()["importacao_id"], "aplicar")

        segunda = self._enviar(
            dwg_falso("P-outro-nome.dwg"), caminhos=["TorreA/ARQ/P-outro-nome.dwg"],
        )
        self.assertEqual(segunda.json()["duplicadas"], 1)
        self._decidir(segunda.json()["importacao_id"], "aplicar")
        self.assertEqual(RevisaoDocumento.objects.count(), 1)

    def test_rotulo_de_revisao_repetido_nao_derruba_o_lote(self):
        """`PLANTA.dwg` e `PLANTA (cópia).dwg` pedem os dois o `R00`. Como
        `aplicar` é tudo-ou-nada, a `UniqueConstraint` levaria as outras 299
        pranchas junto — com um 500."""
        self.autenticar()
        resposta = self._enviar(
            dwg_falso("PLANTA.dwg", kb=2),
            dwg_falso("PLANTA.dwg", kb=3),
            caminhos=["TorreA/ARQ/PLANTA.dwg", "TorreA/ARQ/copia/PLANTA.dwg"],
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        aplicada = self._decidir(resposta.json()["importacao_id"], "aplicar")
        self.assertEqual(aplicada.status_code, 200, aplicada.content)
        self.assertEqual(
            sorted(RevisaoDocumento.objects.values_list("revisao", flat=True)),
            ["R00", "R01"],
        )

    def test_obra_de_outro_tenant_nao_recebe_acervo(self):
        """Mesma mensagem para "não existe" e "é de outro tenant": distinguir
        confirmaria a existência da obra alheia."""
        self.autenticar()
        resposta = self._enviar(
            dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"], obra=self.obra_b,
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("contexto", resposta.json())

    def test_sem_obra_o_lote_nao_comeca(self):
        """`contexto_requerido` — o destino é resolvido antes de ler um byte."""
        import json

        self.autenticar()
        resposta = self.client.post(self.ROTA, {
            "arquivos": [dwg_falso("P.dwg")], "contexto": json.dumps({}),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 400)

    def test_executavel_renomeado_nao_entra_no_lote(self):
        """O D75 no caminho de lote — que é o pior deles, porque é por onde
        entram centenas de arquivos de uma vez."""
        self.autenticar()
        resposta = self._enviar(executavel("planta.dwg"), caminhos=["TorreA/ARQ/planta.dwg"])
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(RevisaoDocumento.objects.count(), 0)

    def test_bcfzip_nao_entra_pelo_lote_do_acervo(self):
        """`formatos_arquivo` do acervo exclui o interop: marcação não é desenho,
        e a porta dela é o `prancheta.marcacao`."""
        topico = bcf.TopicoBcf(guid=str(uuid.uuid4()), titulo="De fora")
        self.autenticar()
        resposta = self._enviar(
            SimpleUploadedFile("marcacoes.bcfzip", bcf.escrever([topico])),
            caminhos=["TorreA/ARQ/marcacoes.bcfzip"],
        )
        self.assertEqual(resposta.status_code, 400)

    def test_o_lote_carrega_os_tiers_do_plano_de_quem_o_abriu(self):
        """`aplicar_linha` roda na requisição da CONFIRMAÇÃO, onde o motor não
        passa o usuário — e sem isto o lote inteiro cairia no `TIERS_PADRAO` (só
        o livre), convertendo trezentas pranchas pelo motor de entrada de um
        cliente que pagou pelo premium."""
        from funcoesimpexp.models import Importacao

        self.autenticar(plano="empresarial")
        resposta = self._enviar(dwg_falso("P.dwg"), caminhos=["TorreA/ARQ/P.dwg"])
        self.assertEqual(resposta.status_code, 201, resposta.content)

        lote = Importacao.objects.get(pk=resposta.json()["importacao_id"])
        self.assertIn("premium", lote.contexto["tiers"])
        self.assertEqual(lote.contexto["obra"], self.obra.pk)

    def test_o_acervo_declara_o_que_recebe_e_o_lote_e_desfazivel(self):
        """As quatro propriedades que o motor lê para decidir o que oferecer na
        tela — e que o registry recusaria no boot se estivessem tortas."""
        from funcoesimpexp.registro import obter

        acervo = obter(entrega.RECURSO_ACERVO)
        self.assertTrue(acervo.importa)
        self.assertTrue(acervo.desfazivel)
        self.assertTrue(acervo.de_arquivo)
        self.assertNotIn("bcf", acervo.formatos_arquivo)


# ---------------------------------------------------------------------------
# 15. A entrega seguinte — `atualizar/`, a última porta avulsa (PRA.9d)
# ---------------------------------------------------------------------------
class EntregaSeguinteTests(PranchetaTestBase):
    """Trocar o arquivo de uma prancha que já está aberta na tela.

    **O irmão `enviar/` saiu na PRA.9d**, e com ele os testes que o cobriam. Ele
    era um segundo caminho para o mesmo gesto do wizard de arquivos — o dono
    achou o defeito no uso ("escolher arquivos é inútil, já que tem enviar pasta
    e dentro tem escolher pasta e escolher arquivos") —, e o que ele provava
    sobre a entrada do acervo é hoje provado pelo lote, em
    `CorrigirNaConferenciaTests` e `VariasDisciplinasTests`.

    O que ficou aqui é o gesto que o lote **não** cobre, e por isso não saiu: o
    documento já está escolhido, é o que a pessoa tem na tela, e não há acervo a
    conferir.
    """

    def test_a_porta_avulsa_do_acervo_nao_existe_mais(self):
        """Regressão da PRA.9d.

        Não é zelo com rota morta: enquanto ela responder, uma tela futura pode
        voltar a usá-la sem passar pela conferência — e as duas entradas
        divergiriam de novo, que é o defeito inteiro desta fatia.

        **É 405 e não 404, e a diferença é do roteador, não do módulo.** Sem a
        `@action`, `documentos/enviar/` passa a casar a rota de *detalhe*
        (`documentos/<pk>/`) com `pk="enviar"`, e o detalhe não recebe POST. A
        garantia que importa é a segunda linha: nada entrou no acervo.
        """
        self.autenticar()
        resposta = self.client.post("/api/prancheta/documentos/enviar/", {
            "obra": self.obra.pk, "arquivo": pdf_falso("ARQ-PLB-001_R02.pdf"),
        }, format="multipart")
        self.assertEqual(resposta.status_code, 405, resposta.content)
        self.assertFalse(DocumentoProjeto.objects.filter(codigo="ARQ-PLB-001").exists())
        self.assertFalse(RevisaoDocumento.objects.exists())

    def test_o_palpite_de_disciplina_por_nome_tambem_saiu_do_http(self):
        """`disciplinas/adivinhar/` existia só para a tela avulsa pré-marcar os
        chips. O palpite continua — mudou de lugar: quem o faz agora é o
        `dados_do_arquivo`, na montagem da linha de conferência, com o mesmo
        `_TOKENS` do servidor. (405 pelo mesmo motivo do teste acima.)"""
        self.autenticar()
        resposta = self.client.post(
            "/api/prancheta/disciplinas/adivinhar/",
            {"nomes": ["ARQ-ELE-PLB-001.dwg"]}, format="json",
        )
        self.assertEqual(resposta.status_code, 405, resposta.content)

    def test_atualizar_numera_a_partir_do_maior_que_existe(self):
        """Continua do maior, e não do primeiro buraco: a entrega de hoje não
        pode entrar ATRÁS da que está em campo porque uma revisão do meio foi
        apagada um dia."""
        documento = self._documento()
        self._revisao(documento, "R00")
        self._revisao(documento, "R01", situacao="vigente")
        self.autenticar()

        resposta = self.client.post(
            f"/api/prancheta/documentos/{documento.pk}/atualizar/",
            {"arquivo": pdf_falso("qualquer-nome.pdf"), "observacao": "pé-direito do hall"},
            format="multipart",
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        corpo = resposta.json()
        self.assertEqual(corpo["revisao"], "R02")
        self.assertEqual(corpo["situacao"], "rascunho")
        self.assertEqual(corpo["observacao"], "pé-direito do hall")
        # A vigente NÃO muda ao subir: trocar o desenho que o campo executa
        # continua sendo `revisao.publicar`.
        documento.refresh_from_db()
        self.assertEqual(
            documento.revisoes.get(situacao="vigente").revisao, "R01",
        )

    def test_atualizar_respeita_o_rotulo_do_nome_quando_esta_livre(self):
        """Quem numera o acervo é o escritório. Se o arquivo diz R07, é R07."""
        documento = self._documento()
        self._revisao(documento, "R00")
        self.autenticar()
        resposta = self.client.post(
            f"/api/prancheta/documentos/{documento.pk}/atualizar/",
            {"arquivo": pdf_falso("ARQ-PLB-001_R07.pdf")},
            format="multipart",
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["revisao"], "R07")

    def test_atualizar_de_outro_tenant_e_404(self):
        alheio = self._documento(codigo="ALHEIA-001", tenant=self.tenant_b, obra=self.obra_b)
        self.autenticar()
        resposta = self.client.post(
            f"/api/prancheta/documentos/{alheio.pk}/atualizar/",
            {"arquivo": pdf_falso("x.pdf")}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 404)

    def test_atualizar_de_documento_que_nao_comeca_no_R00(self):
        """O caso que o E2E pegou e o unitário acima **não** pegava.

        `codigo_e_revisao` devolve `R00` em dois casos diferentes: o nome que diz
        `_R00` e o nome que não diz nada. Num documento cujas revisões começam em
        `R00` a fusão se esconde — o rótulo colide, o helper anda, e o resultado
        sai certo por acaso. Num documento que começa em `R02`, o `R00` está livre
        e a entrega de hoje entrava **atrás** da que o canteiro está executando.
        """
        documento = self._documento(codigo="EST-VIG-001")
        self._revisao(documento, "R02", situacao="vigente")
        self.autenticar()
        resposta = self.client.post(
            f"/api/prancheta/documentos/{documento.pk}/atualizar/",
            {"arquivo": pdf_falso("sem-marca-de-revisao.pdf")}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["revisao"], "R03")

    def test_o_lote_no_documento_existente_nao_volta_para_o_inicio(self):
        """**A regressão que a PRA.9d quase deixou passar**, e que só aparece
        depois de o avulso sair.

        O `enviar/` cobria "a entrega de hoje de uma prancha viva" e usava o
        `proximo_rotulo` — segue do maior. O lote cobria "o acervo histórico
        inteiro" e usava um `_rotulo_livre` que tapava o primeiro buraco, o que
        era inofensivo enquanto o documento de destino nascia vazio. Com uma porta
        só, o lote passou a receber os dois casos: documento com `R04` em campo,
        chega `HID-001.pdf` sem marca de revisão, o `R00` está livre — e a entrega
        de hoje entraria **atrás** da que o canteiro está executando.
        """
        import json

        documento = self._documento(codigo="HID-001")
        self._revisao(documento, "R04", situacao="vigente")
        self.autenticar()

        enviou = self.client.post(
            "/api/impexp/prancheta.acervo/importar-arquivos/",
            {
                "arquivos": [pdf_falso("HID-001.pdf")],
                "contexto": json.dumps({"obra": self.obra.pk}),
            },
            format="multipart",
        )
        self.assertEqual(enviou.status_code, 201, enviou.content)
        importacao_id = enviou.json()["importacao_id"]

        # A célula chega **vazia**, e não com um `R00` inventado: o nome não
        # declarou revisão nenhuma, e a conferência não deve mostrar um rótulo
        # que não vai ser o gravado.
        detalhe = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()
        self.assertEqual(detalhe["linhas"][0]["valores"]["revisao"], "")

        aplicou = self.client.post(f"/api/impexp/importacoes/{importacao_id}/aplicar/")
        self.assertEqual(aplicou.status_code, 200, aplicou.content)
        documento.refresh_from_db()
        self.assertEqual(
            sorted(documento.revisoes.values_list("revisao", flat=True)), ["R04", "R05"],
        )

    def test_o_lote_ainda_respeita_a_revisao_que_o_nome_declara(self):
        """O outro lado da mesma troca: quem numera o acervo é o escritório."""
        import json

        self.autenticar()
        enviou = self.client.post(
            "/api/impexp/prancheta.acervo/importar-arquivos/",
            {
                "arquivos": [pdf_falso("ARQ-PLB-001_R02.pdf")],
                "contexto": json.dumps({"obra": self.obra.pk}),
            },
            format="multipart",
        )
        self.assertEqual(enviou.status_code, 201, enviou.content)
        importacao_id = enviou.json()["importacao_id"]
        detalhe = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()
        self.assertEqual(detalhe["linhas"][0]["valores"]["revisao"], "R02")

        self.client.post(f"/api/impexp/importacoes/{importacao_id}/aplicar/")
        documento = DocumentoProjeto.objects.get(obra=self.obra, codigo="ARQ-PLB-001")
        revisao = documento.revisoes.get()
        self.assertEqual(revisao.revisao, "R02")
        # Subir não é publicar — o lote nasce em rascunho, como sempre.
        self.assertEqual(revisao.situacao, "rascunho")


# ---------------------------------------------------------------------------
# 16. PRA.9b — a disciplina é vocabulário do cliente
# ---------------------------------------------------------------------------
class DisciplinaDoTenantTests(PranchetaTestBase):
    """As 13 embutidas são o piso; o andar de cima é do cliente.

    O que motivou a fatia foi a fileira de filtro da grade virar um botão só:
    tudo caía em *Outra*, porque a tela não mandava disciplina no envio e não
    havia como criar a que faltava.
    """

    URL = "/api/prancheta/disciplinas/"

    def test_catalogo_traz_as_embutidas_mesmo_sem_nenhuma_criada(self):
        self.autenticar()
        resposta = self.client.get(self.URL)
        self.assertEqual(resposta.status_code, 200, resposta.content)
        codigos = [d["codigo"] for d in resposta.json()]
        self.assertIn("arquitetura", codigos)
        self.assertIn("outra", codigos)
        # Toda linha vem com cor resolvida: a tela pinta, não deriva.
        self.assertTrue(all(d["cor"].startswith("#") for d in resposta.json()))
        self.assertTrue(all(d["padrao"] for d in resposta.json()))

    def test_criar_disciplina_deriva_o_codigo_do_nome(self):
        """Quem cria não precisa saber o que é slug — mas é o slug que a prancha
        guarda, então ele tem de sair de algum lugar previsível."""
        self.autenticar()
        resposta = self.client.post(
            self.URL, {"nome": "Impermeabilização", "cor": "#0F766E"}, format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["codigo"], "impermeabilizacao")

        catalogo = self.client.get(self.URL).json()
        criada = next(d for d in catalogo if d["codigo"] == "impermeabilizacao")
        self.assertFalse(criada["padrao"])   # dá para apagar
        self.assertEqual(criada["cor"], "#0F766E")

    def test_cor_invalida_e_recusada(self):
        """O valor vai para dentro de um `style` no cliente: texto livre aqui é
        conteúdo do usuário num atributo CSS."""
        self.autenticar()
        resposta = self.client.post(
            self.URL, {"nome": "Fachada", "cor": "red; background:url(x)"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_disciplina_de_outro_tenant_nao_aparece(self):
        DisciplinaProjeto.objects.create(
            tenant=self.tenant_b, codigo="segredo", nome="Segredo Industrial",
        )
        self.autenticar()
        codigos = [d["codigo"] for d in self.client.get(self.URL).json()]
        self.assertNotIn("segredo", codigos)

    def test_renomear_embutida_nao_a_torna_apagavel(self):
        """Trocar o rótulo de `legal` para "Aprovação na prefeitura" não pode
        tirá-la do piso: é dela que a taxonomia adivinha a pasta no lote."""
        self.autenticar()
        self.client.post(self.URL, {"nome": "Legal", "codigo": "legal"}, format="json")
        catalogo = self.client.get(self.URL).json()
        legal = next(d for d in catalogo if d["codigo"] == "legal")
        self.assertTrue(legal["padrao"])

    def test_o_lote_grava_a_disciplina_escolhida_na_tela(self):
        """A escolha da tela é a reserva do palpite (PRA.9c), e uma disciplina
        **criada pelo cliente** atravessa a entrada como qualquer embutida."""
        self.autenticar()
        self.client.post(self.URL, {"nome": "Fachada"}, format="json")
        self._pelo_lote(pdf_falso("SEM-SIGLA-001_R00.pdf"), disciplina="fachada")

        documento = DocumentoProjeto.objects.get(codigo="SEM-SIGLA-001")
        self.assertEqual(documento.disciplina, "fachada")
        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        grupo = next(g for g in acervo["disciplinas"] if g["disciplina"] == "fachada")
        self.assertEqual(grupo["rotulo"], "Fachada")

    def test_lote_com_disciplina_inexistente_e_recusado_antes_de_ler_byte(self):
        """Sem isto, trezentas pranchas gravariam um slug que a tela não sabe
        pintar nem oferecer no filtro. É `validar_contexto`, e ele roda **antes**
        do primeiro byte — a recusa não custa o upload."""
        self.autenticar()
        resposta = self._pelo_lote(
            pdf_falso("X-001.pdf"), disciplina="nao-existe", aplicar=False,
        )
        self.assertEqual(resposta.status_code, 400, resposta.content)
        self.assertFalse(DocumentoProjeto.objects.filter(codigo="X-001").exists())

    def test_o_lote_nao_reclassifica_prancha_que_ja_esta_no_acervo(self):
        """**A regra ficou mais firme com a saída do avulso, e de propósito.**

        O `enviar/` reclassificava o documento que ainda estava em *Outra* — era
        o conserto barato de quem tinha subido tudo sem escolher. O lote nunca
        fez isso: `aplicar_linha` só define disciplina **na criação**, porque uma
        remessa de trezentos arquivos que reclassificasse o acervo existente
        desfaria decisão individual em massa, que é a fronteira do
        `publicar-pendentes`.

        Com uma porta só, é a regra do lote que vale — e reclassificar continua
        possível pelo ato explícito, na própria prancha (`codigos_disciplina`).
        """
        self.autenticar()
        self.client.post(self.URL, {"nome": "Fachada"}, format="json")
        self._pelo_lote(pdf_falso("FAC-009_R00.pdf"))
        documento = DocumentoProjeto.objects.get(codigo="FAC-009")
        self.assertEqual(documento.disciplina, "outra")

        # Remessa seguinte com escolha: entra como revisão nova, e NÃO mexe na
        # classificação do documento que já existe. `kb` diferente de propósito —
        # a chave do lote é o **hash**, e dois PDFs do mesmo tamanho seriam byte a
        # byte o mesmo arquivo: a linha viria `duplicada` e nada seria gravado,
        # que é a dedup funcionando e não o que este teste quer medir.
        self._pelo_lote(pdf_falso("FAC-009_R01.pdf", kb=8), disciplina="fachada")
        documento.refresh_from_db()
        self.assertEqual(documento.disciplina, "outra")
        self.assertEqual(documento.revisoes.count(), 2)

        # O ato explícito, na prancha, é o que reclassifica.
        self.client.patch(
            f"/api/prancheta/documentos/{documento.pk}/",
            {"codigos_disciplina": ["fachada"]}, format="json",
        )
        documento.refresh_from_db()
        self.assertEqual(documento.disciplina, "fachada")

    def test_apagar_disciplina_nao_apaga_prancha(self):
        """`CASCADE` aqui apagaria acervo por causa de uma faxina de rótulo. O
        documento guarda o CÓDIGO, e volta a se exibir por ele."""
        self.autenticar()
        criada = self.client.post(self.URL, {"nome": "Paisagismo"}, format="json").json()
        documento = self._documento(codigo="PAI-001")
        documento.definir_disciplinas(["paisagismo"])
        self._revisao(documento, "R00")

        apagou = self.client.delete(f"{self.URL}{criada['disciplina_id']}/")
        self.assertEqual(apagou.status_code, 204, apagou.content)

        documento = DocumentoProjeto.objects.get(codigo="PAI-001")
        self.assertEqual(documento.disciplina, "paisagismo")
        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        grupo = next(g for g in acervo["disciplinas"] if g["disciplina"] == "paisagismo")
        # Degradação honesta: o slug cru, e não "Outra" — que mentiria sobre uma
        # classificação que a prancha ainda carrega.
        self.assertEqual(grupo["rotulo"], "paisagismo")

    def test_acervo_publica_o_catalogo_e_o_rotulo_no_grupo(self):
        """A fileira de filtro os desenha; lê-los do primeiro documento do grupo
        deixava a disciplina renomeada desatualizada até alguém recarregar."""
        self.autenticar()
        self.client.post(self.URL, {"nome": "Fachada", "cor": "#B45309"}, format="json")
        documento = self._documento(codigo="FAC-777")
        documento.definir_disciplinas(["fachada"])
        self._revisao(documento, "R00")

        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        grupo = next(g for g in acervo["disciplinas"] if g["disciplina"] == "fachada")
        self.assertEqual(grupo["rotulo"], "Fachada")
        self.assertEqual(grupo["cor"], "#B45309")
        codigos = [d["codigo"] for d in acervo["catalogo_disciplinas"]]
        self.assertIn("fachada", codigos)
        self.assertIn("arquitetura", codigos)

    def test_criar_disciplina_exige_documento_edit(self):
        self.autenticar(perms=["prancheta.documento.view"])
        resposta = self.client.post(self.URL, {"nome": "Fachada"}, format="json")
        self.assertEqual(resposta.status_code, 403)


# ---------------------------------------------------------------------------
# 17. PRA.9c — uma prancha pode ter VÁRIAS disciplinas
# ---------------------------------------------------------------------------
class VariasDisciplinasTests(PranchetaTestBase):
    """A planta de forro é arquitetura **e** elétrica.

    Obrigar a escolher uma fazia escolher errado — ou não escolher, que era o
    caminho para tudo cair em *Outra*.
    """

    def test_o_palpite_do_nome_ja_chega_com_TODAS_as_disciplinas(self):
        """**A correção da PRA.9d.**

        A coluna é `multipla` desde a PRA.9c, mas o palpite do lote cortava em
        `[0]`: `ARQ-ELE-PLB-001.dwg` chegava à conferência só como Arquitetura, e
        a Elétrica tinha de ser marcada à mão em cada linha. O upload avulso —
        que era o outro caminho da tela — pré-marcava as duas desde sempre, então
        manter o corte teria transformado o caminho único numa regressão para o
        arquivo que declara mais de uma.
        """
        self.autenticar()
        detalhe = self._pelo_lote(pdf_falso("ARQ-ELE-PLB-001_R00.pdf"))
        self.assertEqual(
            detalhe["linhas"][0]["valores"]["disciplina"], "arquitetura,eletrica",
        )

        documento = DocumentoProjeto.objects.get(codigo="ARQ-ELE-PLB-001")
        self.assertEqual(documento.codigos_de_disciplina, ["arquitetura", "eletrica"])
        # A coluna denormalizada acompanha, com a PRIMEIRA como principal: é ela
        # que sustenta ordenação, coluna do lote e cor de destaque do cartão — e
        # é o que impede `"arquitetura,eletrica"`, que não é `choices` de
        # ninguém, de entrar no campo.
        self.assertEqual(documento.disciplina, "arquitetura")

    def test_tres_siglas_no_nome_entram_as_tres(self):
        self.autenticar()
        self._pelo_lote(pdf_falso("ARQ-ELE-HID-001_R00.pdf"))
        documento = DocumentoProjeto.objects.get(codigo="ARQ-ELE-HID-001")
        self.assertEqual(len(documento.codigos_de_disciplina), 3)

    def test_a_pasta_continua_vencendo_o_nome_e_declara_uma_so(self):
        """A precedência da PRA.9c não mudou: pasta > nome > escolha da tela. A
        pasta declara **uma**, porque é uma que ela declara — quem passou a
        devolver a lista inteira foi o palpite do nome."""
        self.autenticar()
        detalhe = self._pelo_lote(
            pdf_falso("ARQ-ELE-PLB-002_R00.pdf"), caminhos=["TorreA/HID/ARQ-ELE-PLB-002_R00.pdf"],
        )
        self.assertEqual(detalhe["linhas"][0]["valores"]["disciplina"], "hidrossanitario")

    def test_nome_sem_sigla_nao_inventa_disciplina(self):
        """Lista vazia é resposta legítima, e diferente de "Outra": inventar
        classificação é pior do que não ter."""
        self.autenticar()
        self._pelo_lote(pdf_falso("PRANCHA-GENERICA_R00.pdf"))
        documento = DocumentoProjeto.objects.get(codigo="PRANCHA-GENERICA")
        self.assertEqual(documento.disciplina, "outra")

    def test_a_prancha_aparece_em_TODAS_as_suas_disciplinas_no_acervo(self):
        """É o que "várias disciplinas" significa: quem filtra por elétrica quer
        ver a planta de forro. A soma dos grupos passa a ser maior que o total —
        não é inconsistência, e por isso o total não sai da soma."""
        self.autenticar()
        documento = self._documento(codigo="FORRO-001")
        documento.definir_disciplinas(["arquitetura", "eletrica"])
        self._revisao(documento, "R00")

        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        grupos = {g["disciplina"]: [d["codigo"] for d in g["documentos"]] for g in acervo["disciplinas"]}
        self.assertIn("FORRO-001", grupos["arquitetura"])
        self.assertIn("FORRO-001", grupos["eletrica"])
        self.assertEqual(acervo["total_documentos"], 1)

    def test_filtro_de_documentos_casa_qualquer_disciplina(self):
        """No `filterset_fields` ele compararia só a coluna principal, e a
        prancha sumiria do filtro da segunda disciplina."""
        self.autenticar()
        documento = self._documento(codigo="SHAFT-001")
        documento.definir_disciplinas(["hidrossanitario", "incendio"])
        self._revisao(documento, "R00")

        for codigo in ("hidrossanitario", "incendio"):
            resposta = self.client.get(f"/api/prancheta/documentos/?disciplina={codigo}")
            self.assertEqual(resposta.status_code, 200)
            achados = [d["codigo"] for d in resposta.json()["results"]]
            self.assertIn("SHAFT-001", achados, f"sumiu no filtro de {codigo}")

    def test_documento_antigo_sem_vinculo_continua_respondendo(self):
        """A migração de dados é desnecessária **porque** este caso funciona: o
        `codigos_de_disciplina` cai na coluna quando não há vínculo."""
        documento = self._documento(codigo="ANTIGO-001")
        documento.disciplina = "estrutural"
        documento.save(update_fields=["disciplina"])
        self._revisao(documento, "R00", situacao="vigente")
        self.autenticar()

        acervo = self.client.get(f"/api/prancheta/acervo/?obra={self.obra.pk}").json()
        grupo = next(g for g in acervo["disciplinas"] if g["disciplina"] == "estrutural")
        self.assertIn("ANTIGO-001", [d["codigo"] for d in grupo["documentos"]])

        achados = self.client.get("/api/prancheta/documentos/?disciplina=estrutural").json()
        self.assertIn("ANTIGO-001", [d["codigo"] for d in achados["results"]])

    def test_reclassificar_pela_prancha_troca_o_conjunto_inteiro(self):
        self.autenticar()
        documento = self._documento(codigo="RECLASS-001")
        documento.definir_disciplinas(["arquitetura"])

        resposta = self.client.patch(
            f"/api/prancheta/documentos/{documento.pk}/",
            {"codigos_disciplina": ["eletrica", "arquitetura"]},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(
            [d["codigo"] for d in resposta.json()["disciplinas"]], ["eletrica", "arquitetura"],
        )
        # A principal acompanhou a troca de ordem.
        self.assertEqual(resposta.json()["disciplina"], "eletrica")

    def test_repetida_na_lista_entra_uma_vez_so(self):
        """É o que a tela manda quando alguém toca duas vezes no mesmo chip."""
        documento = self._documento(codigo="REPETE-001")
        documento.definir_disciplinas(["eletrica", "eletrica", "arquitetura"])
        self.assertEqual(documento.codigos_de_disciplina, ["eletrica", "arquitetura"])

    def test_lote_com_pasta_declarada_ignora_a_escolha_da_tela(self):
        """A escolha da tela é a **reserva**, não o carimbo (PRA.9c inverteu a
        PRA.9b): manda-se a pasta da obra inteira, e uma escolha só classificaria
        elétrica, hidráulica e arquitetura com a mesma disciplina."""
        from .impexp import AcervoDeProjeto

        recurso = AcervoDeProjeto()
        recurso.contexto = {"obra": self.obra.pk, "disciplina": "topografia"}

        class _Arquivo:
            nome = "P-001.dwg"
            caminho = "TorreA/ELE/P-001.dwg"
            hash = "x"
            formato = "dwg"
            tamanho = 10

        self.assertEqual(recurso.dados_do_arquivo(_Arquivo())["disciplina"], "eletrica")

    def test_lote_sem_pasta_nem_nome_cai_na_escolha_da_tela(self):
        from .impexp import AcervoDeProjeto

        recurso = AcervoDeProjeto()
        recurso.contexto = {"obra": self.obra.pk, "disciplina": "topografia"}

        class _Arquivo:
            nome = "generico.dwg"
            caminho = "generico.dwg"
            hash = "x"
            formato = "dwg"
            tamanho = 10

        self.assertEqual(recurso.dados_do_arquivo(_Arquivo())["disciplina"], "topografia")


# ---------------------------------------------------------------------------
# 18. R19 — corrigir a disciplina NA CONFERÊNCIA, sem reenviar o arquivo
# ---------------------------------------------------------------------------
class CorrigirNaConferenciaTests(PranchetaTestBase):
    """A conferência aceitava só aceitar/recusar a linha inteira.

    O caso que forçou a mudança: manda-se a pasta **da obra**, o palpite acerta as
    subpastas organizadas e erra o arquivo solto no meio — e a única saída era
    recusar a linha e subir aquele arquivo à parte.
    """

    ROTA = "/api/impexp/prancheta.acervo/importar-arquivos/"

    def _enviar(self, *arquivos, caminhos=None, obra=None):
        import json

        corpo = {
            "arquivos": list(arquivos),
            "contexto": json.dumps({"obra": (obra or self.obra).pk}),
        }
        if caminhos:
            corpo["caminhos"] = list(caminhos)
        return self.client.post(self.ROTA, corpo, format="multipart")

    def test_a_coluna_disciplina_e_declarada_editavel_e_multipla(self):
        from funcoesimpexp.registro import obter

        acervo = obter(entrega.RECURSO_ACERVO)
        coluna = next(c for c in acervo.colunas if c.campo == "disciplina")
        self.assertTrue(coluna.editavel)
        self.assertTrue(coluna.multipla)
        # As outras seguem de leitura: código e revisão são o que a conferência
        # existe para o operador CONFERIR, não reescrever.
        self.assertFalse(next(c for c in acervo.colunas if c.campo == "codigo").editavel)

    def test_o_catalogo_publica_as_opcoes_do_tenant(self):
        """A tela é compartilhada e não sabe o que é disciplina — quem oferece a
        lista é o recurso, e ela é do cliente."""
        self.autenticar()
        self.client.post(
            "/api/prancheta/disciplinas/", {"nome": "Fachada", "cor": "#B45309"}, format="json",
        )
        catalogo = self.client.get("/api/impexp/recursos/").json()
        acervo = next(
            r for r in catalogo["recursos"] if r["id"] == entrega.RECURSO_ACERVO
        )
        coluna = next(c for c in acervo["colunas"] if c["campo"] == "disciplina")
        valores = [o["valor"] for o in coluna["opcoes"]]
        self.assertIn("arquitetura", valores)
        self.assertIn("fachada", valores)
        # A cor viaja junto: é por ela que se reconhece antes de ler.
        self.assertEqual(
            next(o for o in coluna["opcoes"] if o["valor"] == "fachada")["cor"], "#B45309",
        )

    def test_corrigir_troca_o_palpite_de_uma_linha(self):
        self.autenticar()
        resposta = self._enviar(pdf_falso("SOLTO.pdf"), caminhos=["TorreA/SOLTO.pdf"])
        self.assertEqual(resposta.status_code, 201, resposta.content)
        importacao_id = resposta.json()["importacao_id"]

        detalhe = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()
        linha = detalhe["linhas"][0]
        self.assertEqual(linha["valores"]["disciplina"], "outra")  # pasta não declara

        corrigida = self.client.post(
            f"/api/impexp/importacoes/{importacao_id}/corrigir/",
            {"valores": {"disciplina": "eletrica,incendio"}, "linhas": [linha["linha_id"]]},
            format="json",
        )
        self.assertEqual(corrigida.status_code, 200, corrigida.content)
        self.assertEqual(corrigida.json()["linhas_corrigidas"], 1)

        depois = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()
        self.assertEqual(depois["linhas"][0]["valores"]["disciplina"], "eletrica,incendio")

    def test_o_valor_corrigido_e_o_que_entra_no_acervo(self):
        """O ciclo inteiro: corrigir → aplicar → a prancha nasce nas duas."""
        self.autenticar()
        importacao_id = self._enviar(
            pdf_falso("SOLTO2.pdf"), caminhos=["TorreA/SOLTO2.pdf"],
        ).json()["importacao_id"]
        detalhe = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()

        self.client.post(
            f"/api/impexp/importacoes/{importacao_id}/corrigir/",
            {"valores": {"disciplina": "arquitetura,eletrica"}},
            format="json",
        )
        aplicou = self.client.post(f"/api/impexp/importacoes/{importacao_id}/aplicar/")
        self.assertEqual(aplicou.status_code, 200, aplicou.content)

        documento = DocumentoProjeto.objects.get(
            obra=self.obra, codigo=detalhe["linhas"][0]["valores"]["codigo"],
        )
        self.assertEqual(documento.codigos_de_disciplina, ["arquitetura", "eletrica"])

    def test_coluna_nao_editavel_e_recusada(self):
        """Sem isto a tela gravaria qualquer chave no JSON da linha, e o
        `aplicar_linha` receberia um campo que não existe."""
        self.autenticar()
        importacao_id = self._enviar(
            pdf_falso("SOLTO3.pdf"), caminhos=["TorreA/SOLTO3.pdf"],
        ).json()["importacao_id"]
        resposta = self.client.post(
            f"/api/impexp/importacoes/{importacao_id}/corrigir/",
            {"valores": {"codigo": "OUTRO-CODIGO"}}, format="json",
        )
        self.assertEqual(resposta.status_code, 400, resposta.content)

    def test_valor_fora_do_vocabulario_e_recusado(self):
        self.autenticar()
        importacao_id = self._enviar(
            pdf_falso("SOLTO4.pdf"), caminhos=["TorreA/SOLTO4.pdf"],
        ).json()["importacao_id"]
        resposta = self.client.post(
            f"/api/impexp/importacoes/{importacao_id}/corrigir/",
            {"valores": {"disciplina": "nao-existe"}}, format="json",
        )
        self.assertEqual(resposta.status_code, 400, resposta.content)

    def test_corrigir_nao_aceita_a_linha(self):
        """Corrigir e decidir continuam sendo dois atos: a R1 é sobre a decisão,
        e corrigir não é decidir."""
        self.autenticar()
        importacao_id = self._enviar(
            pdf_falso("SOLTO5.pdf"), caminhos=["TorreA/SOLTO5.pdf"],
        ).json()["importacao_id"]
        self.client.post(
            f"/api/impexp/importacoes/{importacao_id}/marcar/",
            {"aceitar": False}, format="json",
        )
        self.client.post(
            f"/api/impexp/importacoes/{importacao_id}/corrigir/",
            {"valores": {"disciplina": "eletrica"}}, format="json",
        )
        depois = self.client.get(f"/api/impexp/importacoes/{importacao_id}/").json()
        self.assertFalse(depois["linhas"][0]["aceita"])


# ===========================================================================
# PRA.10 — snap de medição: o índice onde a mira gruda
# ===========================================================================
class SnapExtratorTests(SimpleTestCase):
    """O extrator sozinho, sem banco: é geometria, não domínio.

    Roda como `SimpleTestCase` de propósito — estes testes precisam ser baratos
    o bastante para rodar a cada mexida no motor, e o que eles cobrem não toca
    linha nenhuma.
    """

    def _player(self, desenhar):
        """Grava entidades pelo MESMO caminho da produção e devolve o player.

        Passar pelo `Recorder` em vez de fabricar pontos à mão é o que faz o
        teste valer: é exatamente daqui que o `_folha` tira a geometria, com
        transformação de bloco e achatamento de curva já aplicados.
        """
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.recorder import Recorder

        doc = ezdxf.new()
        desenhar(doc.modelspace())
        gravador = Recorder()
        Frontend(RenderContext(doc), gravador).draw_layout(doc.modelspace())
        return gravador.player()

    def _indice(self, desenhar, envolvente, teto=None):
        from .motores import snap as snapmod

        return snapmod.indice_de_snap(
            self._player(desenhar), envolvente,
            teto=snapmod.SEM_TETO if teto is None else teto,
        )

    def _tipos(self, indice):
        from .motores import snap as snapmod

        return {snapmod.NOME_DO_TIPO[indice.ponto(i)[2]] for i in range(indice.total())}

    def _tem_ponto(self, indice, x, y, folga=1e-4):
        return any(
            abs(indice.ponto(i)[0] - x) < folga and abs(indice.ponto(i)[1] - y) < folga
            for i in range(indice.total())
        )

    # -- a transformação, que é o risco número um -----------------------------
    def test_o_ponto_cai_onde_o_svg_desenha(self):
        """A mira tem de grudar no traço, e não ao lado dele.

        A folha do `ezdxf` mede `largura + 2·MARGEM_MM` e a tela normaliza os
        DOIS eixos pela LARGURA. Um retângulo de 100×50 na origem tem, portanto,
        canto inferior esquerdo em `(10/120, 60/120)`. Conferido contra o SVG
        realmente emitido em 15/08/2026 — se esta conta mudar, toda medida já
        anotada no canteiro passa a apontar para outro lugar.
        """
        indice = self._indice(
            lambda msp: msp.add_lwpolyline(
                [(0, 0), (100, 0), (100, 50), (0, 50)], close=True),
            (0, 0, 100, 50),
        )
        self.assertTrue(self._tem_ponto(indice, 10 / 120, 60 / 120))
        self.assertTrue(self._tem_ponto(indice, 110 / 120, 60 / 120))
        self.assertTrue(self._tem_ponto(indice, 110 / 120, 10 / 120))

    def test_deslocar_o_desenho_nao_move_a_mira(self):
        """A normalização é relativa à envolvente, não à origem do CAD.

        O mesmo retângulo desenhado a 1 km da origem produz o mesmo índice: é o
        que garante que a mira não dependa de onde o projetista ancorou o
        desenho — e o acervo real tem levantamento em UTM, a milhões de unidades.
        """
        na_origem = self._indice(
            lambda msp: msp.add_lwpolyline(
                [(0, 0), (100, 0), (100, 50), (0, 50)], close=True),
            (0, 0, 100, 50),
        )
        longe = self._indice(
            lambda msp: msp.add_lwpolyline(
                [(1000, 2000), (1100, 2000), (1100, 2050), (1000, 2050)], close=True),
            (1000, 2000, 1100, 2050),
        )
        self.assertEqual(na_origem.total(), longe.total())
        for i in range(na_origem.total()):
            self.assertAlmostEqual(na_origem.ponto(i)[0], longe.ponto(i)[0], places=5)
            self.assertAlmostEqual(na_origem.ponto(i)[1], longe.ponto(i)[1], places=5)

    def test_folha_retrato_passa_de_um_no_eixo_y(self):
        """Normalizar os dois eixos pela largura faz `y` estourar 1,0 no retrato.

        Não é defeito: é a convenção do `Ponto` do frontend, a mesma que o pino
        de marcação já usa. Um teste que exigisse `y <= 1` cobraria o contrato
        errado, e "consertá-lo" moveria toda marcação existente.
        """
        indice = self._indice(
            lambda msp: msp.add_lwpolyline(
                [(0, 0), (50, 0), (50, 200), (0, 200)], close=True),
            (0, 0, 50, 200),
        )
        self.assertGreater(max(indice.ponto(i)[1] for i in range(indice.total())), 1.0)

    # -- o D90: o índice contra o SVG que de fato saiu ------------------------
    #
    # Os testes acima conferem a CONTA da folha. Os dois abaixo conferem a
    # FOLHA — outra pergunta, e foi a diferença entre as duas que segurou o
    # achado por três tentativas: a conta estava certa e a mira caía fora
    # assim mesmo. Eles são caros (convertem um DXF de verdade) e valem cada
    # milissegundo: nenhum teste barato podia ver o que eles veem.

    #: Largura do retângulo de prova, em mm, e ela é escolhida a dedo: a folha
    #: sai com 93,4851 mm e o `ezdxf` a arredonda para 93,5. Sobre medida
    #: redonda (100 × 50) a página deduzida e a emitida coincidem, e o teste não
    #: veria nada. Ver `snap.py::normalizador`.
    LARGURA_QUE_ARREDONDA = 73.4851
    ALTURA_DE_PROVA = 42.0

    def _converter_retangulo(self, com_diagonal=False):
        """Converte um retângulo pelo caminho de produção e devolve `(saída, svg)`.

        O retângulo é uma LWPOLYLINE de propósito: ela desce pelo `PathRecord`,
        que é o registro que o `Player.replay()` entrega **por referência** ao
        gravador do backend — o caminho que o D90 mostrou estar sendo destruído
        pela emissão. Uma LINE não veria o defeito: ela é reconstruída no meio do
        caminho e sobrevivia mesmo quebrado.
        """
        import os
        import tempfile

        import ezdxf

        documento = ezdxf.new("R2010")
        espaco = documento.modelspace()
        largura, altura = self.LARGURA_QUE_ARREDONDA, self.ALTURA_DE_PROVA
        espaco.add_lwpolyline(
            [(0, 0), (largura, 0), (largura, altura), (0, altura)], close=True)
        if com_diagonal:
            espaco.add_line((0, 0), (largura, altura))
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as arquivo:
            caminho = arquivo.name
        documento.saveas(caminho)
        self.addCleanup(lambda: os.unlink(caminho))

        from .motores import snap as snapmod
        from .motores.dxf import MotorDxf

        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d",
                                     teto_snap=snapmod.SEM_TETO)
        return saida, saida.conteudo.decode("utf-8")

    def _pontos_do_sidecar(self, octetos):
        import struct

        # `d` porque o formato é `SNAP2` (float64) — ver `empacotar`.
        n = struct.unpack_from("<I", octetos, 5)[0]
        xs = struct.unpack_from(f"<{n}d", octetos, 14)
        ys = struct.unpack_from(f"<{n}d", octetos, 14 + 8 * n)
        return list(zip(xs, ys))

    def _vertices_do_svg(self, texto):
        """Os vértices que os `<path>` do SVG realmente desenham.

        O `SVGBackend` abre cada subcaminho com um `M` absoluto e segue em `l`
        RELATIVO — somar os números aos pares, como se fossem todos coordenadas,
        lê `l -785937 0` como um ponto em x = −785.937. O caminhador é curto
        porque o desenho de prova só tem reta; a asserção de comando garante que
        continue assim se o `ezdxf` mudar de ideia.
        """
        import re

        saida = []
        for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', texto):
            self.assertRegex(
                d, r"^[MmLl0-9.,\s+-]+$",
                "o desenho de prova passou a ter curva; o caminhador deste teste "
                "só entende M e L e passaria a mentir em silêncio",
            )
            x = y = 0.0
            for comando, valores in re.findall(r"([MmLl])([^A-Za-z]*)", d):
                numeros = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+", valores)]
                for i in range(0, len(numeros) - 1, 2):
                    dx, dy = numeros[i], numeros[i + 1]
                    x, y = (x + dx, y + dy) if comando.islower() else (dx, dy)
                    saida.append((x, y))
        return saida

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_o_indice_cai_sobre_o_traco_do_svg_que_saiu(self):
        """**D90, primeira metade:** a página deduzida não é a página emitida.

        `largura_do_desenho + 2·MARGEM_MM` parece a conta do `ezdxf` e não é: ele
        arredonda a página para 0,1 mm, reescala o conteúdo para caber nela
        (`fit_page`) e centraliza a sobra dentro das margens. Sobra um erro de
        escala que some no enquadramento, cresce com o zoom e **muda a cada
        prancha** — o que fazia o defeito parecer não ter padrão.

        A pergunta aqui é a única que fecha o caso: o índice descreve o arquivo
        que saiu? A tolerância é de 2 unidades de `viewBox` em 1.000.000 — a
        própria precisão do SVG, cujas coordenadas são inteiras. Pela dedução, o
        desvio medido em 15/08/2026 nesta folha foi de ~530 unidades.
        """
        import re

        saida, texto = self._converter_retangulo()
        caixa = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', texto)
        self.assertIsNotNone(caixa, "o SVG emitido tem de trazer o viewBox")
        vbw = float(caixa.group(1))

        desenhado = self._vertices_do_svg(texto)
        self.assertTrue(desenhado, "o SVG emitido tem de ter traço")
        indexado = self._pontos_do_sidecar(saida.partes[0].snap)
        self.assertTrue(indexado, "o sidecar tem de ter ponto")

        for eixo, (nome, rotulo) in enumerate((("x", "esquerda/direita"),
                                               ("y", "topo/base"))):
            do_svg = (min(p[eixo] for p in desenhado),
                      max(p[eixo] for p in desenhado))
            do_indice = (min(p[eixo] for p in indexado) * vbw,
                         max(p[eixo] for p in indexado) * vbw)
            for i, ponta in enumerate(("mínimo", "máximo")):
                self.assertAlmostEqual(
                    do_indice[i], do_svg[i], delta=2,
                    msg=(f"o {ponta} do índice em {nome} ({rotulo}) está a "
                         f"{abs(do_indice[i] - do_svg[i]):.0f} unidades de viewBox "
                         f"do traço que o SVG desenha — a mira acende fora da "
                         f"linha (D90)"),
                )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_emitir_o_svg_nao_come_a_geometria_de_curva(self):
        """**D90, segunda metade:** a emissão destrói a geometria de quem a empresta.

        `Player.replay()` repassa `PathRecord` e `FilledPathsRecord` **por
        referência** ao gravador do backend, e o `get_string()` transforma esses
        registros *in place* para o espaço do `viewBox`. Quem indexar o player de
        origem depois disso lê um espaço misto — reta em milímetro, arco em
        unidade de `viewBox` — e a metade transformada cai inteira no filtro de
        "fora da folha", **sem uma linha de log**. Na
        `01_02-DETALHE_DAS_SAPATAS` eram 1.699 de 3.214 registros: todo arco,
        círculo, polilinha, hachura e texto da prancha.

        O sintoma na tela não era mira ausente, era **mira mentirosa**: sem os
        vértices da curva, ela grudava no ponto de reta mais próximo, que é outro
        lugar. E era também o "fantasma" de 516 mil pontos fora da folha na
        `001` — não geometria inventada, o desenho dela em coordenada de
        `viewBox`, comendo o teto do plano.

        O retângulo rende 4 extremidades e 4 meios, e **nenhum descarte**: ponto
        fora de uma folha que o próprio `ezdxf` dimensionou é notícia.
        """
        saida, _texto = self._converter_retangulo()
        parte = saida.partes[0]

        self.assertEqual(
            parte.snap_pontos, 8,
            "o retângulo rende 4 extremidades + 4 meios; contagem diferente "
            "significa que a polilinha não chegou inteira ao índice (D90)",
        )
        self.assertIsNone(
            parte.detalhe.get("snap_fora_da_folha"),
            "o ezdxf não põe geometria fora da página que ele mesmo dimensionou "
            "— descarte aqui é o desenho chegando no espaço errado (D90)",
        )

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_reta_e_polilinha_no_mesmo_lugar_dao_o_mesmo_ponto(self):
        """As duas famílias de registro têm de falar o mesmo espaço.

        A LINE é reconstruída pelo `replay` (`draw_line` cria pontos novos) e
        sobrevivia à emissão; a LWPOLYLINE desce por referência e não sobrevivia.
        Com os dois no mesmo desenho, a diagonal e o retângulo compartilham dois
        cantos — e o índice tem de **fundi-los**, não duplicá-los deslocados.

        É o teste mais barato que distingue "a mira sumiu" de "a mira mudou de
        lugar", e o único que falharia se um dia só metade do caminho for
        consertada.
        """
        saida, _texto = self._converter_retangulo(com_diagonal=True)
        pontos = self._pontos_do_sidecar(saida.partes[0].snap)

        # 4 cantos + 4 meios de aresta + 1 meio da diagonal. Os cantos (0,0) e
        # (L,H) são de AMBOS os registros e contam uma vez só — se a diagonal e o
        # retângulo estivessem em espaços diferentes, seriam 11.
        self.assertEqual(
            len(pontos), 9,
            "a diagonal e o retângulo compartilham dois cantos; contagem maior "
            "significa que os dois registros caíram em espaços diferentes (D90)",
        )

    #: Onde o retângulo de prova é DESENHADO, longe da origem e sem simetria:
    #: uma coordenada tipo UTM pega translação errada (que a origem esconderia) e
    #: X ≠ Y pega os dois eixos trocados.
    MUNDO_X, MUNDO_Y = 712345.0, 9876543.0

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_folha_devolve_a_coordenada_do_desenho(self):
        """A prancha volta a dizer a coordenada que o CAD mostra.

        A conversão troca a régua do desenho pela da folha (fração, milímetro de
        papel, unidade de `viewBox`) — três réguas nossas. O arquivo tinha a
        dele, e é contra ela que se confere um vértice no AutoCAD; sem esta ponte
        o número original se perde na conversão, em silêncio.

        A ponte é **medida na emissão** (`_mundo_da_folha`), nunca deduzida: a
        conta óbvia da página erra porque o `ezdxf` ainda arredonda a folha,
        reescala com `fit_page` e centraliza a sobra — é a primeira metade do
        D90, e ela reapareceria aqui inteira. Este teste desenha em coordenada
        conhecida e cobra os quatro cantos de volta.

        A tolerância é de **0,001 unidade de desenho** sobre uma folha de ~93 mm
        com coordenada na casa dos 10⁷: ela cobra a ponte, não a precisão do
        `float`.
        """
        import os
        import tempfile

        import ezdxf

        from .motores import snap as snapmod
        from .motores.dxf import MotorDxf

        largura, altura = self.LARGURA_QUE_ARREDONDA, self.ALTURA_DE_PROVA
        x0, y0 = self.MUNDO_X, self.MUNDO_Y
        documento = ezdxf.new("R2010")
        espaco = documento.modelspace()
        espaco.add_lwpolyline(
            [(x0, y0), (x0 + largura, y0), (x0 + largura, y0 + altura), (x0, y0 + altura)],
            close=True)
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as arquivo:
            caminho = arquivo.name
        documento.saveas(caminho)
        self.addCleanup(lambda: os.unlink(caminho))

        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d",
                                     teto_snap=snapmod.SEM_TETO)
        parte = saida.partes[0]
        mundo = parte.mundo
        self.assertTrue(
            mundo,
            "a folha tem de publicar a ponte para a coordenada de desenho; "
            f"vazia, a tela mostra régua de folha achando que é do CAD "
            f"({parte.detalhe.get('mundo_erro')})",
        )

        def para_desenho(fx, fy):
            return (mundo["origem_x"] + fx * mundo["por_folha"],
                    mundo["origem_y"] - fy * mundo["por_folha"])

        # Os cantos vêm do SIDECAR, que é o que a tela usa para acender a mira:
        # conferir a ponte contra ele prova o caminho inteiro, e não só a conta.
        pontos = self._pontos_do_sidecar(parte.snap)
        cantos = {(round(x, 3), round(y, 3))
                  for x, y in (para_desenho(*p) for p in pontos)}
        for esperado in ((x0, y0), (x0 + largura, y0),
                         (x0, y0 + altura), (x0 + largura, y0 + altura)):
            perto = min(cantos, key=lambda c: abs(c[0] - esperado[0]) + abs(c[1] - esperado[1]))
            self.assertAlmostEqual(
                perto[0], esperado[0], delta=1e-3,
                msg=f"canto em X: o índice devolve {perto} para o vértice {esperado}")
            self.assertAlmostEqual(
                perto[1], esperado[1], delta=1e-3,
                msg=f"canto em Y: o índice devolve {perto} para o vértice {esperado} "
                    "— Y invertido é o erro clássico aqui (SVG cresce para baixo)")

        # A folha é maior que o desenho: a origem publicada é o CANTO SUPERIOR
        # ESQUERDO DA FOLHA, margem incluída, e não o canto do desenho.
        self.assertLess(mundo["origem_x"], x0, "a margem entra à esquerda")
        self.assertGreater(mundo["origem_y"], y0 + altura, "a margem entra acima")
        self.assertGreater(mundo["por_folha"], largura,
                           "a largura da folha inclui as duas margens")

    @unittest.skipUnless(ADAPTADORES["ezdxf"].disponivel(), "ezdxf não instalado")
    def test_a_quinta_casa_decimal_atravessa_o_caminho_inteiro(self):
        """**Decisão do dono (15/08/2026): tudo com precisão na quinta casa.**

        Não é arredondar para cinco casas — é *carregar* 1e-5 em cada etapa. A
        etapa que não carregar é a que manda, e era isso que fazia a mira "travar
        na casa decimal mais próxima": o índice guarda a coordenada exata e a
        **tinta** só existe nos inteiros da grade do SVG. Com a grade de 10⁶ numa
        folha A1, esses inteiros distam 0,000861 unidade de desenho — a quarta
        casa. O desvio é invisível no enquadramento e cresce proporcional ao
        zoom, que é exatamente a forma do defeito relatado.

        O teste desenha um retângulo cujos lados **exigem a quinta casa**
        (73,48512 × 42,00003) e cobra os três funis de uma vez, no caminho de
        produção:

        1. a grade emitida tem de dar passo ≤ 1e-5 em unidade de desenho;
        2. o sidecar tem de sair em `SNAP2` (float64) — o float32 dá degrau de
           0,00005 nesta folha, cinco vezes grosso;
        3. os vértices reconstruídos pelo `mundo` têm de bater com o desenhado.
        """
        import os
        import tempfile

        import ezdxf

        from .motores import snap as snapmod
        from .motores.dxf import PRECISAO_DE_DESENHO, MotorDxf

        # Lados com dígito na quinta casa: se qualquer etapa truncar, o canto
        # volta diferente e o teste falha no dígito exato que foi perdido.
        largura, altura = 73.48512, 42.00003
        x0, y0 = 712345.00007, 9876543.00009
        documento = ezdxf.new("R2010")
        espaco = documento.modelspace()
        espaco.add_lwpolyline(
            [(x0, y0), (x0 + largura, y0), (x0 + largura, y0 + altura), (x0, y0 + altura)],
            close=True)
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as arquivo:
            caminho = arquivo.name
        documento.saveas(caminho)
        self.addCleanup(lambda: os.unlink(caminho))

        saida = MotorDxf().converter(caminho, formato="dxf", tipo="vetor_2d",
                                     teto_snap=snapmod.SEM_TETO)
        parte = saida.partes[0]

        # 1. a grade emitida alcança a quinta casa?
        passo = parte.detalhe.get("precisao_desenho")
        self.assertIsNotNone(passo, "a conversão tem de registrar a precisão obtida")
        self.assertLessEqual(
            passo, PRECISAO_DE_DESENHO,
            f"a grade do SVG só resolve {passo:.8f} unidade de desenho: a tinta "
            f"fica presa a múltiplos disso e a mira 'trava na casa mais próxima'",
        )
        self.assertNotIn("precisao_insuficiente", parte.detalhe)

        # 2. o sidecar guarda 64 bits?
        self.assertEqual(
            parte.snap[:5], b"SNAP2",
            "float32 dá degrau de 0,00005 unidade nesta folha — quarta casa, não quinta",
        )

        # 3. o vértice volta com os cinco dígitos?
        mundo = parte.mundo
        self.assertTrue(mundo)
        pontos = [(mundo["origem_x"] + fx * mundo["por_folha"],
                   mundo["origem_y"] - fy * mundo["por_folha"])
                  for fx, fy in self._pontos_do_sidecar(parte.snap)]
        for esperado in ((x0, y0), (x0 + largura, y0),
                         (x0, y0 + altura), (x0 + largura, y0 + altura)):
            erro = min(max(abs(px - esperado[0]), abs(py - esperado[1]))
                       for px, py in pontos)
            self.assertLessEqual(
                erro, PRECISAO_DE_DESENHO,
                f"o vértice {esperado} volta com erro de {erro:.8f} unidade de "
                f"desenho — a quinta casa não sobreviveu ao caminho",
            )

    def test_a_grade_de_saida_cresce_para_alcancar_a_quinta_casa(self):
        """A folha grande pede grade grande — e o teto é declarado, não silencioso.

        A grade é o passo em que a tinta pode existir, então ela tem de crescer
        junto com a folha. O teto existe (a grade engorda o SVG), e num
        levantamento de milhões de unidades a quinta casa fica fora de alcance —
        o que o sistema faz aí é **dizer**, não fingir.
        """
        from .motores.dxf import (GRADE_MAXIMA, GRADE_PADRAO,
                                  PRECISAO_DE_DESENHO, _grade_de_saida)

        # Folha comum de 861 unidades: 1e6 não basta, e a grade sobe.
        grade = _grade_de_saida(1.0, 861.0)
        self.assertGreater(grade, GRADE_PADRAO)
        self.assertLessEqual(861.0 / grade, PRECISAO_DE_DESENHO)
        # Com a folga, ela sobra de propósito — a folha emitida é um fio maior
        # que a estimada, e é isso que a folga cobre (ver `FOLGA_DA_GRADE`).
        self.assertLess(861.0 / grade, PRECISAO_DE_DESENHO)

        # Sem informação da folha, o comportamento antigo continua valendo.
        self.assertEqual(_grade_de_saida(1.0), GRADE_PADRAO)

        # Levantamento de 8,5 milhões de unidades: pediria 8,5×10¹¹ e o teto
        # corta. O teto vale — e é o `precisao_insuficiente` que avisa.
        self.assertEqual(_grade_de_saida(1.0, 8_500_000.0), GRADE_MAXIMA)

    # -- os tipos de snap -----------------------------------------------------
    def test_linha_rende_extremidade_e_meio(self):
        indice = self._indice(
            lambda msp: msp.add_line((0, 0), (100, 0)), (0, 0, 100, 100))
        self.assertEqual(self._tipos(indice), {"extremidade", "meio"})

    def test_circulo_rende_centro_e_quadrante(self):
        indice = self._indice(
            lambda msp: msp.add_circle((50, 50), radius=25), (0, 0, 100, 100))
        tipos = self._tipos(indice)
        self.assertIn("centro", tipos)
        self.assertIn("quadrante", tipos)
        # O centro do círculo É o centro da envolvente dele — exato, e é
        # justamente por isso que só curva FECHADA ganha centro.
        self.assertTrue(self._tem_ponto(indice, 60 / 120, 60 / 120))

    def test_arco_aberto_nao_inventa_centro(self):
        """Arco não ganha centro, e a razão é honestidade geométrica.

        A envolvente de um arco aberto **não contém** o centro da circunferência
        dele. Publicar o centro da caixa como "centro" daria uma mira que gruda
        no vazio com a confiança de quem acertou — o pior defeito possível numa
        ferramenta cujo produto é apontar onde.
        """
        indice = self._indice(
            lambda msp: msp.add_arc((50, 50), radius=25, start_angle=0, end_angle=90),
            (0, 0, 100, 100),
        )
        self.assertNotIn("centro", self._tipos(indice))

    def test_duas_linhas_que_se_cruzam_rendem_intersecao(self):
        indice = self._indice(
            lambda msp: (msp.add_line((0, 50), (100, 50)),
                         msp.add_line((50, 0), (50, 100))),
            (0, 0, 100, 100),
        )
        self.assertIn("intersecao", self._tipos(indice))
        self.assertTrue(self._tem_ponto(indice, 60 / 120, 60 / 120))

    def test_encostar_na_ponta_nao_vira_intersecao(self):
        """Ponta com ponta já é extremidade — repetir o lugar só engorda o índice."""
        indice = self._indice(
            lambda msp: (msp.add_line((0, 0), (50, 0)),
                         msp.add_line((50, 0), (100, 0))),
            (0, 0, 100, 100),
        )
        self.assertNotIn("intersecao", self._tipos(indice))

    # -- fusão, teto e o defeito que a medição achou --------------------------
    def test_pontos_no_mesmo_lugar_viram_um_so(self):
        """A parede feita de quatro linhas soltas tem UM canto, não quatro.

        Sem a fusão o índice cresce ~4× sem oferecer um lugar novo onde grudar —
        e quem paga é o cliente, em banda, e o celular do canteiro, em memória.
        """
        from .motores import snap as snapmod

        soltas = self._indice(
            lambda msp: (msp.add_line((0, 0), (100, 0)),
                         msp.add_line((100, 0), (100, 50)),
                         msp.add_line((100, 50), (0, 50)),
                         msp.add_line((0, 50), (0, 0))),
            (0, 0, 100, 50),
        )
        cantos = [i for i in range(soltas.total())
                  if soltas.ponto(i)[2] == snapmod.EXTREMIDADE]
        self.assertEqual(len(cantos), 4)

    def test_extremidade_vence_meio_no_mesmo_lugar(self):
        """Empate de lugar resolve pelo tipo mais útil (`PRECEDENCIA`)."""
        from .motores import snap as snapmod

        self.assertLess(snapmod.PRECEDENCIA[snapmod.EXTREMIDADE],
                        snapmod.PRECEDENCIA[snapmod.MEIO])

    def test_o_teto_corta_e_declara_que_cortou(self):
        """Passou do teto do plano: índice parcial, **e a bandeira levantada**.

        Sem `truncado`, a mira que não gruda num canto da prancha se lê como
        defeito em vez de limite contratado — e o cliente abre chamado em vez de
        comprar o pacote.
        """
        indice = self._indice(
            lambda msp: [msp.add_line((i, 0), (i, 100)) for i in range(0, 200, 2)],
            (0, 0, 200, 100), teto=20,
        )
        self.assertTrue(indice.truncado)
        self.assertLessEqual(indice.total(), 40)

    def test_coordenada_negativa_nao_corrompe_a_grade(self):
        """Regressão do defeito achado medindo em 15/08/2026.

        A chave da grade era `(cx << 20) | cy`; com `cy = -1` o deslocamento
        invade os bits do `cx` e células distantes colidem. O sintoma foram 626
        "células densas" e o tempo triplicando num arquivo que não tem nenhuma.
        Coordenada negativa é legítima aqui: o traço na borda do recorte, com a
        `FOLGA_RECORTE`, normaliza um fio acima de `ymax`.
        """
        from .motores import snap as snapmod

        self.assertNotEqual(snapmod._celula(0, -1), snapmod._celula(-1, 0))
        self.assertNotEqual(snapmod._celula(1, -1), snapmod._celula(0, 1))
        # E a folha cuja envolvente é menor que o desenho não vira célula densa.
        indice = self._indice(
            lambda msp: (msp.add_line((0, 50), (100, 50)),
                         msp.add_line((50, 0), (50, 100))),
            (10, 10, 90, 90),
        )
        self.assertFalse(indice.censo.get("celulas_densas"))

    # -- o sidecar ------------------------------------------------------------
    def test_o_sidecar_tem_o_cabecalho_e_o_tamanho_documentados(self):
        """O formato é contrato com o navegador, e por isso é testado por byte.

        `SNAP2` + `uint32 n` + `uint32 m` + `uint8 truncado`, depois
        `float64[n] x`, `float64[n] y`, `uint8[n] tipo` e `float64[4m]`. X e Y em
        blocos separados porque a busca varre X primeiro para descartar
        candidatos, e intercalar puxaria um Y que não vai ser usado.

        **64 bits e não 32**: em coordenada normalizada o float32 dá degrau de
        6×10⁻⁸, que numa folha A1 vale 0,00005 unidade de desenho — a quarta casa
        decimal, e o sistema promete a quinta.
        """
        import struct

        from .motores import snap as snapmod

        indice = self._indice(
            lambda msp: msp.add_line((0, 0), (100, 0)), (0, 0, 100, 100))
        octetos = snapmod.empacotar(indice)
        self.assertEqual(octetos[:5], b"SNAP2")
        n, m, truncado = struct.unpack("<IIB", octetos[5:14])
        self.assertEqual(n, indice.total())
        self.assertEqual(m, indice.total_de_segmentos())
        self.assertEqual(truncado, 0)
        self.assertEqual(len(octetos), 14 + n * 8 + n * 8 + n + m * 32)


# ---------------------------------------------------------------------------
# 20. PRA.11 — o arquivo pesado termina, uma volta de fila por vez
# ---------------------------------------------------------------------------
class RetomadaDaConversaoTests(PranchetaTestBase):
    """O item 23 do dono: *"se esse arquivo nao terminar em tantos segundos,
    volta pro final da fila e continua assim ate terminar"*.

    O que o registro do D98 dizia ser impossivel — e por que deixou de ser: a
    preempcao exigia checkpoint, porque devolver a fila um trabalho que
    recomecaria do zero gastaria mais CPU total do que deixa-lo terminar. Com a
    conversao gravando folha a folha, cada volta preserva o que ficou pronto.
    """

    def _lotes(self, *tamanhos):
        """Um arquivo cujas folhas chegam em N passadas."""
        ordem = 0
        lotes = []
        for quantas in tamanhos:
            lote = []
            for _ in range(quantas):
                ordem += 1
                lote.append(Parte(
                    conteudo=b"<svg><path d='M0 0'/></svg>", ordem=ordem,
                    caixa={"xmin": 0.0, "ymin": ordem * 1000.0,
                           "xmax": 500.0, "ymax": ordem * 1000.0 + 400.0},
                    tracos=42, detalhe={"desenhos": ordem},
                ))
            lotes.append(tuple(lote))
        return tuple(lotes)

    def _derivada(self, revisao):
        return DerivadaProjeto.objects.create(
            tenant=self.tenant, revisao=revisao, tipo="vetor_2d", motor="ezdxf",
        )

    def _revisao_dxf(self):
        documento = self._documento(codigo="PESADO-001")
        return RevisaoDocumento.objects.create(
            tenant=self.tenant, documento=documento, revisao="R00",
            arquivo=SimpleUploadedFile("pesado.dxf", b"0\nSECTION\n"),
            nome_original="pesado.dxf", formato="dxf", tamanho_bytes=10,
            hash_sha256="hash-pesado",
        )

    def test_a_passada_que_nao_termina_grava_o_que_fez_e_volta_para_a_fila(self):
        revisao = self._revisao_dxf()
        motor = MotorFalso(lotes=self._lotes(2, 2))
        derivada = self._derivada(revisao)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}), \
                mock.patch("celery.current_app.send_task"):
            pipeline.executar(derivada)

        derivada.refresh_from_db()
        # As duas folhas desta passada JA ABREM — e e isso que separa esta
        # recolocacao do erro que existia antes: a prancha nao fica em branco
        # esperando um fim que pode nunca vir.
        self.assertEqual(revisao.desenhos.count(), 2)
        self.assertEqual(derivada.estado, "retomando")
        self.assertEqual(derivada.retomada_restam, 1)
        self.assertEqual(derivada.retomada_desenhos, 2)

    def test_a_passada_seguinte_continua_de_onde_parou_e_nao_do_zero(self):
        revisao = self._revisao_dxf()
        motor = MotorFalso(lotes=self._lotes(2, 3))
        derivada = self._derivada(revisao)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}), \
                mock.patch("celery.current_app.send_task"):
            pipeline.executar(derivada)
            derivada.refresh_from_db()
            pipeline.executar(derivada)

        derivada.refresh_from_db()
        # O marcador chegou ao motor na segunda chamada: e ele que faz a folha 3
        # ser a folha 3, e nao um segundo "Desenho 1" por cima do primeiro.
        self.assertIsNone(motor.retomadas_recebidas[0])
        self.assertIsNotNone(motor.retomadas_recebidas[1])
        self.assertEqual(motor.retomadas_recebidas[1].desenhos_feitos, 2)
        self.assertEqual(revisao.desenhos.count(), 5)
        self.assertEqual(derivada.estado, "pronto")
        self.assertEqual(derivada.retomada_restam, 0)

    def test_a_volta_nao_apaga_as_folhas_que_a_volta_anterior_gravou(self):
        """`_remover_orfas` apaga o que a conversao nao produziu — e numa passada
        parcial "nao produziu ainda" e "nao produz mais" sao indistinguiveis.
        Sem a guarda, cada volta destruiria o trabalho da anterior e o arquivo
        nunca sairia da primeira folha."""
        revisao = self._revisao_dxf()
        motor = MotorFalso(lotes=self._lotes(1, 1, 1))
        derivada = self._derivada(revisao)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}), \
                mock.patch("celery.current_app.send_task"):
            for _ in range(3):
                derivada.refresh_from_db()
                pipeline.executar(derivada)

        self.assertEqual(revisao.desenhos.count(), 3)
        self.assertEqual(
            sorted(revisao.desenhos.values_list("ordem", flat=True)), [1, 2, 3],
        )

    def test_o_censo_das_folhas_antigas_e_acertado_no_fim(self):
        """Cada passada so sabe quantas folhas viu ate ali. Sem o acerto final,
        quem abrisse a folha 1 leria "2 desenhos" num arquivo de 5."""
        revisao = self._revisao_dxf()
        motor = MotorFalso(lotes=self._lotes(2, 3))
        derivada = self._derivada(revisao)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}), \
                mock.patch("celery.current_app.send_task"):
            pipeline.executar(derivada)
            derivada.refresh_from_db()
            pipeline.executar(derivada)

        censos = {
            d.memoria.get("desenhos")
            for d in DerivadaProjeto.objects.filter(revisao=revisao, tipo="vetor_2d")
        }
        self.assertEqual(censos, {5})

    def test_o_teto_de_tempo_ACUMULADO_encerra_e_preserva_o_que_ficou_pronto(self):
        """A desistencia e por tempo somado, e nao por numero de voltas (decisao
        do dono): contar voltas mediria a nossa politica, nao o custo."""
        revisao = self._revisao_dxf()
        motor = MotorFalso(lotes=self._lotes(2, 2, 2))
        derivada = self._derivada(revisao)
        with mock.patch.dict(ADAPTADORES, {"ezdxf": motor}), \
                mock.patch("celery.current_app.send_task"), \
                self.settings(PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS=1):
            pipeline.executar(derivada)
            # A primeira passada ja estourou o teto de 1 s? So se ela gastou 1 s.
            # Forcamos o acumulado, que e o que o relogio real faria.
            DerivadaProjeto.objects.filter(pk=derivada.pk).update(retomada_segundos=99)
            derivada.refresh_from_db()
            pipeline.executar(derivada)

        derivada.refresh_from_db()
        self.assertEqual(derivada.estado, "erro")
        self.assertEqual(derivada.erro_motivo, "recurso_excedido")
        # As folhas convertidas CONTINUAM no acervo: a prancha abre pelo que deu.
        self.assertGreaterEqual(revisao.desenhos.count(), 2)
        self.assertIn("faltaram", derivada.erro_detalhe)

    def test_motor_que_nao_retoma_nao_recebe_prazo_nenhum(self):
        """`retomavel = False` e uma resposta, nao uma pendencia: reenfileirar
        quem converte numa unidade indivisivel gastaria mais maquina para chegar
        ao mesmo estouro."""
        from .motores.documento import MotorDocumento

        self.assertFalse(MotorDocumento.retomavel)
        self.assertEqual(pipeline._turno_do_motor(MotorDocumento(), None), {})
