"""Fase 9.D — LGPD além da máscara: portabilidade, esquecimento e incidente ANPD.

- Export reúne a PII do titular (integral).
- Esquecimento anonimiza a PII e apaga os filhos de PII.
- Incidente nasce **pendente**; só o **dono da plataforma** confirma (inicia o
  prazo de 72h) ou descarta — a trava de falso-positivo.
"""
from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from nucleo import lgpd
from nucleo.models import Tenant, Usuario, IncidenteLGPD
from clientes.models import Cliente


class LgpdServiceTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="lgpd-a", nome="Empresa LGPD")
        cls.cli = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="João PII", cpf_cnpj="11144477735",
            email="joao@ex.com", telefone="41999990000", data_nascimento=date(1990, 1, 1),
        )

    def test_export_traz_a_pii_do_titular(self):
        dados = lgpd.exportar_titular("cliente", self.cli)
        self.assertEqual(dados["titular"]["cpf_cnpj"], "11144477735")
        self.assertEqual(dados["titular"]["email"], "joao@ex.com")
        self.assertIn("DadoBancarioCliente", dados["relacionados"])

    def test_esquecimento_anonimiza_a_pii(self):
        lgpd.anonimizar_titular("cliente", self.cli)
        self.cli.refresh_from_db()
        self.assertNotEqual(self.cli.cpf_cnpj, "11144477735")
        self.assertTrue(self.cli.nome_completo.startswith("[ANON-"))
        # e-mail é blank=True → vira "" ou marcador; nunca o original
        self.assertNotEqual(self.cli.email, "joao@ex.com")


class LgpdEndpointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="lgpd-b", nome="Empresa B")
        cls.cli = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="Ana PII", cpf_cnpj="52998224725",
            email="ana@ex.com", data_nascimento=date(1985, 5, 5),
        )
        cls.encarregado = Usuario.objects.create(username="dpo", tenant=cls.tenant)
        cls.comum = Usuario.objects.create(username="joe", tenant=cls.tenant)

    def _auth(self, user, perms=None):
        user.iam_permissions = perms or []
        self.client.force_authenticate(user)

    def test_esquecer_exige_permissao(self):
        self._auth(self.comum, [])  # sem plataforma.lgpd.excluir
        r = self.client.post(f"/api/lgpd/cliente/{self.cli.cliente_id}/esquecer/")
        self.assertEqual(r.status_code, 403)

    def test_esquecer_anonimiza_com_permissao(self):
        self._auth(self.encarregado, ["plataforma.lgpd.excluir"])
        r = self.client.post(f"/api/lgpd/cliente/{self.cli.cliente_id}/esquecer/")
        self.assertEqual(r.status_code, 200, r.data)
        self.cli.refresh_from_db()
        self.assertNotEqual(self.cli.cpf_cnpj, "52998224725")

    def test_exportar_com_permissao(self):
        self._auth(self.encarregado, ["plataforma.lgpd.exportar"])
        r = self.client.get(f"/api/lgpd/cliente/{self.cli.cliente_id}/exportar/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["titular"]["cpf_cnpj"], "52998224725")


class IncidenteLGPDTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="inc-a", nome="Inc")
        cls.reporter = Usuario.objects.create(username="rep", tenant=cls.tenant, is_tenant_admin=True)
        cls.owner = Usuario.objects.create(username="owner", tenant=cls.tenant)

    def _auth(self, user, **attrs):
        for k, v in attrs.items():
            setattr(user, k, v)
        self.client.force_authenticate(user)

    def _reportar(self):
        self._auth(self.reporter, is_platform_admin=False)  # admin de tenant passa
        r = self.client.post("/api/lgpd/incidentes/", {"descricao": "Vazamento de e-mails"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], "pendente")
        return r.data["id"]

    def test_confirmacao_exige_o_dono_da_plataforma(self):
        iid = self._reportar()
        # quem não é dono não confirma
        self._auth(self.reporter, is_platform_admin=False)
        self.assertEqual(self.client.post(f"/api/lgpd/incidentes/{iid}/confirmar/").status_code, 403)

    def test_dono_confirma_inicia_prazo_72h_e_notifica(self):
        iid = self._reportar()
        self._auth(self.owner, is_platform_admin=True)
        r = self.client.post(f"/api/lgpd/incidentes/{iid}/confirmar/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "confirmado")
        self.assertIsNotNone(r.data["prazo_anpd"])
        # notificar só depois de confirmado
        r = self.client.post(f"/api/lgpd/incidentes/{iid}/notificar/")
        self.assertEqual(r.data["status"], "notificado")

    def test_dono_descarta_falso_positivo(self):
        iid = self._reportar()
        self._auth(self.owner, is_platform_admin=True)
        r = self.client.post(f"/api/lgpd/incidentes/{iid}/descartar/")
        self.assertEqual(r.data["status"], "descartado")
        # incidente descartado não pode ser notificado
        self.assertEqual(self.client.post(f"/api/lgpd/incidentes/{iid}/notificar/").status_code, 400)
