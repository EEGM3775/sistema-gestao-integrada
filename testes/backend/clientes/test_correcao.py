"""A correção monetária: onde ela ancora, quando incide e o que ela não faz.

O que estes testes protegem é a diferença entre corrigir certo e corrigir quase
certo — que num contrato de 10 anos é a diferença entre o saldo fechar e o
cliente ir ao Procon.
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APITestCase

from clientes import correcao
from clientes.models import Cliente, ClienteEmpreendimento
from empreendimentos.models import Empreendimento, Unidade
from moduloerp.models import ContaReceber, StatusConta
from nucleo.models import IndiceEconomico, Tenant, Usuario, ValorIndice


class AniversarioTests(SimpleTestCase):
    """O marco do reajuste anual é o aniversário do contrato."""

    BASE = date(2026, 3, 15)

    def test_antes_do_primeiro_aniversario_nao_ha_reajuste(self):
        self.assertIsNone(correcao.aniversario_vigente(self.BASE, date(2027, 3, 14)))

    def test_no_dia_do_aniversario_ja_reajusta(self):
        self.assertEqual(
            correcao.aniversario_vigente(self.BASE, date(2027, 3, 15)), date(2027, 3, 15),
        )

    def test_entre_aniversarios_o_valor_fica_parado(self):
        """Correção anual não é mensal diluída: sobe no aniversário e para."""
        self.assertEqual(
            correcao.aniversario_vigente(self.BASE, date(2027, 11, 30)), date(2027, 3, 15),
        )

    def test_29_de_fevereiro_cai_em_28_no_ano_comum(self):
        self.assertEqual(
            correcao.aniversario_vigente(date(2024, 2, 29), date(2025, 6, 1)), date(2025, 2, 28),
        )


class SerieBaseTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.indice = IndiceEconomico.objects.create(codigo="ipca", nome="IPCA", fonte="IBGE")
        # 24 meses a 1% — acumulado de 12 meses = 12,6825%, não 12%.
        for i in range(24):
            ano, mes = divmod(i, 12)
            ValorIndice.objects.create(
                indice=cls.indice, competencia=date(2026 + ano, mes + 1, 1),
                variacao_percentual=Decimal("1.0"),
            )


class FatorTests(SerieBaseTestCase):

    def test_o_fator_e_composto_e_nao_somado(self):
        """1% ao mês por 12 meses dá 12,6825% — somar daria 12% e subestimaria."""
        fator, aplicadas, ultima, faltando = correcao.fator_acumulado(
            self.indice, date(2026, 1, 1), date(2026, 12, 1),
        )
        self.assertEqual(aplicadas, 12)
        self.assertEqual(ultima, date(2026, 12, 1))
        self.assertEqual(faltando, 0)
        self.assertEqual(fator.quantize(Decimal("0.000001")), Decimal("1.126825"))

    def test_mes_sem_publicacao_e_relatado_e_nao_chutado(self):
        """Índice não publicado não vira zero nem projeção — vira aviso."""
        fator, aplicadas, _, faltando = correcao.fator_acumulado(
            self.indice, date(2026, 1, 1), date(2028, 6, 1),
        )
        self.assertEqual(aplicadas, 24)
        self.assertEqual(faltando, 6)
        self.assertGreater(fator, 1)

    def test_deflacao_reduz_o_valor(self):
        ValorIndice.objects.create(
            indice=self.indice, competencia=date(2029, 1, 1),
            variacao_percentual=Decimal("-0.5"),
        )
        fator, _, _, _ = correcao.fator_acumulado(
            self.indice, date(2029, 1, 1), date(2029, 1, 1),
        )
        self.assertEqual(fator, Decimal("0.99500000"))

    def test_sem_indice_o_fator_e_neutro(self):
        fator, aplicadas, _, _ = correcao.fator_acumulado(None, date(2026, 1, 1), date(2027, 1, 1))
        self.assertEqual(fator, Decimal("1"))
        self.assertEqual(aplicadas, 0)


class CorrigirTests(SerieBaseTestCase):

    BASE = date(2026, 1, 10)

    def test_no_primeiro_ano_o_valor_e_o_da_assinatura(self):
        r = correcao.corrigir(
            Decimal("1000.00"), indice=self.indice, data_base=self.BASE,
            referencia=date(2026, 11, 10), periodicidade="anual",
        )
        self.assertEqual(r.valor_corrigido, Decimal("1000.00"))
        self.assertEqual(r.fator, Decimal("1"))

    def test_no_aniversario_aplica_os_12_meses_acumulados(self):
        r = correcao.corrigir(
            Decimal("1000.00"), indice=self.indice, data_base=self.BASE,
            referencia=date(2027, 1, 10), periodicidade="anual",
        )
        self.assertEqual(r.competencias_aplicadas, 12)
        self.assertEqual(r.valor_corrigido, Decimal("1126.83"))

    def test_a_data_do_boleto_nao_e_ancora(self):
        """O ponto do item: cobrar em outro dia do mesmo período não muda o valor.

        Se a emissão fosse a âncora, rodar a régua de cobrança em outro dia daria
        outro número para a mesma parcela — e o contrato passaria a depender da
        agenda do financeiro.
        """
        valores = {
            correcao.corrigir(
                Decimal("1000.00"), indice=self.indice, data_base=self.BASE,
                referencia=ref, periodicidade="anual",
            ).valor_corrigido
            for ref in (date(2027, 1, 10), date(2027, 6, 1), date(2027, 12, 31))
        }
        self.assertEqual(len(valores), 1)

    def test_mensal_acumula_ate_o_mes_anterior(self):
        """INCC de obra: sobe todo mês, e nunca usa o mês ainda não publicado."""
        r = correcao.corrigir(
            Decimal("1000.00"), indice=self.indice, data_base=date(2026, 1, 1),
            referencia=date(2026, 7, 1), periodicidade="mensal",
        )
        self.assertEqual(r.competencias_aplicadas, 6)
        self.assertEqual(r.ate_competencia, date(2026, 6, 1))

    def test_contrato_sem_indice_nao_corrige(self):
        r = correcao.corrigir(
            Decimal("1000.00"), indice=None, data_base=self.BASE,
            referencia=date(2030, 1, 1), periodicidade="anual",
        )
        self.assertEqual(r.valor_corrigido, Decimal("1000.00"))


class CorrigirCarneTests(APITestCase):
    """O endpoint: prévia antes de aplicar, só o que está em aberto, sem compor
    o índice duas vezes."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="corr", nome="Loteadora Correção")
        cls.user = Usuario.objects.create(username="corretor", tenant=cls.tenant)
        cls.indice = IndiceEconomico.objects.create(codigo="ipca", nome="IPCA")
        for i in range(36):
            ano, mes = divmod(i, 12)
            ValorIndice.objects.create(
                indice=cls.indice, competencia=date(2024 + ano, mes + 1, 1),
                variacao_percentual=Decimal("1.0"),
            )
        cls.emp = Empreendimento.objects.create(
            tenant=cls.tenant, empreendimento="Jardins", razao_social="Jardins SPE",
            cnpj="11222333000181", telefone="1133334444", endereco="Rua A, 1",
            cidade="Palhoça", estado="SC",
        )
        cls.unidade = Unidade.objects.create(
            tenant=cls.tenant, empreendimento=cls.emp, quadra="1", lote="01",
            valor_base=Decimal("120000.00"),
        )
        cls.cliente = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="Ana Prado", cpf_cnpj="52998224725",
            email="ana@exemplo.com", telefone="48999990001",
            data_nascimento=date(1988, 5, 20), cidade="Palhoça", estado="SC",
        )
        cls.aquisicao = ClienteEmpreendimento.objects.create(
            tenant=cls.tenant, cliente=cls.cliente, empreendimento=cls.emp,
            unidade=cls.unidade, data_compra=date(2024, 1, 10),
            valor_tabela=Decimal("120000.00"), valor_compra=Decimal("120000.00"),
            condicoes_pagamento="financiamento_direto",
            indice_correcao=cls.indice, periodicidade_correcao="anual",
        )

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = [
            "cadastro.venda.view", "cadastro.venda.edit", "cadastro.venda.gerar_carne",
        ]
        self.client.force_authenticate(user=self.user)
        self.aberta = ContaReceber.objects.create(
            tenant=self.tenant, cliente=self.cliente, empreendimento=self.emp,
            cliente_empreendimento=self.aquisicao, descricao="Parcela 1/2",
            valor=Decimal("1000.00"), data_vencimento=date(2025, 6, 10),
        )
        self.quitada = ContaReceber.objects.create(
            tenant=self.tenant, cliente=self.cliente, empreendimento=self.emp,
            cliente_empreendimento=self.aquisicao, descricao="Parcela 2/2",
            valor=Decimal("1000.00"), data_vencimento=date(2025, 7, 10),
            status=StatusConta.QUITADO,
        )

    def _url(self):
        return f"/api/clientes-empreendimentos/{self.aquisicao.pk}/corrigir/"

    def test_previa_nao_grava(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["aplicado"])
        self.aberta.refresh_from_db()
        self.assertEqual(self.aberta.valor, Decimal("1000.00"))

    def test_aplicar_corrige_e_guarda_a_memoria_do_calculo(self):
        r = self.client.post(self._url())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["aplicado"])
        self.aberta.refresh_from_db()
        self.assertEqual(self.aberta.valor, Decimal("1126.83"))
        self.assertEqual(self.aberta.valor_nominal, Decimal("1000.00"))
        self.assertEqual(self.aberta.correcao_ate_competencia, date(2024, 12, 1))
        self.assertIsNotNone(self.aberta.corrigido_em)

    def test_titulo_quitado_nao_e_reajustado(self):
        """Corrigir o que já foi pago é cobrar duas vezes pelo mesmo mês."""
        self.client.post(self._url())
        self.quitada.refresh_from_db()
        self.assertEqual(self.quitada.valor, Decimal("1000.00"))

    def test_corrigir_duas_vezes_nao_compoe_o_indice_duas_vezes(self):
        self.client.post(self._url())
        primeiro = ContaReceber.objects.get(pk=self.aberta.pk).valor
        self.client.post(self._url())
        self.assertEqual(ContaReceber.objects.get(pk=self.aberta.pk).valor, primeiro)

    def test_contrato_sem_indice_recusa_com_o_motivo(self):
        self.aquisicao.indice_correcao = None
        self.aquisicao.save(update_fields=["indice_correcao"])
        r = self.client.post(self._url())
        self.assertEqual(r.status_code, 400)
        self.assertIn("índice", r.data["detail"])

    def test_corrigir_exige_a_permissao_do_carne(self):
        self.user.iam_permissions = ["cadastro.venda.view", "cadastro.venda.edit"]
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.post(self._url()).status_code, 403)
