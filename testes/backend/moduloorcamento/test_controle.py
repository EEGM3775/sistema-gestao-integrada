# testes/backend/moduloorcamento/test_controle.py
"""Testes do ORC.3 — quatro colunas, cronograma físico-financeiro e curva S.

O que estes testes protegem, além da aritmética: que as quatro colunas
continuem sendo **quatro leituras distintas**. Se um dia alguém "simplificar"
somando comprometido com realizado, ou atribuindo despesa de empreendimento a
uma obra por rateio implícito, o número resultante parece certo e não é — e é
sobre ele que a construtora decide se pode comprar.
"""
from datetime import date
from decimal import Decimal

from catalogo.models import Item
from fornecedores.models import Fornecedor
from moduloerp.models import ContaPagar
from modulosil.models import LocalEstoque, MovimentacaoEstoque
from moduloscm.models import CentroCusto, PedidoCompra

from moduloorcamento import controle, planilha
from moduloorcamento.models import ItemOrcado, ParcelaEtapa
from .test_planilha import PlanilhaTestBase


class QuatroColunasTests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Fornecedor A LTDA",
            cnpj="11222333000181", email="compras@a.com.br",
        )
        self.centro = CentroCusto.objects.create(
            tenant=self.tenant, nome="Obra Aurora", tipo=CentroCusto.Tipo.OBRA, obra=self.obra,
        )
        self.item = Item.objects.create(
            tenant=self.tenant, codigo_interno="CIM-01", descricao="Cimento", unidade="KG",
        )

    def _orcamento_aprovado(self, valor="100000"):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo=valor, etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)
        return orc

    def _pedido(self, valor, *, status=PedidoCompra.Status.ENVIADO, conta=None):
        return PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, centro_custo=self.centro,
            status=status, valor_total=Decimal(valor), conta_pagar_ref=conta,
        )

    def _saida(self, quantidade, custo):
        local = LocalEstoque.objects.create(
            tenant=self.tenant, nome=f"Canteiro {quantidade}", obra=self.obra,
        )
        return MovimentacaoEstoque.objects.create(
            tenant=self.tenant, item=self.item, local=local,
            tipo=MovimentacaoEstoque.Tipo.SAIDA, quantidade=Decimal(quantidade),
            custo_unitario=Decimal(custo), obra=self.obra, etapa=self.fundacao,
        )

    def test_as_quatro_colunas_sao_quatro_leituras(self):
        self._orcamento_aprovado("100000")
        self._pedido("60000")
        self._saida("100", "400")  # 40.000 aplicados

        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]

        self.assertEqual(Decimal(linha["orcado"]), Decimal("100000.00"))
        self.assertEqual(Decimal(linha["comprometido"]), Decimal("60000.00"))
        self.assertEqual(Decimal(linha["aplicado"]), Decimal("40000.00"))
        self.assertEqual(Decimal(linha["realizado"]), Decimal("0.00"))

    def test_saldo_desconta_o_comprometido_e_nao_o_aplicado(self):
        """O que já foi pedido não está mais disponível, ainda que a nota não
        tenha chegado — é o número que evita comprar duas vezes o mesmo."""
        self._orcamento_aprovado("100000")
        self._pedido("60000")

        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]
        self.assertEqual(Decimal(linha["saldo"]), Decimal("40000.00"))
        self.assertEqual(linha["consumido_pct"], "60.00")
        self.assertFalse(linha["estourado"])

    def test_comprometido_acima_do_orcado_marca_estouro(self):
        self._orcamento_aprovado("50000")
        self._pedido("60000")

        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]
        self.assertTrue(linha["estourado"])
        self.assertEqual(Decimal(linha["saldo"]), Decimal("-10000.00"))

    def test_rascunho_e_cancelado_nao_comprometem(self):
        """Rascunho é intenção; cancelado é compromisso desfeito."""
        self._orcamento_aprovado("100000")
        self._pedido("10000", status=PedidoCompra.Status.RASCUNHO)
        self._pedido("20000", status=PedidoCompra.Status.CANCELADO)
        self._pedido("30000")

        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]
        self.assertEqual(Decimal(linha["comprometido"]), Decimal("30000.00"))

    def test_realizado_vem_da_baixa_do_erp_pelo_caminho_do_scm(self):
        conta = ContaPagar.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, descricao="NF 123",
            valor=Decimal("60000"), data_vencimento=date(2026, 8, 10),
            valor_pago=Decimal("25000"),
        )
        self._orcamento_aprovado("100000")
        self._pedido("60000", conta=conta.pk)

        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]
        self.assertEqual(Decimal(linha["realizado"]), Decimal("25000.00"))
        self.assertEqual(linha["realizado_cobertura"], "erp")

    def test_obra_sem_orcamento_aprovado_tem_orcado_nulo(self):
        """Zero se leria como 'estourou 100%' — o honesto é não ter régua."""
        self._pedido("10000")
        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]

        self.assertIsNone(linha["orcado"])
        self.assertIsNone(linha["saldo"])
        self.assertIsNone(linha["consumido_pct"])
        self.assertFalse(linha["estourado"])
        self.assertEqual(Decimal(linha["comprometido"]), Decimal("10000.00"))

    def test_pedido_sem_centro_de_custo_de_obra_nao_entra(self):
        """Compra administrativa não é custo de obra."""
        self._orcamento_aprovado("100000")
        administrativo = CentroCusto.objects.create(
            tenant=self.tenant, nome="Administrativo", tipo=CentroCusto.Tipo.ADMINISTRATIVO,
        )
        PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, centro_custo=administrativo,
            status=PedidoCompra.Status.ENVIADO, valor_total=Decimal("9999"),
        )
        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]
        self.assertEqual(Decimal(linha["comprometido"]), Decimal("0.00"))

    def test_isolamento_por_tenant(self):
        self._orcamento_aprovado("100000")
        self._pedido("60000")

        self.assertEqual(controle.quatro_colunas(self.tenant_b.id), [])


class CronogramaTests(PlanilhaTestBase):
    def _com_valor(self, valor="120000"):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo=valor, etapa=self.fundacao)
        planilha.recalcular_orcamento(orc)
        return orc

    def test_distribuicao_linear_fecha_cem_por_cento(self):
        """O resíduo vai no último mês — 100/3 deixaria sobra e o cronograma
        não bateria com o orçamento."""
        orc = self._com_valor("120000")
        controle.distribuir_linear(orc, inicio=date(2026, 8, 1), fim=date(2026, 10, 1))

        parcelas = ParcelaEtapa.objects.filter(orcamento=orc).order_by("competencia")
        self.assertEqual(parcelas.count(), 3)
        self.assertEqual(sum(p.percentual for p in parcelas), Decimal("100.0000"))
        self.assertEqual(sum(p.valor_previsto for p in parcelas), Decimal("120000.00"))

    def test_parcela_de_etapa_distribui_so_o_valor_da_etapa(self):
        orc = self._orcamento()
        self._linha(orc, "Fundação", quantidade="1", custo="40000", etapa=self.fundacao, ordem=1)
        self._linha(orc, "Estrutura", quantidade="1", custo="60000", etapa=self.estrutura, ordem=2)
        planilha.recalcular_orcamento(orc)

        controle.distribuir_linear(
            orc, inicio=date(2026, 8, 1), fim=date(2026, 9, 1), etapa=self.fundacao,
        )
        parcelas = ParcelaEtapa.objects.filter(orcamento=orc, etapa=self.fundacao)
        self.assertEqual(sum(p.valor_previsto for p in parcelas), Decimal("40000.00"))

    def test_periodo_invertido_e_recusado(self):
        orc = self._com_valor()
        with self.assertRaises(controle.CronogramaInvalido):
            controle.distribuir_linear(orc, inicio=date(2026, 10, 1), fim=date(2026, 8, 1))

    def test_redistribuir_substitui_em_vez_de_acumular(self):
        orc = self._com_valor()
        controle.distribuir_linear(orc, inicio=date(2026, 8, 1), fim=date(2026, 10, 1))
        controle.distribuir_linear(orc, inicio=date(2026, 8, 1), fim=date(2026, 9, 1))

        self.assertEqual(ParcelaEtapa.objects.filter(orcamento=orc).count(), 2)

    def test_validacao_aponta_etapa_que_nao_fecha(self):
        orc = self._com_valor()
        ParcelaEtapa.objects.create(
            tenant=self.tenant, orcamento=orc, competencia=date(2026, 8, 1),
            percentual=Decimal("70.0000"),
        )
        validacao = controle.validar_cronograma(orc)

        self.assertFalse(validacao["consistente"])
        self.assertEqual(validacao["problemas"][0]["diferenca"], "30.0000")

    def test_grade_do_cronograma_traz_meses_e_linhas(self):
        orc = self._com_valor()
        controle.distribuir_linear(
            orc, inicio=date(2026, 8, 1), fim=date(2026, 9, 1), etapa=self.fundacao,
        )
        grade = controle.cronograma(orc)

        self.assertEqual(grade["competencias"], ["2026-08-01", "2026-09-01"])
        self.assertEqual(len(grade["linhas"]), 1)
        self.assertEqual(grade["linhas"][0]["etapa_nome"], "Fundação")
        self.assertEqual(grade["total"], "120000.00")


class CurvaSTests(PlanilhaTestBase):
    def _cenario(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="90000", etapa=self.fundacao)
        planilha.recalcular_orcamento(orc)
        controle.distribuir_linear(orc, inicio=date(2026, 8, 1), fim=date(2026, 10, 1))
        return orc

    def _consumir(self, valor, quando):
        local = LocalEstoque.objects.create(
            tenant=self.tenant, nome=f"Canteiro {quando:%m}", obra=self.obra,
        )
        item = Item.objects.create(
            tenant=self.tenant, codigo_interno=f"IT-{quando:%m%d}",
            descricao="Insumo", unidade="UN",
        )
        mov = MovimentacaoEstoque.objects.create(
            tenant=self.tenant, item=item, local=local,
            tipo=MovimentacaoEstoque.Tipo.SAIDA, quantidade=Decimal("1"),
            custo_unitario=Decimal(valor), obra=self.obra, etapa=self.fundacao,
        )
        MovimentacaoEstoque.objects.filter(pk=mov.pk).update(criado_em=quando)
        return mov

    def test_serie_acumula_previsto_e_realizado(self):
        """90.000 em 3 meses: o percentual é a fonte de verdade, então cada mês
        vale 33,3333% = 29.999,97 e o último absorve o resíduo (33,3334% =
        30.000,06). O **total fecha exato** — é o invariante que importa; a
        diferença de centavos no mês é inerente a representar um terço com 4
        casas de percentual, e aparece igual nas ferramentas do mercado."""
        from django.utils import timezone

        orc = self._cenario()
        self._consumir("20000", timezone.make_aware(timezone.datetime(2026, 8, 15, 10, 0)))
        self._consumir("40000", timezone.make_aware(timezone.datetime(2026, 9, 15, 10, 0)))

        curva = controle.curva_s(orc)
        serie = {linha["competencia"].isoformat(): linha for linha in curva["serie"]}

        self.assertEqual(curva["total_previsto"], "90000.00")
        self.assertEqual(serie["2026-08-01"]["previsto_acumulado"], "29999.97")
        self.assertEqual(serie["2026-08-01"]["realizado_acumulado"], "20000.00")
        self.assertEqual(serie["2026-09-01"]["realizado_acumulado"], "60000.00")
        # Consumo (60.000) acima do previsto acumulado (59.999,94) → desvio +0,06.
        self.assertEqual(serie["2026-09-01"]["desvio_acumulado"], "0.06")
        self.assertEqual(serie["2026-10-01"]["previsto_acumulado"], "90000.00")

    def test_mes_com_consumo_e_sem_previsao_aparece_na_serie(self):
        """O desvio que a curva existe para revelar não pode sumir da série."""
        from django.utils import timezone

        orc = self._cenario()
        self._consumir("5000", timezone.make_aware(timezone.datetime(2026, 12, 20, 10, 0)))

        curva = controle.curva_s(orc)
        meses = [linha["competencia"].isoformat() for linha in curva["serie"]]

        self.assertIn("2026-12-01", meses)
        dezembro = curva["serie"][-1]
        self.assertEqual(dezembro["previsto"], "0.00")
        self.assertEqual(dezembro["realizado"], "5000.00")

    def test_curva_sem_cronograma_nao_divide_por_zero(self):
        orc = self._orcamento()
        curva = controle.curva_s(orc)
        self.assertEqual(curva["total_previsto"], "0.00")
        self.assertEqual(curva["serie"], [])


class ControleAPITests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_controle_pela_api_traz_a_nota_de_cobertura(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="100000", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)

        resp = self.client.get(f"/api/orcamento/controle/?obra={self.obra.pk}")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Decimal(resp.data["obras"][0]["orcado"]), Decimal("100000.00"))
        self.assertIn("atribuída à obra", resp.data["nota_realizado"])

    def test_controle_exige_permissao_de_relatorio(self):
        self.autenticar(perms=["orcamento.orcamento.view"])
        resp = self.client.get("/api/orcamento/controle/")
        self.assertEqual(resp.status_code, 403)

    def test_distribuir_cronograma_pela_api(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="120000", etapa=self.fundacao)
        planilha.recalcular_orcamento(orc)

        resp = self.client.post(
            f"/api/orcamento/orcamentos/{orc.pk}/distribuir-cronograma/",
            {"inicio": "2026-08-01", "fim": "2026-10-01"}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["total"], "120000.00")
        self.assertEqual(len(resp.data["competencias"]), 3)

    def test_data_invalida_no_cronograma_e_400(self):
        orc = self._orcamento()
        resp = self.client.post(
            f"/api/orcamento/orcamentos/{orc.pk}/distribuir-cronograma/",
            {"inicio": "nao-e-data", "fim": "2026-10-01"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cronograma_de_orcamento_aprovado_e_409(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="1000", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)

        resp = self.client.post(
            f"/api/orcamento/orcamentos/{orc.pk}/distribuir-cronograma/",
            {"inicio": "2026-08-01", "fim": "2026-09-01"}, format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_editar_parcela_recalcula_o_valor(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="100000", etapa=self.fundacao)
        planilha.recalcular_orcamento(orc)

        resp = self.client.post("/api/orcamento/parcelas/", {
            "orcamento": orc.pk, "etapa": self.fundacao.pk,
            "competencia": "2026-08-15", "percentual": "40.0000",
        }, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        parcela = ParcelaEtapa.objects.get(pk=resp.data["parcela_id"])
        # A competência é normalizada para o dia 1 do mês.
        self.assertEqual(parcela.competencia, date(2026, 8, 1))
        self.assertEqual(parcela.valor_previsto, Decimal("40000.00"))

    def test_curva_s_pela_api(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="90000", etapa=self.fundacao)
        planilha.recalcular_orcamento(orc)
        controle.distribuir_linear(orc, inicio=date(2026, 8, 1), fim=date(2026, 10, 1))

        resp = self.client.get(f"/api/orcamento/orcamentos/{orc.pk}/curva-s/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["total_previsto"], "90000.00")
        self.assertEqual(resp.data["fonte_realizado"], "consumo_fisico_sil")

    def test_parcela_com_etapa_de_outra_obra_e_400(self):
        from obras.models import EtapaObra, Obra

        outra = Obra.objects.create(tenant=self.tenant, nome_obra="Outra", endereco="Rua B")
        alheia = EtapaObra.objects.create(
            tenant=self.tenant, obra=outra, nome_etapa="Fundação", ordem=1
        )
        orc = self._orcamento()

        resp = self.client.post("/api/orcamento/parcelas/", {
            "orcamento": orc.pk, "etapa": alheia.pk,
            "competencia": "2026-08-01", "percentual": "100",
        }, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
