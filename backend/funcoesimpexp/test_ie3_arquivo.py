# backend/funcoesimpexp/test_ie3_arquivo.py
"""IE.3 — a porta única aprende arquivo.

Arquivo próprio, e não mais 250 linhas no `tests.py`: o que se prova aqui é uma
**natureza** nova do motor, com fixtures próprias (um recurso de arquivo, dois
formatos registrados) e um ciclo de vida de registry diferente — a natureza
`arquivo` troca o registry de FORMATOS além do de recursos, e misturar as duas
trocas no mesmo `setUpClass` faria um teste de linha herdar formatos que não são
dele. Segue o padrão de `nucleo/test_s8_jwt_throttle.py`.

**A máquina não é reexercitada.** R1, R6, gate, quota e a classificação são
literalmente as mesmas funções que o `tests.py` já cobre para a natureza `linha`
— repeti-las aqui seria testar duas vezes o mesmo código. O que estes testes
cobrem é só onde as duas divergem:

1. a allowlist **extensível** e a detecção por BYTES (o [D75](../../docs/historico-correcoes.md));
2. o teto **por formato**, porque `impexp_max_mb` foi dimensionado para planilha;
3. o binário **esperando decisão sem existir para o módulo dono** — a R1 aplicada
   a bytes, que na natureza `linha` não precisava existir.
"""
from __future__ import annotations

import hashlib
import os
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from nucleo.models import Tenant, Usuario

from . import importacao as motor_importacao
from .limites import (
    _REGISTRO_FORMATOS,
    FormatoDesconhecido,
    FormatoEntrada,
    NATUREZA_ARQUIVO as FORMATO_NATUREZA_ARQUIVO,
    detectar_formato,
    limites_do_plano,
    registrar_formato,
)
from .models import Importacao, LinhaImportacao
from .registro import (
    CAMPO_ARQUIVO,
    NATUREZA_ARQUIVO,
    NATUREZA_LINHA,
    ArquivoRecebido,
    Coluna,
    Recurso,
    RecursoInvalido,
    registrar,
)
from .tests import PERMS, ItemDeTeste, instantaneo, limpar, restaurar

#: "Acervo" do módulo dono, no lugar de um FileField real. O que interessa provar
#: é que o binário CHEGOU a `aplicar_linha` — não como o módulo o guarda.
ACERVO: dict[str, dict] = {}


class AcervoDeTeste(Recurso):
    """Recurso de natureza `arquivo` — o esqueleto do que a PRA.5 vai declarar."""

    rotulo = "Acervo de teste"
    modulo = "teste"
    natureza = NATUREZA_ARQUIVO
    formatos_arquivo = ("dwgteste", "dxfteste")
    permissoes_exigidas = PERMS
    chave = "hash"
    colunas = (
        Coluna("hash", "Hash", obrigatoria=True),
        Coluna("nome", "Arquivo"),
        Coluna("caminho", "Caminho"),
        Coluna("formato", "Formato"),
        Coluna("tamanho", "Tamanho", tipo=int),
        Coluna("obra", "Obra"),
    )

    def dados_do_arquivo(self, arquivo):
        dados = super().dados_do_arquivo(arquivo)
        partes = arquivo.caminho.split("/")
        dados["obra"] = partes[0] if len(partes) > 1 else ""
        return dados

    def validar_linha(self, dados):
        # Regra de domínio qualquer, só para provar que a classificação de arquivo
        # passa pelo MESMO `_classificar` da linha.
        if dados["nome"].startswith("~$"):
            return "Arquivo temporário do Office."
        return ""

    def localizar(self, dados, tenant_id):
        return ACERVO.get(dados["hash"])

    def aplicar_linha(self, dados, existente, tenant_id):
        binario = dados.get(CAMPO_ARQUIVO)
        lidos = len(binario.read()) if binario else 0
        ACERVO[dados["hash"]] = {
            "nome": dados["nome"], "obra": dados["obra"], "bytes": lidos,
        }
        return {"acao": "criou", "chave": dados["hash"]}

    def desfazer_linha(self, estado_anterior, tenant_id):
        ACERVO.pop(estado_anterior["chave"], None)


DWG_TESTE = FormatoEntrada(
    "dwgteste", "Desenho de teste", (".dwgt",), (b"AC10",),
    FORMATO_NATUREZA_ARQUIVO, max_mb=300, origem="teste",
)
DXF_TESTE = FormatoEntrada(
    "dxfteste", "DXF de teste", (".dxft",), (),
    FORMATO_NATUREZA_ARQUIVO, marcadores_texto=(b"SECTION",), max_mb=300, origem="teste",
)


class _Plano:
    """Usuário mínimo para `limites_do_plano` — só a claim importa."""

    def __init__(self, plano="free"):
        self.iam_plano = plano
        self.username = "u"


class ArquivoTestBase(TestCase):
    """Troca os DOIS registries globais: recursos e formatos.

    O de formatos é a novidade e o que mais morde: `registrar_formato` escreve num
    dict de processo, então um teste que registra `dwgteste` e não o remove deixa a
    allowlist real da plataforma com um formato inventado — e o estrago aparece em
    outro arquivo de teste, como um DWG que passa onde não devia.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._registro_do_boot = instantaneo()
        cls._formatos_do_boot = dict(_REGISTRO_FORMATOS)
        limpar()
        cls.recurso = registrar("teste.acervo")(AcervoDeTeste)()
        registrar_formato(DWG_TESTE)
        registrar_formato(DXF_TESTE)

    @classmethod
    def tearDownClass(cls):
        restaurar(cls._registro_do_boot)
        _REGISTRO_FORMATOS.clear()
        _REGISTRO_FORMATOS.update(cls._formatos_do_boot)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="ie3-a", nome="Construtora A")
        cls.user = Usuario.objects.create(username="operador_ie3", tenant=cls.tenant)

    def setUp(self):
        super().setUp()
        ACERVO.clear()

    def _recebido(self, nome, caminho, conteudo, formato="dwgteste"):
        return (
            ArquivoRecebido(
                nome=nome, caminho=caminho, tamanho=len(conteudo),
                hash=hashlib.sha256(conteudo).hexdigest(), formato=formato,
            ),
            ContentFile(conteudo, name=nome),
        )

    def _preparar(self, itens, **kwargs):
        return motor_importacao.preparar_arquivos(
            recurso=self.recurso, arquivos=itens,
            tenant_id=self.tenant.id, usuario_nome="operador", **kwargs,
        )


# ---------------------------------------------------------------------------
# 1. A allowlist extensível — e o D75
# ---------------------------------------------------------------------------


class AllowlistExtensivelTests(ArquivoTestBase):
    def test_modulo_acrescenta_formato_e_a_deteccao_o_reconhece(self):
        self.assertEqual(
            detectar_formato("p.dwgt", b"AC1015" + b"\x00" * 40).codigo, "dwgteste",
        )

    def test_formato_de_texto_e_reconhecido_pelo_marcador(self):
        """Marcador não ancorado no byte 0 — DXF real traz comentário antes."""
        self.assertEqual(
            detectar_formato("qualquer.dxft", b"999\nfeito a mao\n  0\nSECTION\n").codigo,
            "dxfteste",
        )

    def test_d75_executavel_renomeado_e_recusado(self):
        """O achado que motivou a fatia: sufixo é dado do atacante."""
        with self.assertRaises(FormatoDesconhecido):
            detectar_formato("payload.dwgt", b"MZ\x90\x00\x03" + b"\x00" * 40)

    def test_modulo_nao_pode_declarar_formato_tabular(self):
        """Natureza `tabela` diz que o MOTOR abre o arquivo, e ele só sabe abrir o
        que implementa em `formatos/leitura.py`."""
        with self.assertRaises(RecursoInvalido):
            registrar_formato(
                FormatoEntrada("inventado", "X", (".x",), (b"XX",), "tabela"),
            )

    def test_colisao_com_declaracao_diferente_falha_no_boot(self):
        with self.assertRaises(RecursoInvalido):
            registrar_formato(FormatoEntrada("dwgteste", "Outro", (".zzz",), (b"AC10",)))

    def test_registrar_o_mesmo_duas_vezes_e_idempotente(self):
        registrar_formato(DWG_TESTE)  # o `apps.py` pode ser importado duas vezes

    def test_formato_sem_extensao_e_recusado(self):
        with self.assertRaises(RecursoInvalido):
            registrar_formato(FormatoEntrada("semext", "X", (), (b"QQ",),
                                             FORMATO_NATUREZA_ARQUIVO))


# ---------------------------------------------------------------------------
# 2. O teto por formato
# ---------------------------------------------------------------------------


class TetoPorFormatoTests(ArquivoTestBase):
    def test_planilha_continua_no_teto_do_plano(self):
        self.assertEqual(limites_do_plano(_Plano("free")).max_mb, 5)

    def test_arquivo_vale_o_teto_do_formato_nao_o_da_planilha(self):
        limites = limites_do_plano(_Plano("free"))
        self.assertEqual(
            limites.max_mb_de(DWG_TESTE), 300,
            "5 MB de plano de planilha não comporta prancha",
        )

    def test_teto_de_infra_fica_por_cima_do_formato(self):
        absurdo = FormatoEntrada(
            "gigante", "Gigante", (".gg",), (b"GG",),
            FORMATO_NATUREZA_ARQUIVO, max_mb=100_000, origem="teste",
        )
        self.assertEqual(
            limites_do_plano(_Plano("sob_medida")).max_mb_de(absurdo), 300,
            "contrato negociado não compra o direito de derrubar o worker",
        )

    def test_formato_de_arquivo_nao_e_vendido_pelo_knob_do_motor(self):
        """Quem vende formato de arquivo é o módulo dono (`formatos_prancheta`)."""
        self.assertIn("dwgteste", limites_do_plano(_Plano("free")).formatos)

    def test_descrever_publica_o_teto_por_formato(self):
        formatos = {f["codigo"]: f for f in limites_do_plano(_Plano("free")).descrever()["formatos"]}
        self.assertEqual(formatos["dwgteste"]["max_mb"], 300)
        self.assertEqual(formatos["xlsx"]["max_mb"], 5)
        self.assertEqual(formatos["dwgteste"]["natureza"], FORMATO_NATUREZA_ARQUIVO)


# ---------------------------------------------------------------------------
# 3. A conferência de arquivo — R1 e R6 sobre bytes
# ---------------------------------------------------------------------------


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ConferenciaDeArquivoTests(ArquivoTestBase):
    def test_pasta_vira_taxonomia_e_o_lote_para_em_conferencia(self):
        lote = self._preparar([
            self._recebido("p1.dwgt", "TorreA/ARQ/p1.dwgt", b"AC1015aaa"),
            self._recebido("p2.dwgt", "TorreA/EST/p2.dwgt", b"AC1015bbb"),
        ])
        self.assertEqual(lote.status, Importacao.Status.CONFERINDO)
        self.assertEqual(lote.total_linhas, 2)
        self.assertEqual(
            [l.valores["obra"] for l in lote.linhas.order_by("numero")],
            ["TorreA", "TorreA"],
        )
        self.assertEqual(lote.arquivo_nome, "TorreA/ (2 arquivos)")
        self.assertEqual(ACERVO, {}, "R1 — nada no destino antes da decisão")

    def test_r1_o_binario_espera_na_conferencia_e_nao_no_acervo(self):
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015aaa")])
        linha = lote.linhas.get()
        self.assertTrue(linha.arquivo, "os bytes têm de existir em algum lugar")
        self.assertIn("impexp/conferencia/", linha.arquivo.name)
        self.assertEqual(ACERVO, {})

    def test_envio_avulso_vira_lote_de_um_com_o_nome_do_arquivo(self):
        lote = self._preparar([self._recebido("planta.dwgt", "planta.dwgt", b"AC1015u")])
        self.assertEqual(lote.arquivo_nome, "planta.dwgt")

    def test_mesmo_conteudo_com_outro_nome_e_duplicada(self):
        primeiro = self._preparar([self._recebido("a.dwgt", "a.dwgt", b"AC1015mesmo")])
        motor_importacao.aplicar(primeiro, recurso=self.recurso, usuario_nome="op")
        segundo = self._preparar([
            self._recebido("renomeado.dwgt", "x/renomeado.dwgt", b"AC1015mesmo"),
        ])
        self.assertEqual(
            segundo.linhas.get().situacao, LinhaImportacao.Situacao.DUPLICADA,
            "o hash é a identidade — renomear não faz um arquivo novo",
        )

    def test_repetido_dentro_do_proprio_lote_e_invalido(self):
        lote = self._preparar([
            self._recebido("a.dwgt", "a.dwgt", b"AC1015igual"),
            self._recebido("b.dwgt", "b.dwgt", b"AC1015igual"),
        ])
        self.assertEqual(
            [l.situacao for l in lote.linhas.order_by("numero")], ["nova", "invalida"],
        )

    def test_regra_do_modulo_reprova_e_invalida_nao_gasta_disco(self):
        lote = self._preparar([
            self._recebido("~$rascunho.dwgt", "~$rascunho.dwgt", b"AC1015x"),
        ])
        linha = lote.linhas.get()
        self.assertEqual(linha.situacao, LinhaImportacao.Situacao.INVALIDA)
        self.assertFalse(linha.aceita, "inválida nasce desmarcada")
        self.assertFalse(
            linha.arquivo,
            "não se paga disco por arquivo que já se sabe que será apagado",
        )

    def test_aplicar_entrega_o_binario_ao_modulo(self):
        lote = self._preparar([
            self._recebido("p.dwgt", "TorreA/p.dwgt", b"AC1015conteudo"),
        ])
        motor_importacao.aplicar(lote, recurso=self.recurso, usuario_nome="op")
        self.assertEqual(len(ACERVO), 1)
        gravado = next(iter(ACERVO.values()))
        self.assertEqual(gravado["obra"], "TorreA")
        self.assertEqual(
            gravado["bytes"], len(b"AC1015conteudo"), "os bytes chegaram inteiros",
        )

    def test_desfazer_remove_do_acervo(self):
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015z")])
        motor_importacao.aplicar(lote, recurso=self.recurso, usuario_nome="op")
        self.assertEqual(len(ACERVO), 1)
        motor_importacao.desfazer(lote, recurso=self.recurso)
        self.assertEqual(ACERVO, {}, "R6 vale igual para arquivo")

    # ------------------------------------------------------------------
    # A faxina roda em `on_commit`, então os dois testes abaixo PRECISAM do
    # `captureOnCommitCallbacks`. Sem ele o `TestCase` envolve tudo numa
    # transação que nunca commita, o callback não dispara, e um assert de
    # "o arquivo sumiu" passaria por engano — provando o contrário do que
    # pretende. É o mesmo cuidado que o `agendar_limpeza` documenta: exclusão de
    # arquivo não participa da transação, e é justamente por isso que ela tem de
    # esperar o commit.
    # ------------------------------------------------------------------

    def test_negar_tudo_devolve_o_disco_e_guarda_o_rastro(self):
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015grande")])
        caminho = lote.linhas.get().arquivo.path
        with self.captureOnCommitCallbacks(execute=True):
            motor_importacao.descartar(lote, usuario_nome="op")
        lote.refresh_from_db()
        self.assertEqual(lote.status, Importacao.Status.DESCARTADA)
        self.assertFalse(
            lote.linhas.get().arquivo, "os bytes recusados têm de sumir do disco",
        )
        self.assertFalse(os.path.exists(caminho), "e sumir do disco de verdade")
        self.assertEqual(
            lote.linhas.count(), 1, "a linha fica — é o rastro do que se recusou",
        )

    def test_a_faxina_espera_o_commit(self):
        """Sem commit, o arquivo continua lá — o que garante que uma decisão
        revertida não deixe o lote oferecendo bytes que já não existem."""
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015nc")])
        motor_importacao.descartar(lote, usuario_nome="op")
        self.assertTrue(
            lote.linhas.get().arquivo,
            "apagar dentro do bloco atômico deixaria o pior estado possível",
        )

    def test_aplicado_a_copia_da_conferencia_e_faxinada(self):
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015dup")])
        with self.captureOnCommitCallbacks(execute=True):
            motor_importacao.aplicar(lote, recurso=self.recurso, usuario_nome="op")
        self.assertFalse(
            lote.linhas.get().arquivo,
            "aplicado, a cópia da conferência é duplicata do que está no acervo",
        )

    def test_resumo_declara_a_natureza_para_a_tela(self):
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015r")])
        self.assertEqual(motor_importacao.resumo(lote)["natureza"], NATUREZA_ARQUIVO)

    def test_recurso_de_arquivo_recusa_o_caminho_tabular(self):
        with self.assertRaises(motor_importacao.ImportacaoInvalida):
            motor_importacao.preparar(
                recurso=self.recurso, conteudo=b"a;b", nome_arquivo="x.csv",
                tenant_id=self.tenant.id,
            )

    def test_teto_de_operacao_barra_antes_de_gravar_qualquer_binario(self):
        with self.assertRaises(motor_importacao.LimiteDoPlano):
            self._preparar(
                [self._recebido(f"p{i}.dwgt", f"p{i}.dwgt", b"AC1015" + bytes([i]))
                 for i in range(3)],
                limites={"importacao_linhas": 2},
            )
        self.assertEqual(
            LinhaImportacao.objects.count(), 0, "nem a linha, nem o byte no disco",
        )

    def test_isolamento_o_lote_nasce_no_tenant_de_quem_subiu(self):
        lote = self._preparar([self._recebido("p.dwgt", "p.dwgt", b"AC1015t")])
        self.assertEqual(lote.tenant_id, self.tenant.id)
        self.assertEqual(lote.linhas.get().tenant_id, self.tenant.id)


# ---------------------------------------------------------------------------
# 4. A régua — declaração torta falha no boot
# ---------------------------------------------------------------------------


class ReguaDeArquivoTests(TestCase):
    def test_recurso_de_arquivo_exige_allowlist_propria(self):
        class SemFormato(AcervoDeTeste):
            formatos_arquivo = ()

        SemFormato.id = "teste.semformato"
        with self.assertRaises(RecursoInvalido):
            SemFormato().validar()

    def test_natureza_desconhecida_falha(self):
        class Torto(AcervoDeTeste):
            natureza = "planilha"

        Torto.id = "teste.torto"
        with self.assertRaises(RecursoInvalido):
            Torto().validar()

    def test_recurso_de_arquivo_que_nem_recebe_nem_entrega_falha(self):
        """Natureza `arquivo` sem receber nem entregar arquivo é declaração torta.

        **A régua mudou em 08/08/2026 e este teste guarda a parte que NÃO mudou.**
        Até a IE.3b, um recurso de arquivo sem `aplicar_linha` era recusado com o
        argumento de que a saída de binário pertencia ao módulo dono. A porta
        única passou a ser de entrada e de saída, então só entregar virou
        legítimo (`test_recurso_de_arquivo_que_so_entrega_e_valido`, no
        [test_ie3b_entrega.py](test_ie3b_entrega.py)) — o que segue recusado é
        declarar a natureza e não fazer nenhuma das duas coisas com arquivo.
        Exportação tabular sozinha não justifica a natureza: a unidade de decisão
        dela é a linha.
        """
        class SoTabular(Recurso):
            id = "teste.sotabular"
            rotulo = "X"
            modulo = "teste"
            natureza = NATUREZA_ARQUIVO
            formatos_arquivo = ("dwgteste",)
            permissoes_exigidas = ("teste.item.view",)
            chave = "hash"
            colunas = (Coluna("hash", "Hash", obrigatoria=True),)

            def queryset(self, request, recorte):
                return []

        with self.assertRaisesMessage(RecursoInvalido, "não recebe e não entrega"):
            SoTabular().validar()

    def test_recurso_de_linha_segue_intocado(self):
        item = ItemDeTeste()
        item.id = "teste.item"
        item.validar()
        self.assertFalse(item.de_arquivo)
        self.assertEqual(item.natureza, NATUREZA_LINHA)


# ---------------------------------------------------------------------------
# 5. O catálogo anuncia o que a PORTA aceita — D83
# ---------------------------------------------------------------------------


class CatalogoAnunciaOTetoDaPortaTests(TestCase):
    """O que a tela lê tem de ser o que o servidor faz.

    **O D83 nasceu de duas contas para a mesma pergunta.** O teto de um formato de
    arquivo é do RECURSO (`teto_mb_do_formato`), porque o mesmo PDF é planilha de
    preço num módulo e prancha de 100 MB em outro. Mas quem publicava o número era
    `Limites.descrever()`, que não conhece recurso nenhum e só sabia devolver o do
    plano: o catálogo anunciava **25 MB** para DWG enquanto a porta aceitava
    **150**. A primeira tela a acreditar no anúncio — o `<WizardArquivos>` da
    PRA.5c — recusou sozinha um arquivo de 64,9 MB que o servidor teria aceito.

    Este teste roda sobre o registry **real** de propósito: um recurso de mentira
    provaria o mecanismo e não a frota. O que se cobra é a igualdade, formato a
    formato, entre o anúncio e a régua da porta.
    """

    def test_todo_recurso_de_arquivo_anuncia_o_teto_que_a_porta_aplica(self):
        from .limites import FORMATOS_POR_CODIGO, teto_do_formato
        from .registro import listar
        from .views import RecursosView

        limites = limites_do_plano(_Plano("profissional"))
        de_arquivo = [r for r in listar() if r.de_arquivo]
        self.assertTrue(de_arquivo, "sem recurso de arquivo não há o que conferir")

        for recurso in de_arquivo:
            anunciado = RecursosView._descrever(recurso, limites).get("tetos_mb", {})
            for codigo in recurso.formatos_arquivo:
                if codigo not in FORMATOS_POR_CODIGO:
                    continue
                with self.subTest(recurso=recurso.id, formato=codigo):
                    self.assertEqual(
                        anunciado.get(codigo),
                        teto_do_formato(recurso, FORMATOS_POR_CODIGO[codigo], limites),
                        "o catálogo prometeu um número e a porta aplica outro",
                    )

    def test_o_mesmo_formato_tem_tetos_diferentes_em_recursos_diferentes(self):
        """O controle negativo: se um número global bastasse, o campo não faria falta.

        `imagem` no acervo é prancha escaneada; `imagem` nas marcações é recorte de
        tela. Dois tetos do mesmo formato, e nenhum catálogo global os representa —
        é por isso que `tetos_mb` é por recurso, e não uma coluna a mais no
        `limites`.
        """
        from .registro import listar
        from .views import RecursosView

        limites = limites_do_plano(_Plano("profissional"))
        por_recurso = {
            r.id: RecursosView._descrever(r, limites).get("tetos_mb", {})
            for r in listar() if r.de_arquivo
        }
        tetos_de_imagem = {
            recurso: tetos["imagem"]
            for recurso, tetos in por_recurso.items() if "imagem" in tetos
        }
        if len(tetos_de_imagem) < 2:
            self.skipTest("menos de dois recursos recebem `imagem` nesta build")
        self.assertGreater(
            len(set(tetos_de_imagem.values())), 1,
            f"todos os tetos de `imagem` iguais ({tetos_de_imagem}) — ou a frota "
            "mudou, ou o campo voltou a sair do catálogo global",
        )
