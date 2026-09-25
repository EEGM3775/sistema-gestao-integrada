"""Fase 9.B/E — gate por permissão (RequirePermission) nos endpoints de PII do RH.

`required_resource = "rh.dado_medico"` → GET exige `rh.dado_medico.view`, escrita
exige `rh.dado_medico.edit`. Desde a **fatia E** a checagem é estrita: sem a
permissão no token → 403, sem fallback por papel (o `RequireRole` foi removido).
"""
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario

URL = "/api/dados-medicos-funcionarios/"


class RequirePermissionRHTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="rh-a", nome="Empresa RH")
        cls.user = Usuario.objects.create(username="rh_user", tenant=cls.tenant)

    def _auth(self, *, modules=("rh",), permissions=()):
        self.user.iam_modules = list(modules)
        self.user.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.user)

    def test_permissao_de_leitura_concede_get(self):
        self._auth(permissions=["rh.dado_medico.view"])
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_sem_a_permissao_nega_get(self):
        # tem permissões (era das permissões), mas não a do prontuário → 403.
        self._auth(permissions=["rh.folha.view"])
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_leitura_nao_autoriza_escrita(self):
        # só `.view`; POST exige `.edit` → 403 antes da validação do payload.
        self._auth(permissions=["rh.dado_medico.view"])
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 403)

    def test_sem_permissao_nega_fail_closed(self):
        # Fatia E: conjunto de permissões vazio → 403, sem cair em papel algum.
        self._auth(permissions=[])
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_sem_o_modulo_nega_mesmo_com_permissao(self):
        # camada 1 (entitlement) independe da camada 2.
        self._auth(modules=[], permissions=["rh.dado_medico.view"])
        self.assertEqual(self.client.get(URL).status_code, 403)
