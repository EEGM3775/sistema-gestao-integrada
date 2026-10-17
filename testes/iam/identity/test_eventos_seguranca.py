"""D17 — a trilha de identidade lida por quem audita (`GET /eventos-seguranca/`).

A IAM guardava os eventos de segurança, mas só o shell os lia. O auditor agora
os lê pela API, com a mesma permissão da trilha do backend, só da própria
empresa, e filtra por pessoa e período como lá — a tela junta as duas.
"""
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from identity.models import ConsentimentoSuporte, EventoSeguranca, Perfil, Permissao, Tenant, Usuario


class EventosSegurancaTests(TestCase):
    def setUp(self):
        call_command("sync_authz")
        self.plataforma = Tenant.objects.create(nome="Plataforma", slug="plat-d17")
        self.x = Tenant.objects.create(nome="Construtora X", slug="x-d17")
        self.y = Tenant.objects.create(nome="Construtora Y", slug="y-d17")
        self.admin_x = Usuario.objects.create(username="adm-x", email="adm@x.com", tenant=self.x, is_tenant_admin=True)
        self.ana = Usuario.objects.create(username="ana-x", email="ana@x.com", tenant=self.x)
        self.auditora = Usuario.objects.create(username="aud-x", email="aud@x.com", tenant=self.x)
        papel = Perfil.objects.create(tenant=self.x, nome="auditoria")
        papel.permissoes.add(Permissao.objects.get(codename="plataforma.auditoria.view"))
        self.auditora.perfis.add(papel)
        self.dono = Usuario.objects.create(username="dono", email="dono@p.com", tenant=self.plataforma, is_superuser=True)

        def ev(tenant, tipo, alvo, autor="", dias=0):
            # A linha é imutável no banco (trigger): a data vem do relógio na criação.
            quando = timezone.now() - timedelta(days=dias)
            with patch("django.utils.timezone.now", return_value=quando):
                return EventoSeguranca.objects.create(
                    tenant=tenant, tipo=tipo, alvo_username=alvo, autor_username=autor,
                )

        ev(self.x, EventoSeguranca.Tipo.RESET_SOLICITADO, "ana-x")
        ev(self.x, EventoSeguranca.Tipo.PRIVILEGIO_ALTERADO, "ana-x", autor="adm-x", dias=3)
        ev(self.x, EventoSeguranca.Tipo.SENHA_ALTERADA, "adm-x", autor="adm-x", dias=10)
        ev(self.y, EventoSeguranca.Tipo.RESET_SOLICITADO, "beto-y")

    def _get(self, quem, **params):
        c = APIClient()
        c.force_authenticate(user=quem)
        return c.get("/eventos-seguranca/", params)

    def test_quem_tem_a_permissao_le_a_da_propria_empresa(self):
        r = self._get(self.auditora)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 3)
        self.assertEqual({e["alvo_username"] for e in r.data["results"]}, {"ana-x", "adm-x"})
        # Mais recente primeiro, com o rótulo legível do tipo.
        self.assertEqual(r.data["results"][0]["tipo"], "reset_solicitado")
        self.assertEqual(r.data["results"][0]["tipo_rotulo"], "Recuperação de senha solicitada")

    def test_o_admin_da_empresa_le(self):
        self.assertEqual(self._get(self.admin_x).status_code, 200)

    def test_sem_a_permissao_e_403(self):
        self.assertEqual(self._get(self.ana).status_code, 403)

    def test_filtra_por_pessoa_quem_agiu_ou_quem_sofreu(self):
        r = self._get(self.auditora, pessoa="ADM-X")
        self.assertEqual(r.data["count"], 2)  # alterou o privilégio da Ana e a própria senha

    def test_filtra_por_periodo(self):
        hoje = timezone.localdate()
        r = self._get(self.auditora, desde=(hoje - timedelta(days=5)).isoformat())
        self.assertEqual(r.data["count"], 2)
        r = self._get(self.auditora, ate=(hoje - timedelta(days=5)).isoformat())
        self.assertEqual(r.data["count"], 1)
        # Só data no `ate` vale o dia inteiro: o evento de hoje entra.
        r = self._get(self.auditora, desde=hoje.isoformat(), ate=hoje.isoformat())
        self.assertEqual(r.data["count"], 1)

    def test_pagina_com_o_numero_do_payment(self):
        r = self._get(self.auditora, page_size=2)
        self.assertEqual(len(r.data["results"]), 2)
        self.assertIsNotNone(r.data["next"])

    def test_o_supervisor_so_entra_com_consentimento(self):
        r = self._get(self.dono)
        self.assertEqual(r.data["count"], 0)
        ConsentimentoSuporte.objects.create(
            tenant=self.x, concedido_por=self.admin_x, ate=timezone.now() + timedelta(days=1),
        )
        r = self._get(self.dono)
        self.assertEqual(r.data["count"], 3)
