# testes/backend/modulopdca/test_reajuste_contrato.py
"""Reajuste por fórmula paramétrica e contrato de receita (10/10/2026).

O reajuste saiu do Orçamento: é cláusula de contrato. O motor é
`nucleo/reajuste.py`, sobre a série única de índices; a medição guarda o
reajuste do período. O mesmo contrato serve ao empreiteiro (custo, conta a
pagar) e ao contratante (receita, conta a receber).
"""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction

from clientes.models import Cliente
from moduloerp.models import ContaPagar, ContaReceber
from nucleo import reajuste as motor
from nucleo.models import IndiceEconomico, ValorIndice
from modulopdca import services
from modulopdca.models import LadoContrato, ParcelaReajusteContrato

from .tests import BaseContrato


class SerieDeIndice:
    """Constrói a série com número-índice: 100 na data-base, 110 um ano depois."""

    @staticmethod
    def incc(codigo="incc-t", base=date(2026, 1, 1), numero_base="100", numero_t="110", meses=12):
        indice = IndiceEconomico.objects.create(codigo=codigo, nome=codigo.upper())
        ValorIndice.objects.create(indice=indice, competencia=base, numero_indice=Decimal(numero_base))
        if numero_t is not None:
            ano = base.year + (base.month - 1 + meses) // 12
            mes = (base.month - 1 + meses) % 12 + 1
            ValorIndice.objects.create(indice=indice, competencia=date(ano, mes, 1), numero_indice=Decimal(numero_t))
        return indice


class MotorTests(BaseContrato):
    def test_razao_pelo_numero_indice(self):
        incc = SerieDeIndice.incc()
        r = motor.razao_entre(incc, date(2026, 1, 1), date(2027, 1, 1))
        self.assertEqual((r.valor, r.provisorio, r.metodo), (Decimal("1.100000"), False, "numero_indice"))

    def test_razao_por_variacoes_compostas_e_nunca_somadas(self):
        ipca = IndiceEconomico.objects.create(codigo="ipca-t", nome="IPCA")
        for mes in (2, 3):
            ValorIndice.objects.create(indice=ipca, competencia=date(2026, mes, 1), variacao_percentual=Decimal("1"))
        r = motor.razao_entre(ipca, date(2026, 1, 1), date(2026, 3, 1))
        self.assertEqual((r.valor, r.metodo), (Decimal("1.020100"), "variacoes"))  # 1,01² e não 1,02

    def test_indice_nao_publicado_vira_provisorio_e_diz_qual_competencia_valeu(self):
        incc = SerieDeIndice.incc(numero_t=None)
        ValorIndice.objects.create(indice=incc, competencia=date(2026, 7, 1), numero_indice=Decimal("105"))
        r = motor.razao_entre(incc, date(2026, 1, 1), date(2027, 1, 1))
        self.assertTrue(r.provisorio)
        self.assertEqual(r.competencia_usada, date(2026, 7, 1))

    def test_serie_vazia_depois_da_base_e_recusada(self):
        incc = SerieDeIndice.incc(numero_t=None)
        with self.assertRaises(motor.ReajusteInvalido):
            motor.razao_entre(incc, date(2026, 1, 1), date(2027, 1, 1))

    def test_formula_que_nao_fecha_e_recusada(self):
        incc = SerieDeIndice.incc()
        with self.assertRaises(motor.ReajusteInvalido):
            motor.fator(parcela_fixa=Decimal("0.10"), parcelas=[(incc, Decimal("0.80"), "")],
                        data_base=date(2026, 1, 1), ciclo=1)

    def test_fator_e_truncado_nao_arredondado(self):
        incc = SerieDeIndice.incc(numero_t="110.996")
        r = motor.fator(parcela_fixa=Decimal("0"), parcelas=[(incc, Decimal("1"), "")],
                        data_base=date(2026, 1, 1), ciclo=1, casas=4)
        self.assertEqual(r["fator"], "1.1099")

    def test_aniversario_nao_e_o_mes_da_medicao(self):
        # Antes do 1º aniversário não há reajuste; depois, o ciclo 1 vale até o 2º.
        self.assertEqual(motor.ciclos_completos(date(2026, 1, 15), date(2026, 12, 31), 12), 0)
        self.assertEqual(motor.ciclos_completos(date(2026, 1, 15), date(2027, 1, 15), 12), 1)
        self.assertEqual(motor.ciclos_completos(date(2026, 1, 15), date(2027, 12, 31), 12), 1)
        self.assertEqual(motor.ciclos_completos(date(2026, 1, 15), date(2028, 1, 15), 12), 2)

    def test_periodo_que_atravessa_o_aniversario_divide_pelos_dias(self):
        incc = SerieDeIndice.incc()  # 100 → 110 em jan/2027
        r = motor.reajuste_do_periodo(
            valor=Decimal("1000"), inicio=date(2027, 1, 1), fim=date(2027, 1, 31),
            parcela_fixa=Decimal("0"), parcelas=[(incc, Decimal("1"), "")],
            data_base=date(2026, 1, 1),
        )
        # Aniversário em 01/01/2027: o mês inteiro já é do ciclo 1 → 10%.
        self.assertEqual(r["valor"], "100.00")
        r = motor.reajuste_do_periodo(
            valor=Decimal("1000"), inicio=date(2026, 12, 16), fim=date(2027, 1, 15),
            parcela_fixa=Decimal("0"), parcelas=[(incc, Decimal("1"), "")],
            data_base=date(2026, 1, 1),
        )
        # 31 dias; 15 depois do aniversário (01–15/01) → metade do 10%, cerca de 48,39.
        self.assertEqual(r["valor"], "48.39")


class MedicaoComReajusteTests(BaseContrato):
    def setUp(self):
        super().setUp()
        self.incc = SerieDeIndice.incc("incc-m", base=date(2026, 6, 1), meses=12)
        self.contrato.reajuste_data_base = date(2026, 6, 1)
        self.contrato.save(update_fields=["reajuste_data_base"])
        ParcelaReajusteContrato.objects.create(
            tenant=self.tenant, contrato=self.contrato, indice=self.incc, peso=Decimal("1"), rotulo="Geral",
        )

    def _medicao(self, inicio, fim, qtd):
        return services.criar_medicao(
            contrato=self.contrato, inicio=inicio, fim=fim,
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": qtd}],
        )

    def test_antes_do_aniversario_nao_ha_reajuste(self):
        m = self._medicao(date(2026, 7, 1), date(2026, 7, 31), "100")
        self.assertEqual(m.valor_reajuste, Decimal("0.00"))
        self.assertEqual(services.totais_da_medicao(m)["liquido"], Decimal("8000.00"))

    def test_depois_do_aniversario_o_reajuste_soma_ao_bruto_e_alimenta_o_titulo(self):
        m = self._medicao(date(2027, 7, 1), date(2027, 7, 31), "100")  # 8.000 × 10%
        self.assertEqual(m.valor_reajuste, Decimal("800.00"))
        totais = services.totais_da_medicao(m)
        self.assertEqual((totais["bruto"], totais["reajuste"], totais["liquido"]),
                         (Decimal("8000.00"), Decimal("800.00"), Decimal("8800.00")))
        services._congelar_medicao(m, aprovada=True)
        conta = ContaPagar.objects.get(pk=m.conta_pagar_ref)
        self.assertEqual(conta.valor, Decimal("8800.00"))
        self.assertIn("reajuste", conta.descricao)

    def test_retencao_incide_sobre_o_reajustado(self):
        self.contrato.retencao_percentual = Decimal("10")
        self.contrato.retencao_natureza = "caucao"
        self.contrato.save(update_fields=["retencao_percentual", "retencao_natureza"])
        m = self._medicao(date(2027, 7, 1), date(2027, 7, 31), "100")
        self.assertEqual(services.totais_da_medicao(m)["retencao"], Decimal("880.00"))

    def test_contrato_a_preco_fixo_nao_tem_reajuste(self):
        self.contrato.parcelas_reajuste.all().delete()
        m = self._medicao(date(2027, 7, 1), date(2027, 7, 31), "100")
        self.assertEqual((m.valor_reajuste, m.reajuste_memoria), (Decimal("0.00"), {}))


class ContratoDeReceitaTests(BaseContrato):
    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(
            tenant=self.tenant, nome_completo="Prefeitura de Nazaré", cpf_cnpj="11222333000181",
            data_nascimento=date(2000, 1, 1),
        )

    def _receita(self, **extra):
        return self.criar_contrato(
            numero="R-1", lado=LadoContrato.RECEITA, fornecedor=None, cliente=self.cliente, **extra,
        )

    def test_a_constraint_cobra_exatamente_uma_parte_conforme_o_lado(self):
        for campos in (
            dict(lado=LadoContrato.CUSTO, fornecedor=None, cliente=self.cliente),
            dict(lado=LadoContrato.RECEITA, fornecedor=self.fornecedor, cliente=self.cliente),
            dict(lado=LadoContrato.RECEITA, fornecedor=None, cliente=None),
        ):
            with self.subTest(campos), self.assertRaises(IntegrityError), transaction.atomic():
                self.criar_contrato(numero="X", **campos)

    def test_medicao_aprovada_gera_conta_a_receber_e_nao_a_pagar(self):
        contrato = self._receita()
        item = self.criar_item("9.1", "Obra contratada", qtd="100", preco="50", contrato=contrato, atividade=self.alvenaria)
        m = services.criar_medicao(
            contrato=contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
            linhas=[{"item_contrato_id": item.pk, "quantidade": "10"}],
        )
        services._congelar_medicao(m, aprovada=True)
        m.refresh_from_db()
        self.assertIsNone(m.conta_pagar_ref)
        conta = ContaReceber.objects.get(pk=m.conta_receber_ref)
        self.assertEqual((conta.valor, conta.cliente_id), (Decimal("500.00"), self.cliente.pk))
        self.assertEqual(services.titulo_da_medicao(m).pk, conta.pk)
        self.assertEqual(services.estado_do_titulo(m)["lado"], "receita")

    def test_parte_nome_vem_do_lado(self):
        self.assertEqual(self._receita().parte_nome, "Prefeitura de Nazaré")
        self.assertEqual(self.contrato.parte_nome, "Empreiteira Alfa")
