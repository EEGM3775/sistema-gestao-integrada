"""A semana assumida antes de um replanejamento continua fechável.

Achado do dono (13/10/2026): o cartão fica preso à atividade da versão em que
foi puxado; publicada a versão nova, aquela vira `substituído`, e julgar pelo
% concluído lançava o avanço nela — recusado ("só o cronograma vigente recebe
apontamento"), e a semana não encerrava.
"""
from datetime import date
from decimal import Decimal

from modulopdca import services
from modulopdca.models import ApontamentoAvanco, CausaNaoCumprimento, Cronograma, ItemProgramacao

from testes.backend.modulopdca.test_achados_09_10 import _Base


class SemanaComPlanoReplanejadoTests(_Base):
    def setUp(self):
        super().setUp()
        self.plano = self._plano()
        self.a1 = self._atividade(self.plano, "1", "Alvenaria", duracao=5)
        services.publicar(self.plano)
        self.prog = services.abrir_programacao(
            obra=self.obra, semana_inicio=date(2026, 6, 1), tenant_id=self.tenant.pk,
        )
        self.item = ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.prog, atividade=self.a1,
            percentual_previsto=Decimal("20"),
        )
        services.comprometer(programacao=self.prog, por="Ana")
        self.nova = services.replanejar(self.plano, motivo="Chuva")
        services.publicar(self.nova)
        self.plano.refresh_from_db()
        self.assertEqual(self.plano.status, Cronograma.Status.SUBSTITUIDO)

    def test_julga_pelo_concluido_e_o_avanco_vai_para_a_versao_vigente(self):
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": self.item.pk, "percentual_concluido": Decimal("25")},
        ], por="Ana")
        self.item.refresh_from_db()
        self.assertTrue(self.item.cumprido)
        apontamento = ApontamentoAvanco.objects.get()
        self.assertEqual(apontamento.atividade.cronograma_id, self.nova.pk)
        self.assertEqual(apontamento.percentual, Decimal("25"))
        # A prova "apontou" do cartão enxerga o avanço lançado na versão nova.
        self.assertEqual(
            services.avanco_apontado_dos_itens(self.prog)[self.item.pk], Decimal("25"),
        )

        services.encerrar(programacao=self.prog, por="Ana", hoje=date(2026, 6, 10))
        self.prog.refresh_from_db()
        self.assertEqual(self.prog.status, self.prog.Status.ENCERRADA)

    def test_o_avanco_ja_apontado_na_versao_nova_conta_no_atual(self):
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.nova.atividades.get(codigo="1"),
            data=date(2026, 6, 3), percentual=Decimal("15"),
        )
        andamento = services.andamento_dos_itens(self.prog)[self.item.pk]
        self.assertEqual(andamento["atual"], Decimal("15"))
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": self.item.pk, "percentual_concluido": Decimal("30")},
        ])
        self.assertEqual(
            sum(ApontamentoAvanco.objects.values_list("percentual", flat=True)), Decimal("30"),
        )

    def test_o_que_nao_saiu_e_arrastado_na_versao_vigente(self):
        causa = CausaNaoCumprimento.objects.filter(tenant=self.tenant).first()
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": self.item.pk, "percentual_concluido": Decimal("10"), "causa": causa.pk},
        ])
        r = services.encerrar(programacao=self.prog, por="Ana", hoje=date(2026, 6, 10))
        self.assertEqual(r["arrasto"]["arrastados"], 1)
        novo = ItemProgramacao.objects.get(arrastado_de=self.item)
        self.assertEqual(novo.atividade.cronograma_id, self.nova.pk)
