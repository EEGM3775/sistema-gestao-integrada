# testes/backend/rh/test_d70_entrega.py
"""D70 — o RH pela porta única: o JSON limpo, o gate certo, a trilha escrita.

**Por que o RH é o arquivo de teste do achado inteiro.** Ele tem os três gates
que o D70 tocou (`rh.documento`, `rh.dado_medico`, `rh.folha`) e é onde o desvio
do mascaramento aparecia inteiro: a 9.C escondia `cpf` e `salario_base` na ficha
enquanto o mesmo payload entregava a URL do PDF que contém os dois em claro.

O que se prova aqui, e não em outro lugar:

1. **nenhuma resposta publica `/media/`** — é a metade do achado que vivia no
   serializer, e a que o gateway sozinho não fechava;
2. **cada arquivo tem o gate do seu conteúdo** — quem lê a ficha não abre o ASO;
3. **tenant vizinho é 404, não 403** — 403 num id que existe confirma que ele
   existe (a regra do `EntregaInvalida`);
4. **o download entra na trilha** (R12/D67), porque é PII de titular saindo.
"""
from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from funcoesimpexp.entrega import url_do_arquivo
from nucleo.models import AuditLog, Tenant, Usuario

from rh.impexp import (
    ESPECIE_ASO,
    ESPECIE_CTPS,
    ESPECIE_DOCUMENTO,
    ESPECIE_HOLERITE,
    RECURSO_ASO,
    RECURSO_DOCUMENTOS,
    RECURSO_HOLERITE,
)
from rh.models import ASOFuncionario, Cargo, DocumentoFuncionario, FolhaPagamento, Funcionario

PDF = b"%PDF-1.4\nconteudo sigiloso\n"

#: O conjunto cheio do RH. Cada teste tira o que quer provar que falta.
PERMS_RH = (
    "rh.funcionario.view", "rh.funcionario.edit", "rh.cpf.view",
    "rh.documento.view", "rh.documento.edit",
    "rh.dado_medico.view", "rh.dado_medico.edit",
    "rh.folha.view", "rh.folha.edit",
)


def _pdf(nome):
    return SimpleUploadedFile(nome, PDF, content_type="application/pdf")


class D70RhTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="rh-a", nome="Construtora A")
        cls.tenant_b = Tenant.objects.create(slug="rh-b", nome="Construtora B")
        cls.user = Usuario.objects.create(username="rh_a", tenant=cls.tenant)
        cls.cargo = Cargo.objects.create(
            tenant=cls.tenant, nome_cargo="Pedreiro", departamento="Obra",
        )

    def setUp(self):
        super().setUp()
        self.funcionario = self._funcionario()

    def _funcionario(self, tenant=None):
        tenant = tenant or self.tenant
        # O CPF é único **por tenant**, então o do vizinho pode ser igual — mas
        # variar pelo slug deixa a falha legível quando um teste cruzar os dois.
        return Funcionario.objects.create(
            tenant=tenant, cargo=self.cargo if tenant == self.tenant else None,
            nome_completo="José da Silva", cpf=f"111.222.333-{tenant.slug[-2:]}",
            data_nascimento="1990-05-01", genero="masculino",
            endereco_completo="Rua X, 100", data_admissao="2024-01-10",
            salario_base="3200.00",
            carteira_trabalho=_pdf("ctps.pdf"),
        )

    def autenticar(self, perms=PERMS_RH, modules=("rh",), user=None):
        user = user or self.user
        user.iam_modules = list(modules)
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)
        return user

    def _aso(self, funcionario=None):
        funcionario = funcionario or self.funcionario
        return ASOFuncionario.objects.create(
            tenant=funcionario.tenant, funcionario=funcionario,
            tipo_exame="admissional", data_exame="2024-01-05",
            arquivo=_pdf("aso.pdf"),
        )

    def _holerite(self, funcionario=None):
        funcionario = funcionario or self.funcionario
        return FolhaPagamento.objects.create(
            tenant=funcionario.tenant, funcionario=funcionario,
            mes_referencia="2026-07-01", salario_bruto="3200.00",
            salario_liquido="2800.00", holerite=_pdf("holerite.pdf"),
        )

    def _documento(self, funcionario=None):
        funcionario = funcionario or self.funcionario
        return DocumentoFuncionario.objects.create(
            tenant=funcionario.tenant, funcionario=funcionario,
            tipo_documento="rg", nome_documento="RG frente e verso",
            arquivo=_pdf("rg.pdf"),
        )


class NenhumaRespostaPublicaMediaTests(D70RhTestBase):
    """A metade do achado que morava no serializer, e não no nginx."""

    def test_ficha_do_funcionario_nao_publica_caminho_de_media(self):
        """O caso que resume o D70: `cpf` mascarado e a CTPS aberta ao lado.

        Sem `rh.cpf.view` o CPF sai como `•••` — e antes desta fatia o mesmo
        payload trazia `/media/carteiras_trabalho/ctps.pdf`, onde ele está em
        claro e sem gate nenhum.
        """
        self.autenticar(perms=[p for p in PERMS_RH if p != "rh.cpf.view"])
        resposta = self.client.get(f"/api/funcionarios/{self.funcionario.pk}/")
        self.assertEqual(resposta.status_code, 200)

        corpo = json.dumps(resposta.json())
        self.assertNotIn("/media/", corpo, "a ficha ainda publica caminho de /media/")
        self.assertEqual(
            resposta.json()["carteira_trabalho"],
            url_do_arquivo(RECURSO_DOCUMENTOS, ESPECIE_CTPS, self.funcionario.pk),
        )

    def test_aso_holerite_e_documento_saem_pela_porta_unica(self):
        aso, folha, doc = self._aso(), self._holerite(), self._documento()
        self.autenticar()

        casos = [
            (f"/api/asos-funcionarios/{aso.pk}/", "arquivo",
             url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk)),
            (f"/api/folhas-pagamento/{folha.pk}/", "holerite",
             url_do_arquivo(RECURSO_HOLERITE, ESPECIE_HOLERITE, folha.pk)),
            (f"/api/documentos-funcionarios/{doc.pk}/", "arquivo",
             url_do_arquivo(RECURSO_DOCUMENTOS, ESPECIE_DOCUMENTO, doc.pk)),
        ]
        for url, campo, esperado in casos:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertNotIn("/media/", json.dumps(resposta.json()))
                self.assertEqual(resposta.json()[campo], esperado)

    def test_campo_vazio_continua_vazio(self):
        """Sem binário não há URL: um link para arquivo inexistente é 404 anunciado."""
        self.funcionario.carteira_trabalho = None
        self.funcionario.save(update_fields=["carteira_trabalho"])
        self.autenticar()

        resposta = self.client.get(f"/api/funcionarios/{self.funcionario.pk}/")
        self.assertIn(resposta.json()["carteira_trabalho"], (None, ""))


class CadaArquivoTemOGateDoSeuConteudoTests(D70RhTestBase):
    """A segregação do catálogo valendo para o binário, não só para o campo."""

    def test_quem_le_a_ficha_nao_abre_o_aso(self):
        """ASO é dado de saúde: exige `rh.dado_medico.view`, e não a ficha."""
        aso = self._aso()
        self.autenticar(perms=("rh.funcionario.view", "rh.documento.view"))

        resposta = self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk))
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("rh.dado_medico.view", resposta.json()["detail"])

    def test_quem_nao_ve_a_folha_nao_abre_o_holerite(self):
        folha = self._holerite()
        self.autenticar(perms=("rh.funcionario.view", "rh.documento.view"))

        resposta = self.client.get(
            url_do_arquivo(RECURSO_HOLERITE, ESPECIE_HOLERITE, folha.pk))
        self.assertEqual(resposta.status_code, 403)

    def test_com_a_permissao_certa_o_arquivo_sai(self):
        aso = self._aso()
        self.autenticar(perms=("rh.dado_medico.view",))

        resposta = self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b"".join(resposta.streaming_content), PDF)

    def test_sem_o_modulo_rh_contratado_nao_sai(self):
        """O entitlement é cobrado na entrega — o binário é o produto."""
        aso = self._aso()
        self.autenticar(perms=("rh.dado_medico.view",), modules=())

        resposta = self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk))
        self.assertEqual(resposta.status_code, 403)

    def test_sem_token_nao_sai(self):
        aso = self._aso()
        self.client.force_authenticate(user=None)
        self.assertIn(
            self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk)).status_code,
            (401, 403),
        )


class OArquivoDoVizinhoNaoExisteTests(D70RhTestBase):
    """404 e não 403: 403 num id de outro tenant confirma que ele existe."""

    def test_aso_de_outro_tenant_e_404(self):
        alheio = self._aso(funcionario=self._funcionario(tenant=self.tenant_b))
        self.autenticar()

        resposta = self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, alheio.pk))
        self.assertEqual(resposta.status_code, 404)

    def test_id_inexistente_tambem_e_404(self):
        self.autenticar()
        self.assertEqual(
            self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, 99999)).status_code,
            404,
        )

    def test_id_que_nao_e_numero_e_404_e_nao_500(self):
        """Quem monta URL à mão merece 'não encontrei', não traceback."""
        self.autenticar()
        self.assertEqual(
            self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, "abc")).status_code,
            404,
        )


class GuardaCorposDaRespostaTests(D70RhTestBase):
    def test_sai_como_anexo_com_nosniff_e_sem_cache(self):
        """`no-store` é decisão, não descuido — ver `entregar_campo`.

        Substituir o PDF do ASO reescreve o mesmo campo sob o mesmo id, então a
        URL não identifica o conteúdo: prometer `immutable` deixaria um atestado
        de saúde vencido no cache do navegador de quem o abriu.
        """
        aso = self._aso()
        self.autenticar()

        resposta = self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk))
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertTrue(resposta["Content-Disposition"].startswith("attachment"))
        self.assertEqual(resposta["Cache-Control"], "private, no-store")
        self.assertTrue(resposta["Content-Type"].startswith("application/pdf"))


class ATrilhaRegistraQuemLevouTests(D70RhTestBase):
    def test_baixar_o_aso_entra_no_auditlog(self):
        aso = self._aso()
        self.autenticar()
        antes = AuditLog.objects.count()

        self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, aso.pk))

        self.assertEqual(AuditLog.objects.count(), antes + 1)
        linha = AuditLog.objects.order_by("-pk").first()
        self.assertEqual(linha.detalhes["recurso"], RECURSO_ASO)
        self.assertEqual(linha.detalhes["especie"], ESPECIE_ASO)
        self.assertTrue(linha.detalhes["entrega"])
        # Nome de arquivo não entra na trilha: é conteúdo, e a trilha não pode
        # recriar em texto puro o que a 9.C mascara.
        self.assertNotIn("nome", linha.detalhes)

    def test_o_404_nao_entra_na_trilha(self):
        """Auditar a tentativa que falhou encheria a trilha de nada."""
        self.autenticar()
        antes = AuditLog.objects.count()
        self.client.get(url_do_arquivo(RECURSO_ASO, ESPECIE_ASO, 99999))
        self.assertEqual(AuditLog.objects.count(), antes)
