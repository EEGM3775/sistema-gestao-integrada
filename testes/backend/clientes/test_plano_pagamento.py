"""Testes do motor da proposta.

Os valores conferidos aqui foram calculados à parte (fórmula do Price e do SAC),
não capturados da própria saída — teste que só repete o que o código faz não
prova nada sobre o cálculo estar certo.
"""
from datetime import date, timedelta
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


def fd(valor, parcelas, juros="0", sistema="price", **extra):
    """Um financiamento direto, para os testes lerem como a venda se fala."""
    return dict(tipo="financiamento_direto", valor=Decimal(valor), parcelas=parcelas,
                juros_mensal=Decimal(juros), sistema_amortizacao=sistema, **extra)


def entrada(valor, parcelas=1, juros="0", **extra):
    return dict(tipo="entrada", valor=Decimal(valor), parcelas=parcelas,
                juros_mensal=Decimal(juros), **extra)


class PropostaTests(SimpleTestCase):

    def test_desconto_percentual_e_valor_somam(self):
        plano = pp.montar(
            valor_tabela=Decimal("100000"), desconto_percentual=Decimal("10"),
            desconto_valor=Decimal("5000"),
            meios=[dict(tipo="a_vista", valor="85000")],
            data_compra=date(2026, 1, 10),
        )
        self.assertEqual(plano.desconto, Decimal("15000.00"))
        self.assertEqual(plano.valor_negociado, Decimal("85000.00"))

    def test_a_conta_so_fecha_quando_os_meios_somam_o_negociado(self):
        """Faltar é saldo sem dono; sobrar é cobrar mais do que se negociou. O
        erro diz quanto, em reais — é o vendedor que lê."""
        with self.assertRaisesMessage(ValueError, "Faltam R$ 10.000,00"):
            pp.montar(valor_tabela=Decimal("100000"), meios=[fd("90000", 12)])
        with self.assertRaisesMessage(ValueError, "passam R$ 5.000,00"):
            pp.montar(valor_tabela=Decimal("100000"),
                      meios=[entrada("20000"), fd("85000", 12)])

    def test_venda_sem_meio_nenhum_e_recusada(self):
        with self.assertRaises(ValueError):
            pp.montar(valor_tabela=Decimal("50000"), meios=[])

    def test_entrada_parcelada_nao_rende_juros_por_padrao(self):
        plano = pp.montar(
            valor_tabela=Decimal("60000"),
            meios=[entrada("12000", 6), fd("48000", 48, juros="1")],
            data_compra=date(2026, 1, 10),
        )
        entradas = [p for p in plano.parcelas if p.tipo == "entrada"]
        self.assertEqual(len(entradas), 6)
        self.assertEqual(sum(p.valor for p in entradas), Decimal("12000.00"))
        self.assertEqual(sum(p.juros for p in entradas), Decimal("0"))

    def test_entrada_parcelada_pode_cobrar_juros_quando_o_contrato_cobra(self):
        """A entrada longa às vezes cobra juros: a taxa é opcional e, quando
        vem, a entrada vira um Price curto. 12.000 em 6x a 1% a.m. → 2.070,58
        (fórmula do Price)."""
        plano = pp.montar(
            valor_tabela=Decimal("12000"), meios=[entrada("12000", 6, juros="1")],
            data_compra=date(2026, 1, 10),
        )
        self.assertEqual(plano.parcelas[0].valor, Decimal("2070.58"))
        self.assertGreater(plano.total_juros, 0)
        self.assertEqual(plano.meios[0].detalhe, "6x 1% a.m.")

    def test_entrada_em_uma_vez_nao_tem_prazo_para_juros(self):
        plano = pp.montar(
            valor_tabela=Decimal("12000"), meios=[entrada("12000", 1, juros="2")],
        )
        self.assertEqual(plano.total, Decimal("12000.00"))
        self.assertEqual(plano.total_juros, Decimal("0"))

    def test_anuais_sao_um_meio_a_parte_e_nao_pagam_juros(self):
        """As anuais têm o próprio valor: o financiamento direto só leva juros
        sobre o que é dele."""
        plano = pp.montar(
            valor_tabela=Decimal("100000"),
            meios=[
                entrada("20000"), fd("60000", 36, juros="1"),
                dict(tipo="anuais", valor="20000", parcelas=2),
            ],
            data_compra=date(2026, 1, 10),
        )
        anuais = [p for p in plano.parcelas if p.tipo == "balao"]
        self.assertEqual([p.valor for p in anuais], [Decimal("10000.00")] * 2)
        self.assertEqual(sum(p.juros for p in anuais), Decimal("0"))
        self.assertEqual(plano.baloes, Decimal("20000.00"))
        self.assertEqual(plano.saldo_financiado, Decimal("60000.00"))
        self.assertEqual(anuais[0].vencimento, date(2027, 1, 10))

    def test_total_e_a_soma_do_carne(self):
        plano = pp.montar(
            valor_tabela=Decimal("250000"), desconto_percentual=Decimal("5"),
            meios=[
                entrada("50000", 5), fd("142500", 60, juros="0.8", sistema="sac"),
                dict(tipo="anuais", valor="45000", parcelas=3, periodicidade="anual"),
            ],
            data_compra=date(2026, 3, 20),
        )
        self.assertEqual(plano.total, sum(p.valor for p in plano.parcelas))
        self.assertEqual(len([p for p in plano.parcelas if p.tipo == "balao"]), 3)
        # Com juros, o desembolso é maior que o negociado à vista.
        self.assertGreater(plano.total, plano.valor_negociado)

    def test_dois_financiamentos_diretos_com_taxas_diferentes(self):
        """A lista é livre: 24x sem juros de um lado, 60x a 1% do outro. Cada
        um tem a sua série, e o carnê não mistura as duas numa "1/84"."""
        plano = pp.montar(
            valor_tabela=Decimal("100000"),
            meios=[fd("20000", 24), fd("80000", 60, juros="1")],
            data_compra=date(2026, 1, 10),
        )
        primeiro = [p for p in plano.parcelas if p.meio == 1]
        segundo = [p for p in plano.parcelas if p.meio == 2]
        self.assertEqual(len(primeiro), 24)
        self.assertEqual({p.juros for p in primeiro}, {Decimal("0")})
        self.assertEqual(len(segundo), 60)
        # 80.000 em 60x a 1% a.m. pelo Price → 1.779,56
        self.assertEqual(segundo[0].valor, Decimal("1779.56"))

        class _Aquisicao:
            empreendimento = None

            class unidade:
                rotulo = "QD 1 · LT 01"

        textos = pp.descricoes_do_carne(plano, _Aquisicao())
        self.assertIn("Parcela 1/24 (1ª série) — QD 1 · LT 01", textos)
        self.assertIn("Parcela 60/60 (2ª série) — QD 1 · LT 01", textos)

    def test_venda_a_vista_e_um_titulo_so(self):
        plano = pp.montar(
            valor_tabela=Decimal("80000"), meios=[dict(tipo="a_vista", valor="80000")],
            data_compra=date(2026, 5, 2),
        )
        self.assertEqual(len(plano.parcelas), 1)
        self.assertEqual(plano.parcelas[0].vencimento, date(2026, 5, 2))
        self.assertEqual(plano.total, Decimal("80000.00"))
        self.assertEqual(plano.condicao, "a_vista")

    def test_carne_sai_em_ordem_de_vencimento(self):
        plano = pp.montar(
            valor_tabela=Decimal("120000"),
            meios=[
                entrada("24000", 3), fd("72000", 24, juros="1"),
                dict(tipo="anuais", valor="24000", parcelas=2, periodicidade="semestral"),
            ],
            data_compra=date(2026, 1, 15),
        )
        vencimentos = [p.vencimento for p in plano.parcelas]
        self.assertEqual(vencimentos, sorted(vencimentos))

    def test_desconto_maior_que_a_tabela_e_recusado(self):
        with self.assertRaises(ValueError):
            pp.montar(valor_tabela=Decimal("1000"), desconto_valor=Decimal("1200"))


class MeiosDePagamentoTests(SimpleTestCase):
    """Cada meio comporta um plano diferente — e quatro deles não viram título.

    O resumo fala cada meio pelo nome do dinheiro: "Financiado pelo banco",
    "Pago em permuta — Gol 2019". Antes todos viravam um "Quitado fora do
    carnê" calculado por diferença, que não dizia de onde vinha o dinheiro.
    """

    def test_sinal_mais_banco_e_financiamento_bancario(self):
        plano = pp.montar(
            valor_tabela=Decimal("300000"),
            meios=[
                entrada("30000", 2),
                dict(tipo="financiamento_bancario", valor="270000", descricao="Caixa"),
            ],
            data_compra=date(2026, 5, 2),
        )
        self.assertEqual(len(plano.parcelas), 2)
        self.assertEqual(plano.total, Decimal("30000.00"))
        self.assertEqual(plano.fora_do_carne, Decimal("270000.00"))
        self.assertEqual(plano.meios[1].rotulo, "Financiado pelo banco — Caixa")
        self.assertFalse(plano.meios[1].no_carne)
        # A venda leva o nome do meio que responde pela maior parte.
        self.assertEqual(plano.condicao, "financiamento_bancario")

    def test_permuta_exige_dizer_o_que_foi_permutado(self):
        with self.assertRaisesMessage(ValueError, "o que foi dado em permuta"):
            pp.montar(valor_tabela=Decimal("100000"),
                      meios=[dict(tipo="permuta", valor="100000")])
        plano = pp.montar(
            valor_tabela=Decimal("100000"),
            meios=[dict(tipo="permuta", valor="100000", descricao="Terreno na Rua B")],
        )
        self.assertEqual(plano.parcelas, [])
        self.assertEqual(plano.meios[0].rotulo, "Pago em permuta — Terreno na Rua B")

    def test_outro_e_um_texto_que_explica_a_condicao(self):
        """"Outro" sem explicação é um valor sem dono: a venda não fecha."""
        with self.assertRaisesMessage(ValueError, "explique a condição"):
            pp.montar(valor_tabela=Decimal("50000"),
                      meios=[dict(tipo="outro", valor="50000", descricao="   ")])
        plano = pp.montar(
            valor_tabela=Decimal("50000"),
            meios=[dict(tipo="outro", valor="50000", descricao="5 cheques pré-datados")],
        )
        self.assertEqual(plano.parcelas, [])
        self.assertEqual(plano.fora_do_carne, Decimal("50000.00"))
        self.assertEqual(plano.meios[0].rotulo, "Outro — 5 cheques pré-datados")

    def test_o_meio_apaga_o_que_ele_nao_comporta(self):
        """Prazo e juros num FGTS são descartados — não há carnê para eles. O
        nome do banco, no financiamento bancário, fica: é o que o meio é."""
        meio = pp.meio_de(dict(
            tipo="fgts", valor="30000", parcelas=36, juros_mensal="2",
            sistema_amortizacao="sac", descricao="conta 1",
        ))
        self.assertEqual((meio.parcelas, meio.juros_mensal, meio.sistema_amortizacao),
                         (1, Decimal("0"), "price"))
        self.assertEqual(meio.descricao, "")
        banco = pp.meio_de(dict(tipo="financiamento_bancario", valor="1", descricao=" Caixa "))
        self.assertEqual(banco.descricao, "Caixa")

    def test_cartao_e_um_titulo_da_operadora(self):
        """O parcelamento do cartão é da operadora: fica registrado, mas o
        título a receber é um só."""
        plano = pp.montar(
            valor_tabela=Decimal("50000"),
            meios=[dict(tipo="cartao", valor="50000", parcelas=10, juros_mensal="2")],
            data_compra=date(2026, 5, 2),
        )
        self.assertEqual(len(plano.parcelas), 1)
        self.assertEqual(plano.total_juros, Decimal("0"))
        self.assertEqual(plano.meios[0].detalhe, "10x na operadora")

    def test_forma_desconhecida_e_recusada(self):
        with self.assertRaises(ValueError):
            pp.montar(valor_tabela=Decimal("50000"),
                      meios=[dict(tipo="inventada", valor="50000")])

    def test_meio_sem_valor_e_recusado(self):
        with self.assertRaisesMessage(ValueError, "Meio 2"):
            pp.montar(valor_tabela=Decimal("50000"),
                      meios=[dict(tipo="a_vista", valor="50000"), fd("0", 12)])

    def test_teto_de_meios_vem_do_payment(self):
        from payment.planos import VENDA_TETO_MEIOS_DE_PAGAMENTO as teto

        meios = [dict(tipo="a_vista", valor="1")] * (teto + 1)
        with self.assertRaisesMessage(ValueError, f"até {teto} meios"):
            pp.montar(valor_tabela=Decimal(teto + 1), meios=meios)

    def test_catalogo_cobre_as_escolhas_do_modelo(self):
        """A tela lê o catálogo daqui; se o modelo ganhar um meio novo e o
        catálogo não, o formulário mostraria uma opção sem regra."""
        from clientes.models import ClienteEmpreendimento, MeioPagamento

        self.assertEqual({c for c, _ in MeioPagamento.TIPO_CHOICES}, set(pp.TIPOS_DE_MEIO))
        condicoes = {c for c, _ in ClienteEmpreendimento.CONDICOES_PAGAMENTO_CHOICES}
        self.assertLessEqual({t.condicao for t in pp.TIPOS_DE_MEIO.values()}, condicoes)


class AjusteDeVencimentoTests(SimpleTestCase):
    """O calendário entra **injetado**: o motor continua puro e testável sem banco."""

    class _FimDeSemana:
        """Um ajustador de mentira, com a mesma interface do de verdade."""

        def explicar(self, dia):
            original = dia
            while dia.weekday() >= 5:
                dia += timedelta(days=1)
            return dia, ("fim de semana" if dia != original else "")

    def test_parcela_de_sabado_vai_para_segunda_e_guarda_a_data_do_contrato(self):
        plano = pp.montar(
            valor_tabela=Decimal("12000"),
            meios=[fd("12000", 12, primeiro_vencimento=date(2026, 3, 7))],  # sábado
            ajustar_vencimento=self._FimDeSemana(),
        )
        primeira = plano.parcelas[0]
        self.assertEqual(primeira.vencimento_contratual, date(2026, 3, 7))
        self.assertEqual(primeira.vencimento, date(2026, 3, 9))
        self.assertEqual(primeira.ajuste_motivo, "fim de semana")
        self.assertTrue(primeira.ajustada)

    def test_o_ajuste_nao_mexe_em_um_centavo(self):
        """Empurrar a data não acrescenta juro: juros correm por parcela, não por
        dia corrido. Se acrescentassem, o carnê exibido na venda não fecharia com
        o carnê emitido."""
        comum = dict(
            valor_tabela=Decimal("120000"),
            meios=[
                entrada("24000", 3), fd("84000", 24, juros="1"),
                dict(tipo="anuais", valor="12000", parcelas=2),
            ],
            data_compra=date(2026, 1, 10),
        )
        sem = pp.montar(**comum)
        com = pp.montar(**comum, ajustar_vencimento=self._FimDeSemana())
        self.assertEqual(sem.total, com.total)
        self.assertEqual(sem.total_juros, com.total_juros)
        self.assertEqual([p.valor for p in sem.parcelas], [p.valor for p in com.parcelas])

    def test_sem_ajustador_o_carne_e_o_do_contrato_cru(self):
        plano = pp.montar(
            valor_tabela=Decimal("12000"),
            meios=[fd("12000", 3, primeiro_vencimento=date(2026, 3, 7))],
        )
        self.assertEqual(plano.parcelas[0].vencimento, date(2026, 3, 7))
        self.assertEqual(plano.parcelas_ajustadas, 0)
