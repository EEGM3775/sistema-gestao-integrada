"""D17 — `GET /api/auditoria/` lido junto com a trilha da IAM.

A tela "Trilha de auditoria" intercala as duas pelo horário; para isso as duas
paginam com o mesmo número do `payment`, aceitam o mesmo período e o mesmo
recorte por pessoa. Antes a lista vinha inteira, sem página nenhuma.
"""
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from nucleo.models import AuditLog, Tenant, Usuario
from payment import planos


class LeituraDaTrilhaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="aud-d17", nome="Empresa")
        cls.outro = Tenant.objects.create(slug="aud-d17-b", nome="Outra")
        cls.auditora = Usuario.objects.create(username="aud", tenant=cls.tenant)
        cls.ana = Usuario.objects.create(username="ana", tenant=cls.tenant)

        def linha(tenant, quem, dias, acao=AuditLog.Acao.BAIXA):
            with patch("django.utils.timezone.now", return_value=timezone.now() - timedelta(days=dias)):
                return AuditLog.objects.create(
                    tenant=tenant, usuario=quem, usuario_nome=quem.username,
                    acao=acao, modelo="erp.ContaReceber", objeto_id="1",
                )

        linha(cls.tenant, cls.ana, 0)
        linha(cls.tenant, cls.ana, 3)
        linha(cls.tenant, cls.auditora, 10, AuditLog.Acao.VISUALIZAR_PII)
        linha(cls.outro, cls.ana, 0)

    def _get(self, **params):
        self.auditora.iam_permissions = ["plataforma.auditoria.view"]
        self.client.force_authenticate(user=self.auditora)
        return self.client.get("/api/auditoria/", params)

    def test_pagina_com_o_numero_do_payment(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 3)  # a da outra empresa não entra
        r = self._get(page_size=2)
        self.assertEqual(len(r.json()["results"]), 2)
        self.assertIsNotNone(r.json()["next"])
        r = self._get(page_size=planos.PAGINA_MAXIMA["auditoria"] * 10)
        self.assertEqual(r.status_code, 200)

    def test_mais_recente_primeiro(self):
        datas = [l["timestamp"] for l in self._get().json()["results"]]
        self.assertEqual(datas, sorted(datas, reverse=True))

    def test_periodo_com_data_vale_o_dia_inteiro(self):
        hoje = timezone.localdate()
        self.assertEqual(self._get(desde=(hoje - timedelta(days=5)).isoformat()).json()["count"], 2)
        self.assertEqual(self._get(ate=(hoje - timedelta(days=5)).isoformat()).json()["count"], 1)
        self.assertEqual(self._get(desde=hoje.isoformat(), ate=hoje.isoformat()).json()["count"], 1)

    def test_por_pessoa(self):
        self.assertEqual(self._get(pessoa="ANA").json()["count"], 2)

    def test_sem_a_permissao_e_403(self):
        self.ana.iam_permissions = []
        self.client.force_authenticate(user=self.ana)
        self.assertEqual(self.client.get("/api/auditoria/").status_code, 403)
