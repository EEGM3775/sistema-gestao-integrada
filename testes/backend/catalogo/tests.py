"""Testes do catálogo-mestre (`catalogo`) — app de fundação, sem entitlement.

Espelham o contrato de módulo (isolamento por tenant, permissão camada 2,
unicidade por-tenant, tenant read-only), herdados dos antigos testes de
`moduloscm.Produto` — o item mestre agora é `catalogo.Item`. Sem `RequireModule`
(fundação): só a permissão `cadastro.item.*` gateia.
"""
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario

from catalogo.models import Item

ITEM_PERMS = ["cadastro.item.view", "cadastro.item.edit"]


class CatalogoTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="cat-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="cat-b", nome="Empresa B")
        cls.user = Usuario.objects.create(username="almox_a", tenant=cls.tenant)

    def autenticar(self, user=None, perms=ITEM_PERMS):
        user = user or self.user
        user.iam_modules = []  # catálogo é fundação — sem entitlement
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)
        return user


class PermissaoTests(CatalogoTestBase):
    def test_sem_permissao_recebe_403(self):
        self.autenticar(perms=[])
        resp = self.client.get("/api/catalogo/itens/")
        self.assertEqual(resp.status_code, 403)

    def test_com_permissao_recebe_200(self):
        self.autenticar()
        resp = self.client.get("/api/catalogo/itens/")
        self.assertEqual(resp.status_code, 200)


class ItemCrudTests(CatalogoTestBase):
    def test_post_injeta_tenant_do_usuario(self):
        self.autenticar()
        resp = self.client.post("/api/catalogo/itens/", {
            "codigo_interno": "CIM-50", "descricao": "Cimento CPII 50kg", "unidade": "sc",
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        item = Item.objects.get(codigo_interno="CIM-50")
        self.assertEqual(item.tenant_id, self.tenant.id)

    def test_tenant_no_payload_e_ignorado(self):
        self.autenticar()
        resp = self.client.post("/api/catalogo/itens/", {
            "codigo_interno": "VER-10", "descricao": "Vergalhão CA-50 10mm", "unidade": "m",
            "tenant": self.tenant_b.id,  # deve ser ignorado (read-only)
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Item.objects.get(codigo_interno="VER-10").tenant_id, self.tenant.id)

    def test_tipo_servico_nao_estocavel(self):
        self.autenticar()
        resp = self.client.post("/api/catalogo/itens/", {
            "codigo_interno": "SRV-01", "descricao": "Pintura de fachada", "unidade": "m2",
            "tipo": Item.Tipo.SERVICO, "estocavel": False,
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        item = Item.objects.get(codigo_interno="SRV-01")
        self.assertEqual(item.tipo, Item.Tipo.SERVICO)
        self.assertFalse(item.estocavel)


class IsolamentoTenantTests(CatalogoTestBase):
    def test_lista_nao_vaza_item_de_outro_tenant(self):
        Item.objects.create(tenant=self.tenant, codigo_interno="A-1", descricao="Item A", unidade="un")
        Item.objects.create(tenant=self.tenant_b, codigo_interno="B-1", descricao="Item B", unidade="un")
        self.autenticar()
        resp = self.client.get("/api/catalogo/itens/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        codigos = {p["codigo_interno"] for p in data}
        self.assertIn("A-1", codigos)
        self.assertNotIn("B-1", codigos)

    def test_nao_acessa_detalhe_de_outro_tenant(self):
        alheio = Item.objects.create(tenant=self.tenant_b, codigo_interno="B-2", descricao="Item B", unidade="un")
        self.autenticar()
        resp = self.client.get(f"/api/catalogo/itens/{alheio.item_id}/")
        self.assertEqual(resp.status_code, 404)


class UnicidadePorTenantTests(CatalogoTestBase):
    def test_codigo_interno_duplicado_no_mesmo_tenant_da_400(self):
        Item.objects.create(tenant=self.tenant, codigo_interno="DUP", descricao="X", unidade="un")
        self.autenticar()
        resp = self.client.post("/api/catalogo/itens/", {
            "codigo_interno": "DUP", "descricao": "Y", "unidade": "un",
        })
        self.assertEqual(resp.status_code, 400)

    def test_mesmo_codigo_em_tenants_distintos_e_permitido(self):
        Item.objects.create(tenant=self.tenant_b, codigo_interno="COMPART", descricao="X", unidade="un")
        self.autenticar()
        resp = self.client.post("/api/catalogo/itens/", {
            "codigo_interno": "COMPART", "descricao": "Y", "unidade": "un",
        })
        self.assertEqual(resp.status_code, 201, resp.content)
