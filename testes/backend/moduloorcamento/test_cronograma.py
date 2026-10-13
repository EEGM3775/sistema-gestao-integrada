# testes/backend/moduloorcamento/test_cronograma.py
"""O cronograma físico-financeiro por etapa do orçamento.

*Decisão do dono, 11/10/2026:* a etapa do cronograma é o **grupo de 1º nível da
planilha** — não a `EtapaObra`. O vínculo com a etapa da obra é opcional e se
faz depois (`vincular_etapa_da_obra`); o cronograma funciona sem ele.

O que estes testes protegem: que a grade etapa × mês seja **calculada** do
período e da curva, pelos dias úteis; que ela feche 100% e o valor da etapa;
que a revisão do orçamento herde o cronograma; que o carimbo que o PDCA lê
mude a cada escrita; e que o vínculo com a obra seja opcional e desça às linhas.
"""
from datetime import date
from decimal import Decimal

from moduloorcamento import cronograma, planilha
from moduloorcamento.models import ItemOrcado, ItemOrcadoInsumo, ParcelaEtapa, PlanoEtapa

from .test_planilha import PlanilhaTestBase

SINTETICO = ItemOrcado.TipoLinha.SINTETICO


class _ComEtapasDoOrcamento(PlanilhaTestBase):
    def _etapa(self, orc, nome, custo, *, ordem=1, etapa_obra=None):
        """Um grupo de 1º nível com uma linha de serviço dentro; devolve o grupo."""
        grupo = self._linha(orc, nome, tipo=SINTETICO, ordem=ordem, etapa=etapa_obra)
        self._linha(orc, f"{nome} — serviço", pai=grupo, quantidade="1", custo=custo,
                    etapa=etapa_obra, ordem=1)
        return grupo


class CurvaTests(PlanilhaTestBase):
    """A aritmética pura: dias úteis → percentual por mês."""

    def _dias(self, inicio, fim):
        saida, dia = [], inicio
        while dia <= fim:
            if dia.weekday() < 5:
                saida.append(dia)
            dia = date.fromordinal(dia.toordinal() + 1)
        return saida

    def test_linear_segue_os_dias_uteis_de_cada_mes(self):
        """Agosto/2026 tem 21 dias úteis (seg–sex), setembro 22: a fatia acompanha."""
        dias = self._dias(date(2026, 8, 1), date(2026, 9, 30))
        fatias = cronograma.percentuais_por_mes(dias, PlanoEtapa.Curva.LINEAR)
        self.assertEqual(sum(fatias.values()), Decimal("100"))
        self.assertLess(fatias[date(2026, 8, 1)], fatias[date(2026, 9, 1)])

    def test_curva_s_concentra_no_miolo(self):
        dias = self._dias(date(2026, 8, 1), date(2026, 10, 31))
        fatias = cronograma.percentuais_por_mes(dias, PlanoEtapa.Curva.S)
        self.assertEqual(sum(fatias.values()), Decimal("100"))
        self.assertGreater(fatias[date(2026, 9, 1)], fatias[date(2026, 8, 1)])
        self.assertGreater(fatias[date(2026, 9, 1)], fatias[date(2026, 10, 1)])

    def test_carregada_no_inicio_e_no_fim_sao_espelhos(self):
        dias = self._dias(date(2026, 8, 1), date(2026, 9, 30))
        inicio = cronograma.percentuais_por_mes(dias, PlanoEtapa.Curva.INICIO)
        fim = cronograma.percentuais_por_mes(dias, PlanoEtapa.Curva.FIM)
        self.assertGreater(inicio[date(2026, 8, 1)], inicio[date(2026, 9, 1)])
        self.assertGreater(fim[date(2026, 9, 1)], fim[date(2026, 8, 1)])

    def test_sem_dia_util_nao_inventa_mes(self):
        self.assertEqual(cronograma.percentuais_por_mes([], PlanoEtapa.Curva.LINEAR), {})


class PlanejarEtapaTests(_ComEtapasDoOrcamento):
    def _orcamento_com_etapas(self):
        orc = self._orcamento()
        self.g_fundacao = self._etapa(orc, "1. Fundação", "40000", ordem=1)
        self.g_estrutura = self._etapa(orc, "2. Estrutura", "60000", ordem=2)
        planilha.recalcular_orcamento(orc)
        return orc

    def test_planejar_gera_a_grade_da_etapa_e_fecha_o_valor(self):
        orc = self._orcamento_com_etapas()
        cronograma.planejar_etapa(
            orc, grupo_id=self.g_fundacao.pk, inicio=date(2026, 8, 3), termino=date(2026, 10, 30),
        )
        parcelas = ParcelaEtapa.objects.filter(orcamento=orc, grupo=self.g_fundacao)
        self.assertEqual(parcelas.count(), 3)
        self.assertEqual(sum(p.percentual for p in parcelas), Decimal("100"))
        self.assertEqual(sum(p.valor_previsto for p in parcelas), Decimal("40000.00"))
        self.assertFalse(ParcelaEtapa.objects.filter(orcamento=orc, grupo=self.g_estrutura).exists())

    def test_funciona_sem_nenhuma_etapa_da_obra(self):
        """O cronograma não depende de `EtapaObra`: nenhuma linha tem vínculo."""
        orc = self._orcamento_com_etapas()
        self.assertFalse(ItemOrcado.objects.filter(orcamento=orc, etapa__isnull=False).exists())
        quantas = cronograma.planejar_todas(orc, inicio=date(2026, 8, 3), termino=date(2026, 9, 30))
        self.assertEqual(quantas, 2)

    def test_replanejar_substitui_as_celulas(self):
        orc = self._orcamento_com_etapas()
        cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 10, 30))
        cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 8, 28))
        self.assertEqual(ParcelaEtapa.objects.filter(orcamento=orc, grupo=self.g_fundacao).count(), 1)
        self.assertEqual(PlanoEtapa.objects.filter(orcamento=orc).count(), 1)

    def test_periodo_invertido_e_grupo_que_nao_e_de_1_nivel_sao_recusados(self):
        orc = self._orcamento_com_etapas()
        with self.assertRaises(cronograma.CronogramaInvalido):
            cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                      inicio=date(2026, 10, 1), termino=date(2026, 8, 1))
        filha = ItemOrcado.objects.filter(pai=self.g_fundacao).first()
        with self.assertRaises(cronograma.CronogramaInvalido):
            cronograma.planejar_etapa(orc, grupo_id=filha.pk,
                                      inicio=date(2026, 8, 1), termino=date(2026, 9, 1))

    def test_planejar_todas_poe_o_mesmo_periodo_em_cada_etapa_com_valor(self):
        orc = self._orcamento_com_etapas()
        quantas = cronograma.planejar_todas(orc, inicio=date(2026, 8, 3), termino=date(2026, 9, 30))
        self.assertEqual(quantas, 2)
        grade = cronograma.grade(orc)
        self.assertEqual(grade["total"], "100000.00")
        self.assertTrue(grade["validacao"]["consistente"])
        self.assertEqual(grade["mensal"][-1]["pct_acumulado"], "100.00")

    def test_preco_novo_refaz_o_valor_e_preserva_o_percentual(self):
        orc = self._orcamento_com_etapas()
        cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 8, 28))
        ItemOrcado.objects.filter(pai=self.g_fundacao).update(custo_unitario=Decimal("50000"))
        planilha.recalcular_orcamento(orc)
        parcela = ParcelaEtapa.objects.get(orcamento=orc, grupo=self.g_fundacao)
        self.assertEqual(parcela.percentual, Decimal("100"))
        self.assertEqual(parcela.valor_previsto, Decimal("50000.00"))

    def test_toda_escrita_carimba_o_orcamento(self):
        orc = self._orcamento_com_etapas()
        self.assertIsNone(orc.cronograma_atualizado_em)
        cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 8, 28))
        orc.refresh_from_db()
        primeiro = orc.cronograma_atualizado_em
        self.assertIsNotNone(primeiro)
        cronograma.remover_etapa(orc, grupo_id=self.g_fundacao.pk)
        orc.refresh_from_db()
        self.assertGreater(orc.cronograma_atualizado_em, primeiro)
        self.assertFalse(ParcelaEtapa.objects.filter(orcamento=orc).exists())

    def test_aprovado_aceita_cronograma_e_superado_nao(self):
        """Datas não mexem em preço: o aprovado replaneja; o superado é história."""
        orc = self._orcamento_com_etapas()
        planilha.aprovar_orcamento(orc)
        cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 8, 28))
        orc.status = orc.Status.SUPERADO
        orc.save(update_fields=["status"])
        with self.assertRaises(cronograma.CronogramaFechado):
            cronograma.planejar_etapa(orc, grupo_id=self.g_fundacao.pk,
                                      inicio=date(2026, 8, 3), termino=date(2026, 9, 30))


class VinculoComAObraTests(_ComEtapasDoOrcamento):
    """O vínculo com a `EtapaObra` é opcional, feito depois, e desce às linhas."""

    def test_vincular_e_desvincular_desce_para_as_linhas(self):
        orc = self._orcamento()
        grupo = self._etapa(orc, "1. Fundação", "40000")
        cronograma.vincular_etapa_da_obra(orc, grupo_id=grupo.pk, etapa_id=self.fundacao.pk)
        self.assertEqual(
            set(ItemOrcado.objects.filter(orcamento=orc).values_list("etapa_id", flat=True)),
            {self.fundacao.pk},
        )
        linha = cronograma.etapas_planejadas(orc)["etapas"][0]
        self.assertEqual(linha["etapa"], self.fundacao.pk)
        self.assertEqual(linha["etapa_obra_nome"], "Fundação")

        cronograma.vincular_etapa_da_obra(orc, grupo_id=grupo.pk, etapa_id=None)
        self.assertFalse(ItemOrcado.objects.filter(orcamento=orc, etapa__isnull=False).exists())
        self.assertIsNone(cronograma.etapas_planejadas(orc)["etapas"][0]["etapa"])

    def test_etapa_de_outra_obra_e_recusada(self):
        from obras.models import EtapaObra, Obra

        orc = self._orcamento()
        grupo = self._etapa(orc, "1. Fundação", "40000")
        outra = Obra.objects.create(tenant=self.tenant, nome_obra="Outra", endereco="Rua B")
        alheia = EtapaObra.objects.create(tenant=self.tenant, obra=outra, nome_etapa="X", ordem=1)
        with self.assertRaises(cronograma.CronogramaInvalido):
            cronograma.vincular_etapa_da_obra(orc, grupo_id=grupo.pk, etapa_id=alheia.pk)

    def test_vinculo_vale_com_o_orcamento_aprovado(self):
        orc = self._orcamento()
        grupo = self._etapa(orc, "1. Fundação", "40000")
        planilha.recalcular_orcamento(orc)
        planilha.aprovar_orcamento(orc)
        cronograma.vincular_etapa_da_obra(orc, grupo_id=grupo.pk, etapa_id=self.fundacao.pk)
        grupo.refresh_from_db()
        self.assertEqual(grupo.etapa_id, self.fundacao.pk)


class QuadroDasEtapasTests(_ComEtapasDoOrcamento):
    def test_etapa_nao_planejada_aparece_e_hh_vem_da_composicao(self):
        orc = self._orcamento()
        grupo = self._linha(orc, "1. Estrutura", tipo=SINTETICO, ordem=1)
        linha = self._linha(orc, "Alvenaria", pai=grupo, quantidade="100", custo="50")
        ItemOrcadoInsumo.objects.create(
            tenant=self.tenant, item_orcado=linha, descricao="PEDREIRO", unidade="H",
            categoria=ItemOrcadoInsumo.Categoria.MAO_DE_OBRA, coeficiente=Decimal("0.8"),
            custo_unitario=Decimal("25"), custo_no_item=Decimal("20"),
        )
        ItemOrcadoInsumo.objects.create(
            tenant=self.tenant, item_orcado=linha, descricao="TIJOLO", unidade="UN",
            categoria=ItemOrcadoInsumo.Categoria.MATERIAL, coeficiente=Decimal("25"),
            custo_unitario=Decimal("1.2"), custo_no_item=Decimal("30"),
        )
        planilha.recalcular_orcamento(orc)

        quadro = cronograma.etapas_planejadas(orc)
        self.assertEqual(len(quadro["etapas"]), 1)
        etapa = quadro["etapas"][0]
        self.assertFalse(etapa["planejada"])
        self.assertEqual(etapa["grupo"], grupo.pk)
        self.assertEqual(etapa["etapa_nome"], "1. Estrutura")
        self.assertEqual(etapa["horas_mao_de_obra"], "80.00")
        self.assertIsNone(etapa["dias_uteis"])

        cronograma.planejar_etapa(orc, grupo_id=grupo.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 8, 14))
        etapa = cronograma.etapas_planejadas(orc)["etapas"][0]
        self.assertTrue(etapa["planejada"])
        self.assertEqual(etapa["dias_uteis"], 10)
        # Sem expediente da obra no PDCA a jornada não é conhecida: nada de dividir por 8.
        self.assertIsNone(etapa["equipe_media"])

    def test_com_expediente_da_obra_a_equipe_media_sai(self):
        from modulopdca.models import CalendarioTrabalho

        CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Obra", obra=self.obra, horas_por_dia=Decimal("8"),
            considera_feriados=False,
        )
        orc = self._orcamento()
        grupo = self._linha(orc, "1. Estrutura", tipo=SINTETICO, ordem=1)
        linha = self._linha(orc, "Alvenaria", pai=grupo, quantidade="100", custo="50")
        ItemOrcadoInsumo.objects.create(
            tenant=self.tenant, item_orcado=linha, descricao="PEDREIRO", unidade="H",
            categoria=ItemOrcadoInsumo.Categoria.MAO_DE_OBRA, coeficiente=Decimal("0.8"),
            custo_unitario=Decimal("25"), custo_no_item=Decimal("20"),
        )
        planilha.recalcular_orcamento(orc)
        cronograma.planejar_etapa(orc, grupo_id=grupo.pk,
                                  inicio=date(2026, 8, 3), termino=date(2026, 8, 14))
        quadro = cronograma.etapas_planejadas(orc)
        self.assertEqual(quadro["expediente"], "expediente_da_obra")
        # 80 Hh ÷ (10 dias × 8 h) = 1 pessoa.
        self.assertEqual(quadro["etapas"][0]["equipe_media"], "1.0")


class RevisaoHerdaCronogramaTests(_ComEtapasDoOrcamento):
    def test_revisao_copia_plano_e_celulas_e_carimba(self):
        orc = self._orcamento()
        grupo = self._etapa(orc, "1. Fundação", "40000")
        planilha.recalcular_orcamento(orc)
        cronograma.planejar_etapa(orc, grupo_id=grupo.pk, inicio=date(2026, 8, 3),
                                  termino=date(2026, 9, 30), curva=PlanoEtapa.Curva.S)
        planilha.aprovar_orcamento(orc)

        nova = planilha.revisar_orcamento(orc, tipo="aditivo", motivo="Mudança de projeto")

        plano = PlanoEtapa.objects.get(orcamento=nova)
        self.assertEqual(plano.curva, PlanoEtapa.Curva.S)
        self.assertEqual(plano.termino, date(2026, 9, 30))
        # O grupo da revisão é o clone do grupo da origem, não o mesmo registro.
        self.assertNotEqual(plano.grupo_id, grupo.pk)
        self.assertEqual(plano.grupo.orcamento_id, nova.pk)
        self.assertEqual(plano.grupo.descricao, "1. Fundação")
        self.assertEqual(
            sum(p.valor_previsto for p in ParcelaEtapa.objects.filter(orcamento=nova)),
            Decimal("40000.00"),
        )
        self.assertIsNotNone(nova.cronograma_atualizado_em)


class CronogramaAPITests(_ComEtapasDoOrcamento):
    def setUp(self):
        super().setUp()
        self.autenticar()
        self.orc = self._orcamento()
        self.grupo = self._etapa(self.orc, "1. Fundação", "120000")
        planilha.recalcular_orcamento(self.orc)

    def _url(self, verbo):
        return f"/api/orcamento/orcamentos/{self.orc.pk}/{verbo}/"

    def test_distribuir_e_ler(self):
        resp = self.client.post(self._url("distribuir-cronograma"),
                                {"inicio": "2026-08-01", "fim": "2026-10-31", "curva": "s"},
                                format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["total"], "120000.00")
        self.assertEqual(len(resp.data["competencias"]), 3)
        self.assertEqual(resp.data["etapas"][0]["curva"], "s")

        resp = self.client.get(self._url("cronograma"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["etapas"][0]["planejada"])

    def test_planejar_e_remover_etapa(self):
        resp = self.client.post(self._url("planejar-etapa"), {
            "grupo": self.grupo.pk, "inicio": "2026-08-03", "termino": "2026-08-28",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["total"], "120000.00")

        resp = self.client.post(self._url("remover-etapa"), {"grupo": self.grupo.pk}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["total"], "0.00")

    def test_vincular_etapa_da_obra_pela_api(self):
        resp = self.client.post(self._url("vincular-etapa"), {
            "grupo": self.grupo.pk, "etapa": self.fundacao.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["etapas"][0]["etapa"], self.fundacao.pk)

        resp = self.client.post(self._url("vincular-etapa"), {
            "grupo": self.grupo.pk, "etapa": None,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.data["etapas"][0]["etapa"])

    def test_data_invalida_e_400_e_superado_e_409(self):
        resp = self.client.post(self._url("planejar-etapa"), {
            "grupo": self.grupo.pk, "inicio": "nao-e-data", "termino": "2026-08-28",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

        self.orc.status = self.orc.Status.SUPERADO
        self.orc.save(update_fields=["status"])
        resp = self.client.post(self._url("planejar-etapa"), {
            "grupo": self.grupo.pk, "inicio": "2026-08-03", "termino": "2026-08-28",
        }, format="json")
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_editar_celula_vira_curva_manual(self):
        self.client.post(self._url("planejar-etapa"), {
            "grupo": self.grupo.pk, "inicio": "2026-08-03", "termino": "2026-09-30",
        }, format="json")
        parcela = ParcelaEtapa.objects.filter(orcamento=self.orc).order_by("competencia").first()

        resp = self.client.patch(f"/api/orcamento/parcelas/{parcela.pk}/",
                                 {"percentual": "30.0000"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(PlanoEtapa.objects.get(orcamento=self.orc).curva, PlanoEtapa.Curva.MANUAL)
        parcela.refresh_from_db()
        self.assertEqual(parcela.valor_previsto, Decimal("36000.00"))

    def test_parcela_com_grupo_que_nao_e_de_1_nivel_e_400(self):
        filha = ItemOrcado.objects.filter(pai=self.grupo).first()
        resp = self.client.post("/api/orcamento/parcelas/", {
            "orcamento": self.orc.pk, "grupo": filha.pk,
            "competencia": "2026-08-01", "percentual": "100",
        }, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_curva_s_realizada_saiu_do_orcamento(self):
        """O realizado é execução — mora no PDCA, não aqui."""
        self.assertEqual(self.client.get(self._url("curva-s")).status_code, 404)
