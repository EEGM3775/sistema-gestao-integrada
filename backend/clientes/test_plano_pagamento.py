"""Testes do motor da proposta.

Os valores conferidos aqui foram calculados à parte (fórmula do Price e do SAC),
não capturados da própria saída — teste que só repete o que o código faz não
prova nada sobre o cálculo estar certo.
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from clientes import plano_pagamento as pp


class SomarMesesTests(SimpleTestCase):

    def test_dia_31_cai_no_ultimo_dia_do_mes_curto(self):
        self.assertEqual(pp.somar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_atravessa_o_ano(self):
        self.assertEqual(pp.somar_meses(date(2026, 11, 15), 3), date(2027, 2, 15))

    def test_fevereiro_de_ano_bissexto(self):
        self.assertEqual(pp.somar_meses(date(2028, 1, 31), 1), date(2028, 2, 29))


class PriceTests(SimpleTestCase):

    def test_parcela_fixa_pela_formula(self):
        """PV=10.000, i=1% a.m., n=12 → PMT = 888,49 (fórmula do Price)."""
        linhas = pp.price(Decimal("10000"), Decimal("0.01"), 12)
        self.assertEqual(len(linhas), 12)
        self.assertEqual(linhas[0][0], Decimal("888.49"))
        # Todas iguais menos a última, que fecha o saldo.
        self.assertEqual({l[0] for l in linhas[:-1]}, {Decimal("888.49")})

    def test_saldo_zera_na_ultima(self):
        linhas = pp.price(Decimal("10000"), Decimal("0.01"), 12)
        self.assertEqual(linhas[-1][3], Decimal("0"))

    def test_soma_das_amortizacoes_e_o_principal(self):
        linhas = pp.price(Decimal("10000"), Decimal("0.01"), 12)
        self.assertEqual(sum(l[2] for l in linhas), Decimal("10000.00"))

    def test_sem_juros_e_divisao_simples(self):
        linhas = pp.price(Decimal("12000"), Decimal("0"), 12)
        self.assertEqual({l[0] for l in linhas}, {Decimal("1000.00")})
        self.assertEqual(sum(l[1] for l in linhas), Decimal("0"))

    def test_sem_juros_com_divisao_inexata_fecha_na_ultima(self):
        """1.000 em 3x: 333,33 + 333,33 + 333,34 — nunca 999,99."""
        linhas = pp.price(Decimal("1000"), Decimal("0"), 3)
        self.assertEqual([l[0] for l in linhas],
                         [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")])
        self.assertEqual(sum(l[0] for l in linhas), Decimal("1000.00"))


class SacTests(SimpleTestCase):

    def test_amortizacao_constante_e_parcela_decrescente(self):
        """PV=12.000, i=1%, n=12 → amortiza 1.000/mês; 1ª = 1.120, 2ª = 1.110."""
        linhas = pp.sac(Decimal("12000"), Decimal("0.01"), 12)
        self.assertEqual(linhas[0][0], Decimal("1120.00"))
        self.assertEqual(linhas[1][0], Decimal("1110.00"))
        self.assertEqual(linhas[-1][0], Decimal("1010.00"))
        self.assertEqual({l[2] for l in linhas}, {Decimal("1000.00")})

    def test_sac_paga_menos_juros_que_price(self):
        """O motivo de existirem os dois — e o que o vendedor precisa mostrar."""
        juros_sac = sum(l[1] for l in pp.sac(Decimal("12000"), Decimal("0.01"), 12))
        juros_price = sum(l[1] for l in pp.price(Decimal("12000"), Decimal("0.01"), 12))
        self.assertLess(juros_sac, juros_price)


class PropostaTests(SimpleTestCase):

    def test_desconto_percentual_e_valor_somam(self):
        plano = pp.montar(
            valor_tabela=Decimal("100000"), desconto_percentual=Decimal("10"),
            desconto_valor=Decimal("5000"), entrada_valor=Decimal("85000"),
            data_compra=date(2026, 1, 10),
        )
        self.assertEqual(plano.desconto, Decimal("15000.00"))
        self.assertEqual(plano.valor_negociado, Decimal("85000.00"))

    def test_entrada_parcelada_nao_rende_juros(self):
        plano = pp.montar(
            valor_tabela=Decimal("60000"), entrada_valor=Decimal("12000"),
            entrada_parcelas=6, juros_mensal=Decimal("1"), num_parcelas=48,
            data_compra=date(2026, 1, 10),
        )
        entradas = [p for p in plano.parcelas if p.tipo == "entrada"]
        self.assertEqual(len(entradas), 6)
        self.assertEqual(sum(p.valor for p in entradas), Decimal("12000.00"))
        self.assertEqual(sum(p.juros for p in entradas), Decimal("0"))

    def test_balao_abate_saldo_antes_do_parcelamento(self):
        """Sem isso o comprador pagaria juros sobre o que já se comprometeu a
        quitar à parte, e o total do plano estouraria."""
        com_balao = pp.montar(
            valor_tabela=Decimal("100000"), entrada_valor=Decimal("20000"),
            juros_mensal=Decimal("1"), num_parcelas=36,
            balao_valor=Decimal("10000"), balao_quantidade=2,
            data_compra=date(2026, 1, 10),
        )
        self.assertEqual(com_balao.baloes, Decimal("20000.00"))
        self.assertEqual(com_balao.saldo_financiado, Decimal("60000.00"))
        sem_balao = pp.montar(
            valor_tabela=Decimal("100000"), entrada_valor=Decimal("20000"),
            juros_mensal=Decimal("1"), num_parcelas=36, data_compra=date(2026, 1, 10),
        )
        self.assertLess(com_balao.total, sem_balao.total)

    def test_total_e_a_soma_do_carne(self):
        plano = pp.montar(
            valor_tabela=Decimal("250000"), desconto_percentual=Decimal("5"),
            entrada_valor=Decimal("50000"), entrada_parcelas=5,
            sistema="sac", juros_mensal=Decimal("0.8"), num_parcelas=60,
            balao_valor=Decimal("15000"), balao_quantidade=3, balao_periodicidade="anual",
            data_compra=date(2026, 3, 20),
        )
        self.assertEqual(plano.total, sum(p.valor for p in plano.parcelas))
        self.assertEqual(len([p for p in plano.parcelas if p.tipo == "balao"]), 3)
        # Com juros, o desembolso é maior que o negociado à vista.
        self.assertGreater(plano.total, plano.valor_negociado)

    def test_venda_a_vista_nao_gera_parcela_mensal(self):
        plano = pp.montar(
            valor_tabela=Decimal("80000"), entrada_valor=Decimal("80000"),
            entrada_parcelas=1, data_compra=date(2026, 5, 2),
        )
        self.assertEqual(plano.saldo_financiado, Decimal("0"))
        self.assertEqual(len(plano.parcelas), 1)
        self.assertEqual(plano.total, Decimal("80000.00"))

    def test_carne_sai_em_ordem_de_vencimento(self):
        plano = pp.montar(
            valor_tabela=Decimal("120000"), entrada_valor=Decimal("24000"), entrada_parcelas=3,
            juros_mensal=Decimal("1"), num_parcelas=24,
            balao_valor=Decimal("12000"), balao_quantidade=2, balao_periodicidade="semestral",
            data_compra=date(2026, 1, 15),
        )
        vencimentos = [p.vencimento for p in plano.parcelas]
        self.assertEqual(vencimentos, sorted(vencimentos))

    def test_desconto_maior_que_a_tabela_e_recusado(self):
        with self.assertRaises(ValueError):
            pp.montar(valor_tabela=Decimal("1000"), desconto_valor=Decimal("1200"))

    def test_entrada_maior_que_o_negociado_e_recusada(self):
        with self.assertRaises(ValueError):
            pp.montar(valor_tabela=Decimal("1000"), entrada_valor=Decimal("1500"))

    def test_saldo_sem_prazo_e_recusado(self):
        with self.assertRaises(ValueError):
            pp.montar(valor_tabela=Decimal("50000"), entrada_valor=Decimal("10000"),
                      num_parcelas=0)
