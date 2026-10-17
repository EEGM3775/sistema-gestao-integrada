"""Calendário, Fatia D — agendas compartilhadas e convidados.

O que se prende aqui é a régua de acesso (`modulocalendar/acesso.py`): quem vê
uma agenda, quem lança nela, o convidado que só responde — e os avisos que cada
gesto deixa no sino de quem não estava olhando a tela.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from modulocalendar.models import Calendar, CalendarEvent, EventAttendee, EventReminder
from modulocalendar.tasks import despachar_lembretes
from nucleo.models import Notificacao, Tenant, Usuario

DUMMY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
LEITURA = ["calendario.evento.view"]
ESCRITA = ["calendario.evento.view", "calendario.evento.edit"]


@override_settings(CACHES=DUMMY_CACHE)
@patch("modulocalendar.views.get_holidays", return_value=[])
class AgendasTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="cal-d", nome="Empresa D")
        cls.outro_tenant = Tenant.objects.create(slug="cal-d2", nome="Outra")
        cls.ana = Usuario.objects.create(username="ana", first_name="Ana", tenant=cls.tenant)
        cls.bia = Usuario.objects.create(username="bia", first_name="Bia", tenant=cls.tenant)
        cls.caio = Usuario.objects.create(username="caio", first_name="Caio", tenant=cls.tenant)
        cls.estranho = Usuario.objects.create(username="zeca", tenant=cls.outro_tenant)

    def _como(self, user, perms=ESCRITA):
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)

    def _janela(self):
        agora = timezone.now()
        return {"start": (agora - timedelta(days=1)).isoformat(),
                "end": (agora + timedelta(days=2)).isoformat()}

    def _feed_ids(self, user):
        self._como(user, LEITURA)
        resp = self.client.get("/api/calendar/events/", self._janela())
        self.assertEqual(resp.status_code, 200)
        return {e["id"]: e for e in resp.json() if e["extendedProps"]["type"] == "local"}

    def _evento(self, dono, **extra):
        inicio = timezone.now() + timedelta(hours=2)
        return CalendarEvent.objects.create(
            tenant=self.tenant, user=dono, title=extra.pop("title", "Reunião"),
            start_time=inicio, end_time=inicio + timedelta(hours=1), **extra,
        )

    # ------------------------------------------------------------ agendas
    def test_agenda_de_equipe_aparece_para_os_membros_e_so_para_eles(self, _h):
        self._como(self.ana)
        resp = self.client.post("/api/calendar/calendars/", {
            "name": "Obra Centro", "color": "#0E7490", "scope": "equipe", "members": [self.bia.pk],
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        agenda = Calendar.objects.get(pk=resp.json()["id"])
        self.assertEqual(agenda.owner, self.ana)
        self.assertEqual(agenda.color, "#0e7490")
        ev = self._evento(self.ana, calendar=agenda)

        self.assertIn(ev.pk, self._feed_ids(self.bia))
        self.assertNotIn(ev.pk, self._feed_ids(self.caio))
        # A Bia entrou na agenda e soube disso pelo sino.
        self.assertTrue(Notificacao.objects.filter(user=self.bia, titulo__contains="Obra Centro").exists())

    def test_membro_lanca_na_agenda_de_equipe_e_estranho_nao(self, _h):
        agenda = Calendar.objects.create(tenant=self.tenant, owner=self.ana, name="Equipe", scope="equipe")
        agenda.members.create(user=self.bia, tenant=self.tenant)
        corpo = {
            "title": "Concretagem", "calendar": agenda.pk,
            "start_time": timezone.now().isoformat(),
            "end_time": (timezone.now() + timedelta(hours=1)).isoformat(),
        }
        self._como(self.bia)
        self.assertEqual(self.client.post("/api/calendar/events/", corpo, format="json").status_code, 201)
        self._como(self.caio)
        resp = self.client.post("/api/calendar/events/", corpo, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("calendar", resp.json())

    def test_agenda_da_empresa_todos_veem(self, _h):
        agenda = Calendar.objects.create(tenant=self.tenant, owner=self.ana, name="Empresa", scope="empresa")
        ev = self._evento(self.ana, calendar=agenda)
        feed = self._feed_ids(self.caio)
        self.assertIn(ev.pk, feed)
        self.assertTrue(feed[ev.pk]["extendedProps"]["canEdit"])

    def test_so_o_dono_muda_a_agenda(self, _h):
        agenda = Calendar.objects.create(tenant=self.tenant, owner=self.ana, name="Equipe", scope="equipe")
        agenda.members.create(user=self.bia, tenant=self.tenant)
        self._como(self.bia)
        resp = self.client.patch(f"/api/calendar/calendars/{agenda.pk}/", {"name": "Minha"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.delete(f"/api/calendar/calendars/{agenda.pk}/").status_code, 403)

    def test_membro_de_outra_empresa_e_recusado(self, _h):
        self._como(self.ana)
        resp = self.client.post("/api/calendar/calendars/", {
            "name": "X", "scope": "equipe", "members": [self.estranho.pk],
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_agenda_pessoal_de_outro_nao_aparece(self, _h):
        agenda = Calendar.objects.create(tenant=self.tenant, owner=self.ana, name="Minha", scope="pessoal")
        ev = self._evento(self.ana, calendar=agenda)
        self.assertNotIn(ev.pk, self._feed_ids(self.bia))
        self._como(self.bia, LEITURA)
        nomes = [c["name"] for c in self.client.get("/api/calendar/calendars/").json()]
        self.assertNotIn("Minha", nomes)

    # ---------------------------------------------------------- convidados
    def test_convidar_mostra_o_evento_e_avisa_no_sino(self, _h):
        self._como(self.ana)
        resp = self.client.post("/api/calendar/events/", {
            "title": "Vistoria", "start_time": timezone.now().isoformat(),
            "end_time": (timezone.now() + timedelta(hours=1)).isoformat(),
            "attendees": [self.bia.pk],
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        ev_id = resp.json()["id"]
        self.assertEqual(resp.json()["attendees"], [{"user": self.bia.pk, "nome": "Bia", "status": "pendente"}])

        feed = self._feed_ids(self.bia)
        self.assertIn(ev_id, feed)
        props = feed[ev_id]["extendedProps"]
        self.assertFalse(props["canEdit"])
        self.assertEqual(props["myStatus"], "pendente")
        self.assertEqual(props["ownerName"], "Ana")
        aviso = Notificacao.objects.get(user=self.bia, titulo="Convite: Vistoria")
        self.assertEqual(aviso.nivel, Notificacao.Nivel.DECIDIR)
        self.assertIn(f"evento={ev_id}", aviso.url)

    def test_convidado_responde_so_com_leitura_e_nao_edita(self, _h):
        ev = self._evento(self.ana)
        EventAttendee.objects.create(event=ev, user=self.bia, tenant=self.tenant)
        self._como(self.bia, LEITURA)
        resp = self.client.post(f"/api/calendar/events/{ev.pk}/responder/", {"status": "aceito"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["my_status"], "aceito")
        self.assertTrue(Notificacao.objects.filter(user=self.ana, titulo="Bia aceitou: Reunião").exists())

        self._como(self.bia)  # mesmo com .edit, convite não é agenda
        resp = self.client.patch(f"/api/calendar/events/{ev.pk}/", {"title": "Outra"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.delete(f"/api/calendar/events/{ev.pk}/").status_code, 403)

    def test_quem_nao_foi_convidado_nao_ve_nem_responde(self, _h):
        ev = self._evento(self.ana)
        self._como(self.caio, LEITURA)
        resp = self.client.post(f"/api/calendar/events/{ev.pk}/responder/", {"status": "aceito"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_tirar_convidado_avisa_e_mantem_resposta_de_quem_fica(self, _h):
        ev = self._evento(self.ana)
        EventAttendee.objects.create(event=ev, user=self.bia, tenant=self.tenant, status="aceito")
        EventAttendee.objects.create(event=ev, user=self.caio, tenant=self.tenant)
        self._como(self.ana)
        resp = self.client.patch(f"/api/calendar/events/{ev.pk}/", {"attendees": [self.bia.pk]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(ev.attendees.values_list("user_id", "status")), [(self.bia.pk, "aceito")])
        self.assertTrue(Notificacao.objects.filter(user=self.caio, titulo__startswith="Convite retirado").exists())

    def test_cancelar_avisa_quem_nao_recusou(self, _h):
        ev = self._evento(self.ana)
        EventAttendee.objects.create(event=ev, user=self.bia, tenant=self.tenant, status="aceito")
        EventAttendee.objects.create(event=ev, user=self.caio, tenant=self.tenant, status="recusado")
        self._como(self.ana)
        self.assertEqual(self.client.delete(f"/api/calendar/events/{ev.pk}/").status_code, 204)
        self.assertTrue(Notificacao.objects.filter(user=self.bia, titulo__startswith="Evento cancelado").exists())
        self.assertFalse(Notificacao.objects.filter(user=self.caio, titulo__startswith="Evento cancelado").exists())

    def test_override_de_serie_leva_os_convidados_sem_novo_convite(self, _h):
        inicio = timezone.now().replace(microsecond=0) + timedelta(hours=2)
        mestre = CalendarEvent.objects.create(
            tenant=self.tenant, user=self.ana, title="Semanal", start_time=inicio,
            end_time=inicio + timedelta(hours=1), recurrence_rule="FREQ=DAILY;COUNT=3",
        )
        EventAttendee.objects.create(event=mestre, user=self.bia, tenant=self.tenant, status="aceito")
        self._como(self.ana)
        resp = self.client.post(f"/api/calendar/events/{mestre.pk}/update-recurrence/", {
            "scope": "this", "occurrence_start": inicio.isoformat(), "payload": {"title": "Só hoje"},
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        override = CalendarEvent.objects.get(pk=resp.json()["id"])
        self.assertEqual(list(override.attendees.values_list("user_id", "status")), [(self.bia.pk, "aceito")])
        self.assertFalse(Notificacao.objects.filter(user=self.bia, titulo__startswith="Convite").exists())

    def test_lembrete_chega_a_quem_aceitou(self, _h):
        inicio = timezone.now() + timedelta(minutes=5)
        ev = CalendarEvent.objects.create(
            tenant=self.tenant, user=self.ana, title="Entrega",
            start_time=inicio, end_time=inicio + timedelta(hours=1),
        )
        EventReminder.objects.create(event=ev, tenant=self.tenant, offset_minutes=10)
        EventAttendee.objects.create(event=ev, user=self.bia, tenant=self.tenant, status="aceito")
        EventAttendee.objects.create(event=ev, user=self.caio, tenant=self.tenant, status="pendente")
        despachar_lembretes()
        lembrados = set(Notificacao.objects.filter(titulo="Lembrete: Entrega").values_list("user_id", flat=True))
        self.assertEqual(lembrados, {self.ana.pk, self.bia.pk})

    # -------------------------------------------------------------- pessoas
    def test_pessoas_da_empresa_paginadas_com_busca(self, _h):
        self._como(self.ana, LEITURA)
        resp = self.client.get("/api/calendar/pessoas/", {"search": "bi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([p["nome"] for p in resp.json()["results"]], ["Bia"])
        todos = self.client.get("/api/calendar/pessoas/", {"page_size": 2}).json()
        self.assertEqual(todos["count"], 3)  # o de outra empresa não entra
        self.assertEqual(len(todos["results"]), 2)
        self.assertIsNotNone(todos["next"])
