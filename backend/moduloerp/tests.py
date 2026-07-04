"""
Testes da emissão de NF a partir de ContaReceber (achado L3): a NF herda o
tenant do título e o snapshot do cliente traz os campos reais (`cpf_cnpj`,
endereço completo com cidade/UF/CEP/IBGE) exigidos pelo funcoesnf.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import requests
from rest_framework.test import APITestCase

from clientes.models import Cliente
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass
from .models import ContaReceber, NotaFiscalServico, StatusNFE


class EmitirNFSETests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.user = Usuario.objects.create(username="fin_a", tenant=cls.tenant)
        cls.cliente = Cliente.objects.create(
            nome_completo="Cliente A",
            cpf_cnpj="11111111111",
            email="a@a.com",
            data_nascimento=date(1990, 1, 1),
            endereco="Rua das Obras",
            numero_endereco="10",
            bairro="Centro",
            cidade="Curitiba",
            estado="PR",
            cep="80000-000",
            cidade_ibge="4106902",
            tenant=cls.tenant,
        )
        cls.conta = ContaReceber.objects.create(
            cliente=cls.cliente,
            descricao="Serviço de engenharia",
            valor=1000,
            data_vencimento=date(2026, 8, 1),
            tenant=cls.tenant,
        )

    @patch("moduloerp.views.requests.post",
           side_effect=requests.exceptions.ConnectionError("microserviço de NF fora do ar"))
    def test_nfse_herda_tenant_e_snapshot_completo_do_cliente(self, _post):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_roles = ["financeiro"]
        self.client.force_authenticate(user=self.user)

        resp = self.client.post(
            f"/api/erp/contas-a-receber/{self.conta.conta_receber_id}/emitir-nfse/",
            {}, format="json",
        )

        self.assertEqual(resp.status_code, 201)
        nf = NotaFiscalServico.objects.get()
        self.assertEqual(nf.tenant_id, self.tenant.id)
        self.assertEqual(nf.borrower_data["cpf_cnpj"], self.cliente.cpf_cnpj)
        self.assertEqual(nf.borrower_data["nome_completo"], self.cliente.nome_completo)
        for campo in ("cidade", "estado", "cep", "cidade_ibge"):
            self.assertEqual(nf.borrower_data[campo], getattr(self.cliente, campo))


class S1TenantIsolationAPIViewTests(APITestCase):
    """
    Achado S1: `ERPDashboardView`, `AtualizarStatusNFView` e
    `ConsultarStatusNFView` eram `APIView` puras (fora do
    `TenantScopedViewSetMixin`) e liam/gravavam dados de qualquer tenant. Após a
    correção (`TenantScopedAPIViewMixin` + `scope_qs`), cada uma só enxerga o
    tenant do usuário.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(slug="s1-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="s1-b", nome="Empresa B")
        cls.user_a = Usuario.objects.create(username="s1_fin_a", tenant=cls.tenant_a)

        cls.cli_a = Cliente.objects.create(
            nome_completo="Cliente A", cpf_cnpj="11111111111", email="a@a.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant_a,
        )
        cls.cli_b = Cliente.objects.create(
            nome_completo="Cliente B", cpf_cnpj="22222222222", email="b@b.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant_b,
        )
        # Um título em aberto em cada tenant (saldo = valor; status ABERTO por padrão).
        ContaReceber.objects.create(
            cliente=cls.cli_a, descricao="Receber A", valor=Decimal("1000"),
            data_vencimento=date(2026, 8, 1), tenant=cls.tenant_a,
        )
        ContaReceber.objects.create(
            cliente=cls.cli_b, descricao="Receber B", valor=Decimal("500"),
            data_vencimento=date(2026, 8, 1), tenant=cls.tenant_b,
        )
        # NF de serviço do tenant B — alvo do acesso cruzado.
        cls.nf_b = NotaFiscalServico.objects.create(
            tenant=cls.tenant_b, city_service_code="101", description="Serviço B",
            services_amount=Decimal("500"), borrower_data={"cpf_cnpj": "22222222222"},
        )

    def _auth_user_a(self):
        self.user_a.iam_modules = ["erp_financeiro"]
        self.user_a.iam_roles = ["financeiro"]
        self.client.force_authenticate(user=self.user_a)

    def test_dashboard_soma_apenas_o_proprio_tenant(self):
        # Antes da correção somava 1500 (A + B); agora só os 1000 do tenant A.
        self._auth_user_a()
        resp = self.client.get("/api/erp/dashboard/")
        self.assertEqual(resp.status_code, 200)
        total = sum(float(f["total"]) for f in resp.json()["agingContasAReceber"])
        self.assertEqual(total, 1000.0)

    def test_atualizar_status_nf_cross_tenant_da_404_e_nao_grava(self):
        self._auth_user_a()
        resp = self.client.post(
            "/api/erp/atualizar-status-nf/",
            {"nf_id": self.nf_b.id, "nf_tipo": "servico", "status": StatusNFE.EMITIDA},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        # A NF é do tenant B; sob a RLS fail-closed, o contexto do request (tenant
        # A) a esconde. Lemos sob bypass de plataforma só para provar que o write
        # foi bloqueado (status intacto).
        with rls_bypass():
            self.nf_b.refresh_from_db()
        self.assertEqual(self.nf_b.status, StatusNFE.AGUARDANDO)  # write bloqueado

    def test_consultar_status_nf_cross_tenant_da_404(self):
        self._auth_user_a()
        resp = self.client.post(f"/api/erp/nf/{self.nf_b.id}/consultar/")
        self.assertEqual(resp.status_code, 404)
