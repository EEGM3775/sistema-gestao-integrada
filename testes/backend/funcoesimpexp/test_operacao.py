# testes/backend/funcoesimpexp/test_operacao.py
"""Operação pelo motor (15/10/2026) — PDCA, Estoque & Logística e Diário.

Importam os cadastros: locais da obra (a árvore, nível a nível, pelo caminho de
códigos), almoxarifados e ferramentas. Restrição, NC, ocorrência, ficha, DDS,
medição, atividade, movimento de estoque, diário e os relatórios só exportam.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from modulopdca.models import LocalObra
from modulosil.models import Ferramenta, LocalEstoque
from nucleo.models import Tenant, Usuario
from obras.models import Obra

from funcoesimpexp import importacao as motor
from funcoesimpexp.models import LinhaImportacao
from funcoesimpexp.registro import obter

NOVA = LinhaImportacao.Situacao.NOVA
INVALIDA = LinhaImportacao.Situacao.INVALIDA


def _csv(linhas: list[str]) -> bytes:
    return "\n".join(linhas).encode("utf-8")


class OperacaoBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="op-imp", nome="Construtora Operação")
        cls.user = Usuario.objects.create(username="op_imp", tenant=cls.tenant)
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Torre Única", endereco="Rua A")

    def recurso(self, recurso_id, **contexto):
        recurso = obter(recurso_id)
        contexto = recurso.validar_contexto(contexto, self.user, self.tenant.id)
        return recurso.com_contexto({**contexto, "tenant_id": str(self.tenant.id)})

    def preparar(self, recurso_id, linhas, **contexto):
        return motor.preparar(
            recurso=self.recurso(recurso_id, **contexto), conteudo=_csv(linhas),
            nome_arquivo="op.csv", tenant_id=self.tenant.id, usuario_nome="op",
        )

    def aplicar(self, recurso_id, lote):
        motor.aplicar(lote, recurso=obter(recurso_id).com_contexto(lote.contexto))

    def situacoes(self, lote):
        return [(l.situacao, l.motivo) for l in lote.linhas.order_by("numero")]


class LocaisDaObraTests(OperacaoBase):
    CAB = "Código;Nome;Nível;Dentro de (caminho)"

    def test_a_arvore_entra_nivel_a_nivel_pelo_caminho(self):
        torres = self.preparar("pdca.local", [self.CAB, "T1;Torre 1;Bloco / Torre;"], obra=self.obra.pk)
        self.assertEqual(self.situacoes(torres), [(NOVA, "")])
        self.aplicar("pdca.local", torres)
        pavimentos = self.preparar("pdca.local", [
            self.CAB, "P01;1º pavimento;Pavimento;T1", "P02;2º pavimento;Pavimento;t1",
        ], obra=self.obra.pk)
        self.assertEqual([s for s, _ in self.situacoes(pavimentos)], [NOVA, NOVA])
        self.aplicar("pdca.local", pavimentos)
        p02 = LocalObra.objects.get(obra=self.obra, codigo="P02")
        self.assertEqual((p02.pai.codigo, p02.profundidade, p02.nivel), ("T1", 2, "pavimento"))

    def test_pai_que_ainda_nao_existe_trava_e_diz_o_que_fazer(self):
        lote = self.preparar("pdca.local", [self.CAB, "P01;1º pavimento;Pavimento;T9"], obra=self.obra.pk)
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("T9", motivo)

    def test_mesmo_codigo_sob_o_mesmo_pai_trava(self):
        LocalObra.objects.create(tenant=self.tenant, obra=self.obra, codigo="T1", nome="Torre 1", nivel="bloco")
        lote = self.preparar("pdca.local", [self.CAB, "t1;Outra;Bloco / Torre;"], obra=self.obra.pk)
        with self.assertRaises(motor.ImportacaoInvalida):
            self.aplicar("pdca.local", lote)


class AlmoxarifadoEFerramentaTests(OperacaoBase):
    def test_almoxarifado_com_tipo_pelo_rotulo_e_obra_pelo_nome(self):
        lote = self.preparar("sil.local", ["Nome;Tipo;Obra", "Canteiro T1;Canteiro de obra;Torre Única"])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("sil.local", lote)
        local = LocalEstoque.objects.get(tenant=self.tenant)
        self.assertEqual((local.tipo, local.obra, local.ativo), ("canteiro", self.obra, True))

    def test_ferramenta_pelo_patrimonio_e_emprestada_nao_entra(self):
        Ferramenta.objects.create(tenant=self.tenant, nome="Furadeira", patrimonio="PAT-1")
        lote = self.preparar("sil.ferramenta", [
            "Ferramenta;Patrimônio;Estado",
            "Furadeira;PAT-2;Disponível",
            "Esmerilhadeira;PAT-3;Emprestada",
        ])
        (s1, _), (s2, m2) = self.situacoes(lote)
        self.assertEqual((s1, s2), (NOVA, INVALIDA))
        self.assertIn("empréstimo", m2)


PERMS = [
    "pdca.local.view", "pdca.local.edit", "pdca.restricao.view", "pdca.nc.view", "pdca.ocorrencia.view",
    "pdca.verificacao.view", "pdca.dds.view", "pdca.medicao.view", "pdca.cronograma.view",
    "sil.local.view", "sil.saldo.view", "sil.movimentacao.view", "sil.requisicao.view",
    "sil.transferencia.view", "sil.devolucao.view", "sil.inventario.view", "sil.epi.view",
    "sil.ferramenta.view", "sil.relatorio.view", "obra.diario.view",
]
SO_EXPORTAM = (
    "pdca.restricao", "pdca.nc", "pdca.ocorrencia", "pdca.verificacao", "pdca.dds", "pdca.medicao",
    "pdca.atividade", "pdca.carteira", "sil.saldo", "sil.movimentacao", "sil.requisicao",
    "sil.transferencia", "sil.devolucao", "sil.inventario", "sil.epi", "sil.emprestimo",
    "sil.curva_abc", "obra.diario",
)


class ExportacaoDaOperacaoTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="op-api", nome="Operação API")
        self.user = Usuario.objects.create(username="op_api", tenant=self.tenant)
        self.obra = Obra.objects.create(tenant=self.tenant, nome_obra="Torre API", endereco="Rua B")
        outra = Obra.objects.create(tenant=self.tenant, nome_obra="Outra", endereco="Rua C")
        LocalObra.objects.create(tenant=self.tenant, obra=self.obra, codigo="T1", nome="Torre um", nivel="bloco")
        LocalObra.objects.create(tenant=self.tenant, obra=outra, codigo="X9", nome="De outra obra", nivel="bloco")
        self.user.iam_modules = ["pdca", "sil"]
        self.user.iam_permissions = list(PERMS)
        self.user.iam_quotas = None
        self.client.force_authenticate(user=self.user)

    def _texto(self, resposta):
        corpo = b"".join(resposta.streaming_content if resposta.streaming else [resposta.content])
        return corpo.decode("utf-8-sig")

    def test_locais_saem_so_da_obra_da_tela(self):
        resposta = self.client.get("/api/impexp/pdca.local/exportar/", {"formato": "csv", "obra": self.obra.pk})
        self.assertEqual(resposta.status_code, 200, getattr(resposta, "data", ""))
        texto = self._texto(resposta)
        self.assertIn("Torre um", texto)
        self.assertNotIn("De outra obra", texto)

    def test_documentos_e_relatorios_so_exportam_e_saem(self):
        recursos = {r["id"]: r for r in self.client.get("/api/impexp/recursos/").data["recursos"]}
        for rid in SO_EXPORTAM:
            self.assertTrue(recursos[rid]["exporta"], rid)
            self.assertFalse(recursos[rid]["importa"], rid)
        recorte = {"obra": self.obra.pk, "contrato__obra": self.obra.pk,
                   "atividade__cronograma__obra": self.obra.pk}
        for rid in SO_EXPORTAM:
            resposta = self.client.get(f"/api/impexp/{rid}/exportar/", {"formato": "csv", **recorte})
            self.assertEqual(resposta.status_code, 200, (rid, getattr(resposta, "data", "")))


class ProgramacaoDaSemanaTests(OperacaoBase):
    """O dono pediu (15/10/2026): a programação semanal tem Exportar e Importar."""

    CAB = "Atividade (código);Local (caminho);Responsável / equipe;Previsto na semana (%)"

    def setUp(self):
        from modulopdca import services
        from modulopdca.models import Atividade, CalendarioTrabalho, Cronograma

        calendario = CalendarioTrabalho.objects.create(tenant=self.tenant, nome="Comercial", obra=self.obra)
        self.plano = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano", data_inicio=date(2026, 6, 1),
            calendario=calendario, status=Cronograma.Status.VIGENTE,
        )
        resumo = Atividade.objects.create(tenant=self.tenant, cronograma=self.plano, codigo="1",
                                          nome="Estrutura", duracao_dias=10)
        self.alvenaria = Atividade.objects.create(tenant=self.tenant, cronograma=self.plano, codigo="1.1",
                                                  nome="Alvenaria", duracao_dias=5, pai=resumo, profundidade=2)
        LocalObra.objects.create(tenant=self.tenant, obra=self.obra, codigo="T1", nome="Torre 1", nivel="bloco")
        self.prog = services.abrir_programacao(
            obra=self.obra, semana_inicio=date(2026, 6, 1), tenant_id=self.tenant.pk,
        )

    def test_cartao_entra_no_quadro_em_rascunho_pelo_codigo_e_local(self):
        from modulopdca.models import ItemProgramacao

        lote = self.preparar("pdca.programacao", [self.CAB, "1.1;T1;Equipe do João;40"],
                             programacao=self.prog.pk)
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("pdca.programacao", lote)
        item = ItemProgramacao.objects.get(programacao=self.prog)
        self.assertEqual((item.atividade, item.local.codigo, item.responsavel, item.percentual_previsto),
                         (self.alvenaria, "T1", "Equipe do João", Decimal("40")))
        self.assertIsNotNone(item.peso_origem)  # o peso congela na gravação, como no quadro

    def test_resumo_inexistente_e_repetido_travam(self):
        from modulopdca.models import ItemProgramacao

        ItemProgramacao.objects.create(tenant=self.tenant, programacao=self.prog, atividade=self.alvenaria)
        lote = self.preparar("pdca.programacao", [self.CAB, "1;;;", "9.9;;;", "1.1;;;"],
                             programacao=self.prog.pk)
        (s1, m1), (s2, m2), (s3, _) = self.situacoes(lote)
        self.assertEqual((s1, s2), (INVALIDA, INVALIDA))
        self.assertIn("resumo", m1)
        self.assertIn("9.9", m2)
        with self.assertRaises(motor.ImportacaoInvalida):
            self.aplicar("pdca.programacao", lote)

    def test_semana_comprometida_nao_recebe(self):
        from modulopdca.models import ProgramacaoSemanal

        ProgramacaoSemanal.objects.filter(pk=self.prog.pk).update(status=ProgramacaoSemanal.Status.COMPROMETIDA)
        lote = self.preparar("pdca.programacao", [self.CAB, "1.1;;;"], programacao=self.prog.pk)
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("rascunho", motivo)

    def test_exporta_o_quadro_da_semana_tambem_no_job(self):
        from funcoesimpexp.tasks import RequisicaoDiferida
        from modulopdca.models import ItemProgramacao

        ItemProgramacao.objects.create(tenant=self.tenant, programacao=self.prog, atividade=self.alvenaria,
                                       percentual_previsto=Decimal("25"))
        recurso = self.recurso("pdca.programacao", programacao=self.prog.pk)
        linhas = [recurso.serializar_objeto(o) for o in recurso.queryset(RequisicaoDiferida(self.user), {})]
        self.assertEqual(len(linhas), 1)
        self.assertEqual((linhas[0]["atividade"], linhas[0]["atividade__nome"]), ("1.1", "Alvenaria"))
