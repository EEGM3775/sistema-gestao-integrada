"""Fase 9.B — gate por permissão (RequirePermission) nos endpoints de PII do RH.

Antes: `RequireRole("rh_medico")` barrava o endpoint inteiro por nome de papel.
Agora: `required_resource = "rh.dado_medico"` → GET exige `rh.dado_medico.view`,
escrita exige `rh.dado_medico.edit`. Token legado (sem `permissions`) cai no papel.
"""
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario

URL = "/api/dados-medicos-funcionarios/"


class RequirePermissionRHTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="rh-a", nome="Empresa RH")
        cls.user = Usuario.objects.create(username="rh_user", tenant=cls.tenant)

    def _auth(self, *, modules=("rh",), permissions=None, roles=None):
        self.user.iam_modules = list(modules)
        if permissions is not None:
            self.user.iam_permissions = list(permissions)
        if roles is not None:
            self.user.iam_roles = list(roles)
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

    def test_fallback_legado_por_papel(self):
        # token sem claim `permissions` → cai no RequireRole (papel rh_medico).
        self._auth(roles=["rh_medico"])
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_legado_sem_papel_nega(self):
        self._auth(roles=["operacional"])
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_sem_o_modulo_nega_mesmo_com_permissao(self):
        # camada 1 (entitlement) independe da camada 2.
        self._auth(modules=[], permissions=["rh.dado_medico.view"])
        self.assertEqual(self.client.get(URL).status_code, 403)
