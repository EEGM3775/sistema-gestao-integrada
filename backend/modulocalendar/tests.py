"""
Testes do calendário: a listagem agregada não pode quebrar (achado L1 — era
500 por filtro em campo inexistente), eventos locais saem com `id`, feriados
cobrem todos os anos do período e as tarefas do CRM entram in-process
(Fase 11.2 — sem o microsserviço funcoeslead).
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from modulocrm.models import Interaction, Lead
from nucleo.models import Tenant, Usuario
from .models import CalendarEvent

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM_CACHE)
class CalendarEventListTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.user = Usuario.objects.create(username="user_a", tenant=cls.tenant)
        inicio = timezone.now()
        cls.evento = CalendarEvent.objects.create(
            title="Reunião de obra",
            start_time=inicio,
            end_time=inicio + timedelta(hours=1),
            user=cls.user,
            tenant=cls.tenant,
        )
        lead = Lead.objects.create(
            first_name="Ana", last_name="Souza", email="ana@exemplo.com",
            assigned_to=cls.user, tenant=cls.tenant,
        )
        cls.tarefa = Interaction.objects.create(
            lead=lead,
            type=Interaction.TypeChoices.TAREFA,
            subject="Ligar para Ana",
            due_date=inicio,
            tenant=cls.tenant,
        )

    def _listar(self, start, end):
        self.user.iam_permissions = ["calendario.evento.view"]  # GET → .view (fatia E)
        self.client.force_authenticate(user=self.user)
        return self.client.get("/api/calendar/events/", {"start": start, "end": end})

    @patch("modulocalendar.views.get_holidays", return_value=[])
    def test_listagem_responde_200_com_id_nos_eventos_locais(self, _holidays):
        hoje = timezone.now()
        resp = self._listar((hoje - timedelta(days=1)).isoformat(),
                            (hoje + timedelta(days=1)).isoformat())

        self.assertEqual(resp.status_code, 200)
        locais = [e for e in resp.json()
                  if e.get("extendedProps", {}).get("type") == "local"]
        self.assertEqual(len(locais), 1)
        self.assertEqual(locais[0]["id"], self.evento.id)

    @patch("modulocalendar.views.get_holidays", return_value=[])
    def test_tarefas_do_crm_entram_na_agenda_in_process(self, _holidays):
        hoje = timezone.now()
        resp = self._listar((hoje - timedelta(days=1)).isoformat(),
                            (hoje + timedelta(days=1)).isoformat())

        self.assertEqual(resp.status_code, 200)
        tarefas = [e for e in resp.json()
                   if e.get("extendedProps", {}).get("type") == "tarefa"]
        self.assertEqual(len(tarefas), 1)
        self.assertEqual(tarefas[0]["title"], "Ligar para Ana")
        self.assertEqual(tarefas[0]["id"], str(self.tarefa.id))

    @patch("modulocalendar.views.get_holidays", return_value=[])
    def test_feriados_buscados_para_cada_ano_do_periodo(self, mock_holidays):
        resp = self._listar("2026-12-01T00:00:00", "2027-01-31T00:00:00")

        self.assertEqual(resp.status_code, 200)
        anos = [chamada.args[0] for chamada in mock_holidays.call_args_list]
        self.assertEqual(anos, [2026, 2027])
