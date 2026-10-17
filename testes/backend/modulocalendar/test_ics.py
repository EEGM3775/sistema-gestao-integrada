"""Calendário, Fatia E — local, busca no servidor e a agenda em `.ics`.

A importação segue a regra do dono para toda importação: **só cria, e é tudo
ou nada**. Um evento ilegível ou um UID que já está na agenda recusa o arquivo
inteiro, com o motivo.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from modulocalendar import ics
from modulocalendar.models import Calendar, CalendarEvent
from nucleo.models import Tenant, Usuario

DUMMY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
ESCRITA = ["calendario.evento.view", "calendario.evento.edit"]

GOOGLE = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Google Inc//Google Calendar 70.9054//EN\r\n"
    "BEGIN:VEVENT\r\nDTSTART;TZID=America/Sao_Paulo:20261020T090000\r\n"
    "DTEND;TZID=America/Sao_Paulo:20261020T100000\r\nRRULE:FREQ=WEEKLY;COUNT=4\r\n"
    "UID:abc123@google.com\r\nSUMMARY:Reunião\\, semanal\r\n"
    "DESCRIPTION:Pauta:\\nmedição\r\nLOCATION:Canteiro da obra\r\n"
    "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT10M\r\nEND:VALARM\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTSTART;TZID=America/Sao_Paulo:20261027T110000\r\n"
    "DTEND;TZID=America/Sao_Paulo:20261027T120000\r\n"
    "RECURRENCE-ID;TZID=America/Sao_Paulo:20261027T090000\r\n"
    "UID:abc123@google.com\r\nSUMMARY:Reunião (remarcada)\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261102\r\nDTEND;VALUE=DATE:20261103\r\n"
    "UID:feriado@google.com\r\nSUMMARY:Finados — folga do canteiro com uma descrição longa que dobra a linha\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


class LeitorIcsTests(SimpleTestCase):
    def test_le_o_que_o_google_manda(self):
        lidos, erros = ics.ler(GOOGLE)
        self.assertEqual(erros, [])
        serie, excecao, dia = lidos
        self.assertEqual(serie.titulo, "Reunião, semanal")
        self.assertEqual(serie.descricao, "Pauta:\nmedição")
        self.assertEqual(serie.local, "Canteiro da obra")
        self.assertEqual(serie.regra, "FREQ=WEEKLY;COUNT=4")
        self.assertEqual(serie.inicio.astimezone(dt_timezone.utc).hour, 12)  # 9h em São Paulo
        self.assertEqual(excecao.recorrencia_de.astimezone(dt_timezone.utc),
                         datetime(2026, 10, 27, 12, tzinfo=dt_timezone.utc))
        self.assertTrue(dia.dia_inteiro)

    def test_escrever_e_ler_de_volta(self):
        inicio = datetime(2026, 10, 20, 12, tzinfo=dt_timezone.utc)
        ev = CalendarEvent(pk=7, title="Linha, com; vírgula", description="a\nb", location="Sala 2",
                           start_time=inicio, end_time=inicio + timedelta(hours=1), all_day=False,
                           recurrence_rule="FREQ=DAILY;COUNT=2")
        texto = ics.escrever([ev], "sgi.test")
        self.assertTrue(all(len(l.encode()) <= 75 for l in texto.split("\r\n")))
        (lido,), erros = ics.ler(texto)
        self.assertEqual(erros, [])
        self.assertEqual(lido.uid, "sgi-7@sgi.test")
        self.assertEqual((lido.titulo, lido.descricao, lido.local), ("Linha, com; vírgula", "a\nb", "Sala 2"))
        self.assertEqual(lido.inicio, inicio)

    def test_evento_sem_inicio_vira_erro_com_a_linha(self):
        texto = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:x\nSUMMARY:Sem data\nEND:VEVENT\nEND:VCALENDAR\n"
        lidos, erros = ics.ler(texto)
        self.assertEqual(lidos, [])
        self.assertIn("linha 2", erros[0])

    def test_nao_e_ics(self):
        with self.assertRaises(ics.IcsInvalido):
            ics.ler("nome;data\nAna;2026-10-10\n")


@override_settings(CACHES=DUMMY_CACHE)
@patch("modulocalendar.views.get_holidays", return_value=[])
class ImportarExportarTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="cal-e", nome="Empresa E")
        cls.ana = Usuario.objects.create(username="ana_e", tenant=cls.tenant)
        cls.bia = Usuario.objects.create(username="bia_e", tenant=cls.tenant)

    def setUp(self):
        self.ana.iam_permissions = list(ESCRITA)
        self.client.force_authenticate(user=self.ana)

    def _importar(self, texto, **extra):
        arquivo = SimpleUploadedFile("agenda.ics", texto.encode(), content_type="text/calendar")
        return self.client.post("/api/calendar/events/importar-ics/", {"arquivo": arquivo, **extra},
                                format="multipart")

    def test_importa_serie_excecao_e_dia_inteiro(self, _h):
        resp = self._importar(GOOGLE)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["criados"], 3)
        mestre = CalendarEvent.objects.get(ical_uid="abc123@google.com", recurrence_master__isnull=True)
        self.assertEqual(mestre.location, "Canteiro da obra")
        self.assertEqual(mestre.user, self.ana)
        self.assertIsNone(mestre.calendar)
        override = mestre.overrides.get()
        self.assertEqual(override.title, "Reunião (remarcada)")
        # A ocorrência original de 27/10 sai da série (o override a substitui).
        from modulocalendar.recurrence import expand_occurrences
        ocorrencias = expand_occurrences(mestre, mestre.start_time, mestre.start_time + timedelta(days=30))
        self.assertEqual(len(ocorrencias), 3)

    def test_reimportar_recusa_tudo(self, _h):
        self.assertEqual(self._importar(GOOGLE).status_code, 201)
        antes = CalendarEvent.objects.count()
        resp = self._importar(GOOGLE)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("já foi importado", " ".join(resp.json()["erros"]))
        self.assertEqual(CalendarEvent.objects.count(), antes)

    def test_um_evento_ruim_recusa_o_arquivo_inteiro(self, _h):
        ruim = GOOGLE.replace("END:VCALENDAR", "BEGIN:VEVENT\r\nUID:r\r\nSUMMARY:x\r\nEND:VEVENT\r\nEND:VCALENDAR")
        resp = self._importar(ruim)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CalendarEvent.objects.count(), 0)

    def test_importa_numa_agenda_de_equipe_que_se_ve(self, _h):
        agenda = Calendar.objects.create(tenant=self.tenant, owner=self.bia, name="Equipe", scope="equipe")
        self.assertEqual(self._importar(GOOGLE, calendar=agenda.pk).status_code, 403)
        agenda.members.create(user=self.ana, tenant=self.tenant)
        self.assertEqual(self._importar(GOOGLE, calendar=agenda.pk).status_code, 201)
        self.assertEqual(CalendarEvent.objects.filter(calendar=agenda).count(), 3)

    def test_exporta_a_agenda_pessoal(self, _h):
        inicio = timezone.now()
        CalendarEvent.objects.create(tenant=self.tenant, user=self.ana, title="Minha",
                                     start_time=inicio, end_time=inicio + timedelta(hours=1),
                                     location="Obra 3")
        CalendarEvent.objects.create(tenant=self.tenant, user=self.bia, title="Da Bia",
                                     start_time=inicio, end_time=inicio + timedelta(hours=1))
        resp = self.client.get("/api/calendar/events/exportar-ics/", {"calendar": "meus"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/calendar"))
        texto = resp.content.decode()
        self.assertIn("SUMMARY:Minha", texto)
        self.assertIn("LOCATION:Obra 3", texto)
        self.assertNotIn("Da Bia", texto)

    def test_busca_sem_acento_por_titulo_e_local(self, _h):
        inicio = timezone.now()
        CalendarEvent.objects.create(tenant=self.tenant, user=self.ana, title="Medição de outubro",
                                     start_time=inicio, end_time=inicio + timedelta(hours=1))
        CalendarEvent.objects.create(tenant=self.tenant, user=self.ana, title="Visita",
                                     location="Canteiro São José", start_time=inicio,
                                     end_time=inicio + timedelta(hours=1))
        CalendarEvent.objects.create(tenant=self.tenant, user=self.bia, title="Medicao da Bia",
                                     start_time=inicio, end_time=inicio + timedelta(hours=1))
        achados = self.client.get("/api/calendar/events/busca/", {"q": "medicao"}).json()
        self.assertEqual([e["title"] for e in achados["results"]], ["Medição de outubro"])
        achados = self.client.get("/api/calendar/events/busca/", {"q": "sao jose"}).json()
        self.assertEqual([e["title"] for e in achados["results"]], ["Visita"])
