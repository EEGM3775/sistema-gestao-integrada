"""D.1.4 — financeiro por obra: a atribuição, a DRE e o realizado do Orçamento.

O que estes testes protegem: que uma conta só chegue à obra pelos dois caminhos
declarados (a obra da conta e o rateio a centro de custo com obra), na fração
certa, e que nada seja atribuído por aproximação — conta sem obra fica de fora.
"""
from datetime import date
from decimal import Decimal


from clientes.models import Cliente
from fornecedores.models import Fornecedor
from moduloerp import financeiro_obra
from moduloerp.models import CentroCusto, ContaPagar, ContaReceber, RateioContaPagar, Transacao
from moduloorcamento import controle, planilha
from obras.models import Obra

from ..moduloorcamento.test_planilha import PlanilhaTestBase

PERMS = ["erp.relatorio.view", "erp.conta_pagar.view", "erp.conta_pagar.edit"]


class FinanceiroPorObraTests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Empreiteira B LTDA", cnpj="11222333000181", email="b@b.com.br",
        )
        self.cliente = Cliente.objects.create(
            tenant=self.tenant, nome_completo="Contratante SA", cpf_cnpj="52998224725",
            email="c@c.com", data_nascimento=date(1980, 1, 1),
        )
        self.outra = Obra.objects.create(tenant=self.tenant, nome_obra="Galpão Norte", endereco="Rua B, 1")

    def _pagar(self, valor, pago="0", **extra):
        conta = ContaPagar.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, descricao="Serviço",
            valor=Decimal(valor), data_vencimento=date(2026, 9, 10), **extra,
        )
        if Decimal(pago):
            conta.dar_baixa(valor=Decimal(pago), data=date(2026, 9, 12), meio_pagamento="PIX")
            conta.refresh_from_db()
        return conta

    def test_conta_com_obra_e_etapa_vai_inteira_para_a_obra(self):
        self._pagar("10000", pago="4000", obra=self.obra, etapa=self.fundacao)
        dados = financeiro_obra.por_obra(self.tenant.id)[self.obra.pk]
        self.assertEqual(dados["despesa"]["valor"], Decimal("10000"))
        self.assertEqual(dados["despesa"]["pago"], Decimal("4000"))
        self.assertEqual(dados["despesa_por_etapa"][self.fundacao.pk]["valor"], Decimal("10000"))

    def test_rateio_por_centro_de_custo_divide_entre_obras(self):
        conta = self._pagar("1000", pago="1000")
        aurora = CentroCusto.objects.create(tenant=self.tenant, nome="CC Aurora", obra=self.obra)
        galpao = CentroCusto.objects.create(tenant=self.tenant, nome="CC Galpão", obra=self.outra)
        RateioContaPagar.objects.create(tenant=self.tenant, conta_pagar=conta, centro_custo=aurora, valor=Decimal("700"))
        RateioContaPagar.objects.create(tenant=self.tenant, conta_pagar=conta, centro_custo=galpao, valor=Decimal("300"))
        dados = financeiro_obra.por_obra(self.tenant.id)
        self.assertEqual(dados[self.obra.pk]["despesa"]["pago"], Decimal("700"))
        self.assertEqual(dados[self.outra.pk]["despesa"]["pago"], Decimal("300"))

    def test_conta_sem_obra_nao_e_atribuida(self):
        self._pagar("5000", pago="5000")
        self.assertEqual(financeiro_obra.por_obra(self.tenant.id), {})

    def test_baixa_leva_a_obra_para_a_transacao(self):
        conta = self._pagar("800", pago="800", obra=self.obra)
        self.assertEqual(Transacao.objects.get(conta_pagar=conta).obra_id, self.obra.pk)

    def test_realizado_do_orcamento_le_o_erp(self):
        """A medição de empreiteiro lançada direto no ERP — invisível antes do D.1.4."""
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="100000", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)
        self._pagar("30000", pago="12000", obra=self.obra)
        linha = controle.quatro_colunas(self.tenant.id, self.obra.pk)[0]
        self.assertEqual(Decimal(linha["realizado"]), Decimal("12000.00"))
        self.assertEqual(linha["realizado_cobertura"], "erp")

    def test_dre_da_obra(self):
        orc = self._orcamento()
        self._linha(orc, "Fundação", quantidade="1", custo="50000", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)
        self._pagar("20000", pago="20000", obra=self.obra, etapa=self.fundacao)
        receber = ContaReceber.objects.create(
            tenant=self.tenant, cliente=self.cliente, descricao="Medição 1", valor=Decimal("35000"),
            data_vencimento=date(2026, 9, 20), obra=self.obra,
        )
        receber.dar_baixa(valor=Decimal("35000"), data=date(2026, 9, 21), meio_pagamento="TED")

        dre = financeiro_obra.dre(self.tenant.id, self.obra, com_orcado=True)
        self.assertEqual(dre["receita"]["recebido"], "35000.00")
        self.assertEqual(dre["custo"]["pago"], "20000.00")
        self.assertEqual(dre["resultado"]["caixa"], "15000.00")
        fundacao = next(l for l in dre["por_etapa"] if l["etapa"] == self.fundacao.pk)
        self.assertEqual((fundacao["orcado"], fundacao["apropriado"], fundacao["consumido_pct"]),
                         ("50000.00", "20000.00", "40.00"))
        self.assertEqual(dre["mensal"], [{"mes": "2026-09-01", "entradas": "35000.00",
                                          "saidas": "20000.00", "saldo_acumulado": "15000.00"}])

    def test_dre_sem_o_modulo_de_orcamento_nao_mostra_orcado(self):
        self._pagar("100", obra=self.obra)
        self.autenticar(modules=("erp_financeiro",), perms=PERMS)
        resp = self.client.get(f"/api/erp/obras/{self.obra.pk}/dre/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.data["orcado"])
        self.assertFalse(resp.data["orcado_disponivel"])
        lista = self.client.get("/api/erp/obras/financeiro/")
        self.assertEqual([l["obra"] for l in lista.data["obras"]], [self.obra.pk])

    def test_etapa_de_outra_obra_e_recusada(self):
        self.autenticar(modules=("erp_financeiro",), perms=PERMS)
        resp = self.client.post("/api/erp/contas-a-pagar/", {
            "fornecedor": self.fornecedor.pk, "descricao": "X", "valor": "10.00",
            "data_vencimento": "2026-09-30", "obra": self.outra.pk, "etapa": self.fundacao.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("etapa", resp.data)

    def test_dre_de_obra_de_outra_empresa_e_404(self):
        alheia = Obra.objects.create(tenant=self.tenant_b, nome_obra="Alheia", endereco="X")
        self.autenticar(modules=("erp_financeiro",), perms=PERMS)
        self.assertEqual(self.client.get(f"/api/erp/obras/{alheia.pk}/dre/").status_code, 404)
