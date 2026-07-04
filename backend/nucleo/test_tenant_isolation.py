"""
Testes de isolamento multi-tenant (camada de aplicação — Fase 0.3c/e).

Provam que um usuário de um tenant não enxerga nem acessa dados de outro
tenant via API, e que ao criar um objeto o tenant do usuário é atribuído.
"""
from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from clientes.models import Cliente
from nucleo.models import Tenant, Usuario


class TenantIsolationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="emp-b", nome="Empresa B")

        cls.user_a = Usuario.objects.create(username="user_a", tenant=cls.tenant_a)
        cls.user_b = Usuario.objects.create(username="user_b", tenant=cls.tenant_b)

        cls.cli_a = Cliente.objects.create(
            nome_completo="Cliente A", cpf_cnpj="11111111111",
            email="a@a.com", data_nascimento=date(1990, 1, 1), tenant=cls.tenant_a,
        )
        cls.cli_b = Cliente.objects.create(
            nome_completo="Cliente B", cpf_cnpj="22222222222",
            email="b@b.com", data_nascimento=date(1990, 1, 1), tenant=cls.tenant_b,
        )

    def test_list_so_mostra_clientes_do_proprio_tenant(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get("/api/clientes/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        nomes = {c["nome_completo"] for c in resp.json()}
        self.assertEqual(nomes, {"Cliente A"})

    def test_detail_cross_tenant_retorna_404(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get(f"/api/clientes/{self.cli_b.cliente_id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_atribui_tenant_do_usuario(self):
        self.client.force_authenticate(user=self.user_b)
        payload = {
            "nome_completo": "Novo Cliente",
            "cpf_cnpj": "33333333333",
            "email": "novo@b.com",
            "data_nascimento": "1995-05-05",
        }
        resp = self.client.post("/api/clientes/", payload, format="json")
        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))
        novo = Cliente.objects.get(cpf_cnpj="33333333333")
        self.assertEqual(novo.tenant_id, self.tenant_b.id)

    def test_superuser_ve_todos_os_tenants(self):
        admin = Usuario.objects.create(username="root", is_superuser=True, is_staff=True)
        self.client.force_authenticate(user=admin)
        resp = self.client.get("/api/clientes/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.json()), 2)
