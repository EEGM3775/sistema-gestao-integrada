"""API do centro de notificações in-app (Calendário, Fatia C).

Cobre: só o próprio usuário vê as suas; `unread-count` para o badge; marcar uma
e marcar todas como lidas.
"""
from rest_framework.test import APITestCase

from nucleo.models import Notificacao, Tenant, Usuario


class NotificacaoAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="notif-a", nome="Notif A")
        cls.user = Usuario.objects.create(username="notif_user", tenant=cls.tenant)
        cls.outro = Usuario.objects.create(username="outro_user", tenant=cls.tenant)
        # 2 do usuário (1 lida, 1 não-lida) + 1 de outro usuário (não deve vazar).
        cls.n1 = Notificacao.objects.create(
            user=cls.user, tenant=cls.tenant, titulo="Lembrete: Reunião",
            mensagem="começa em 10 min", tipo=Notificacao.Tipo.LEMBRETE, url="/app/calendario",
        )
        cls.n2 = Notificacao.objects.create(
            user=cls.user, tenant=cls.tenant, titulo="Já lida",
        )
        cls.n2.marcar_lida()
        Notificacao.objects.create(user=cls.outro, tenant=cls.tenant, titulo="De outro")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_lista_so_do_proprio_usuario(self):
        resp = self.client.get("/api/notificacoes/")
        self.assertEqual(resp.status_code, 200)
        titulos = {n["titulo"] for n in resp.json()}
        self.assertEqual(titulos, {"Lembrete: Reunião", "Já lida"})

    def test_filtro_unread(self):
        resp = self.client.get("/api/notificacoes/", {"unread": "1"})
        self.assertEqual(resp.status_code, 200)
        titulos = [n["titulo"] for n in resp.json()]
        self.assertEqual(titulos, ["Lembrete: Reunião"])

    def test_unread_count(self):
        resp = self.client.get("/api/notificacoes/unread-count/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_marcar_lida(self):
        resp = self.client.post(f"/api/notificacoes/{self.n1.id}/marcar-lida/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["lida"])
        self.n1.refresh_from_db()
        self.assertIsNotNone(self.n1.lida_em)

    def test_marcar_todas_lidas(self):
        resp = self.client.post("/api/notificacoes/marcar-todas-lidas/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["marcadas"], 1)
        self.assertEqual(
            Notificacao.objects.filter(user=self.user, lida_em__isnull=True).count(), 0)

    def test_nao_lista_de_outro_tenant_via_user(self):
        # Notificação de outro usuário não aparece na lista do user autenticado.
        resp = self.client.get("/api/notificacoes/")
        self.assertNotIn("De outro", {n["titulo"] for n in resp.json()})
