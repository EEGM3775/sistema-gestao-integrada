"""
Testes do calendário: a listagem agregada não pode quebrar (achado L1 — era
500 por filtro em campo inexistente), eventos locais saem com `id`, feriados
cobrem todos os anos do período e as tarefas do CRM entram in-process
(Fase 11.2 — sem o microsserviço funcoeslead).
"""
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from modulocrm.models import Interaction, Lead
from nucleo.models import Notificacao, Tenant, Usuario
from . import dias_uteis
from .models import CalendarEvent, EventReminder, Feriado, FeriadoSync
from .tasks import despachar_lembretes

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# Sem cache: o feed recorrente é relistado após cada mutação (em produção o
# django-redis limpa via delete_pattern; o LocMem/Dummy não o têm).
DUMMY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}


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


@override_settings(CACHES=DUMMY_CACHE)
class CalendarRecurrenceTests(APITestCase):
    """Fatia B: as ocorrências de um mestre são virtuais (expandidas no feed);
    editar/excluir 'esta/todas/futuras' opera por EXDATE, override e divisão."""

    JANELA = ("2026-08-01T00:00:00-03:00", "2026-08-31T23:59:59-03:00")

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="rec-a", nome="Recorrência A")
        cls.user = Usuario.objects.create(username="rec_user", tenant=cls.tenant)
        # 3 de agosto de 2026 é uma segunda-feira; 4 ocorrências semanais.
        inicio = timezone.make_aware(datetime(2026, 8, 3, 10, 0))
        cls.master = CalendarEvent.objects.create(
            title="Daily standup",
            start_time=inicio,
            end_time=inicio + timedelta(hours=1),
            user=cls.user,
            tenant=cls.tenant,
            recurrence_rule="FREQ=WEEKLY;COUNT=4",
        )

    def setUp(self):
        self.user.iam_permissions = [
            "calendario.evento.view", "calendario.evento.edit",
        ]
        self.client.force_authenticate(user=self.user)

    @patch("modulocalendar.views.get_holidays", return_value=[])
    def _ocorrencias(self, _holidays):
        resp = self.client.get("/api/calendar/events/",
                               {"start": self.JANELA[0], "end": self.JANELA[1]})
        self.assertEqual(resp.status_code, 200)
        return [e for e in resp.json()
                if e.get("extendedProps", {}).get("isRecurring")]

    def test_mestre_semanal_expande_em_ocorrencias_virtuais(self):
        ocorrencias = self._ocorrencias()
        self.assertEqual(len(ocorrencias), 4)
        # nenhuma ocorrência virtual usa o pk numérico do mestre como id
        self.assertTrue(all(str(o["id"]).startswith("occ-") for o in ocorrencias))
        self.assertTrue(all(o["extendedProps"]["masterId"] == self.master.id for o in ocorrencias))

    def test_excluir_apenas_esta_some_a_ocorrencia(self):
        segunda = self._ocorrencias()[1]["extendedProps"]["occurrenceStart"]
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/delete-recurrence/",
            {"scope": "this", "occurrence_start": segunda}, format="json")
        self.assertEqual(resp.status_code, 204)
        restantes = self._ocorrencias()
        self.assertEqual(len(restantes), 3)
        self.assertNotIn(segunda, [o["extendedProps"]["occurrenceStart"] for o in restantes])

    def test_editar_apenas_esta_cria_override(self):
        segunda = self._ocorrencias()[1]["extendedProps"]["occurrenceStart"]
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "this", "occurrence_start": segunda,
             "payload": {"title": "Standup remarcado"}}, format="json")
        self.assertEqual(resp.status_code, 201)
        override = CalendarEvent.objects.get(recurrence_master=self.master)
        self.assertEqual(override.title, "Standup remarcado")
        # a ocorrência original vira EXDATE (some da série); o override é local
        self.master.refresh_from_db()
        self.assertIn(segunda, self.master.excluded_dates)
        recorrentes = self._ocorrencias()
        self.assertEqual(len(recorrentes), 3)

    def test_editar_todas_desloca_a_serie(self):
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "all", "payload": {"title": "Novo título"}}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.master.refresh_from_db()
        self.assertEqual(self.master.title, "Novo título")
        self.assertEqual(len(self._ocorrencias()), 4)

    def test_excluir_todas_remove_o_mestre(self):
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/delete-recurrence/",
            {"scope": "all"}, format="json")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(CalendarEvent.objects.filter(id=self.master.id).exists())
        self.assertEqual(len(self._ocorrencias()), 0)

    def test_editar_futuras_divide_a_serie(self):
        terceira = self._ocorrencias()[2]["extendedProps"]["occurrenceStart"]
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "future", "occurrence_start": terceira,
             "payload": {"title": "Nova fase"}}, format="json")
        self.assertEqual(resp.status_code, 201)
        # mestre truncado (2 ocorrências) + novo mestre (2) = 4 no total,
        # agora repartidas em duas séries.
        recorrentes = self._ocorrencias()
        self.assertEqual(len(recorrentes), 4)
        titulos = {o["title"] for o in recorrentes}
        self.assertIn("Nova fase", titulos)
        self.assertIn("Daily standup", titulos)

    # --- C1: propagação de lembretes pelas actions de recorrência ---
    def _add_master_reminder(self, offset):
        EventReminder.objects.create(
            event=self.master, tenant=self.tenant, offset_minutes=offset)

    @staticmethod
    def _offsets(event):
        return sorted(event.reminders.values_list("offset_minutes", flat=True))

    def test_editar_todas_substitui_lembretes_do_mestre(self):
        self._add_master_reminder(30)
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "all", "payload": {"reminders": [10, 60]}}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.master.refresh_from_db()
        self.assertEqual(self._offsets(self.master), [10, 60])

    def test_editar_apenas_esta_herda_lembretes_no_override(self):
        segunda = self._ocorrencias()[1]["extendedProps"]["occurrenceStart"]
        self._add_master_reminder(30)
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "this", "occurrence_start": segunda,
             "payload": {"title": "Standup remarcado"}}, format="json")
        self.assertEqual(resp.status_code, 201)
        override = CalendarEvent.objects.get(recurrence_master=self.master)
        # payload sem `reminders` → herda os do mestre (não fica sem aviso).
        self.assertEqual(self._offsets(override), [30])

    def test_editar_apenas_esta_usa_lembretes_do_payload(self):
        segunda = self._ocorrencias()[1]["extendedProps"]["occurrenceStart"]
        self._add_master_reminder(30)
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "this", "occurrence_start": segunda,
             "payload": {"title": "Standup remarcado", "reminders": [15]}}, format="json")
        self.assertEqual(resp.status_code, 201)
        override = CalendarEvent.objects.get(recurrence_master=self.master)
        self.assertEqual(self._offsets(override), [15])

    def test_editar_futuras_herda_lembretes_e_preserva_o_mestre(self):
        terceira = self._ocorrencias()[2]["extendedProps"]["occurrenceStart"]
        self._add_master_reminder(30)
        resp = self.client.post(
            f"/api/calendar/events/{self.master.id}/update-recurrence/",
            {"scope": "future", "occurrence_start": terceira,
             "payload": {"title": "Nova fase"}}, format="json")
        self.assertEqual(resp.status_code, 201)
        novo = CalendarEvent.objects.get(title="Nova fase")
        self.assertEqual(self._offsets(novo), [30])         # novo mestre herdou
        self.master.refresh_from_db()
        self.assertEqual(self._offsets(self.master), [30])  # o truncado conserva


@override_settings(CACHES=DUMMY_CACHE)
class FeriadosSyncCommandTests(APITestCase):
    """O comando popula nacional/estadual (python-holidays) e municipal (dataset,
    mockado) e carimba o FeriadoSync."""

    MUNICIPAIS_2026 = [
        {"data": "23/01/2026", "nome": "Aniversário da cidade", "tipo": "MUNICIPAL",
         "uf": "SP", "codigo_ibge": 3550308},
    ]

    @patch("nucleo.geo._municipios_uf", return_value=[{"id": 3550308, "nome": "São Paulo"}])
    @patch("modulocalendar.management.commands.sincronizar_feriados.baixar_municipais")
    def test_sincroniza_tres_escopos(self, mock_baixar, _mun):
        mock_baixar.side_effect = lambda ano: self.MUNICIPAIS_2026 if ano == 2026 else []
        call_command("sincronizar_feriados", anos=[2026], stdout=StringIO())

        self.assertTrue(Feriado.objects.filter(escopo="nacional").exists())
        # SP acrescenta a Revolução Constitucionalista (09/07) sobre o nacional.
        self.assertTrue(Feriado.objects.filter(escopo="estadual", uf="SP").exists())
        municipal = Feriado.objects.get(escopo="municipal", ibge="3550308")
        self.assertEqual(municipal.cidade, "São Paulo")
        self.assertEqual(municipal.data, date(2026, 1, 23))

        sync = FeriadoSync.objects.get(pk=1)
        self.assertGreater(sync.total, 0)
        self.assertEqual(sync.detalhes["municipal"], 1)


@override_settings(CACHES=DUMMY_CACHE)
class FeriadosFeedTests(APITestCase):
    """O feed traz nacional sempre; estadual só com `uf`; municipal só com `ibge`,
    cada um com escopo e nome da localidade."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="fer-a", nome="Feriados A")
        cls.user = Usuario.objects.create(username="fer_user", tenant=cls.tenant)
        Feriado.objects.create(data=date(2026, 1, 1), nome="Confraternização", escopo="nacional")
        Feriado.objects.create(data=date(2026, 7, 9), nome="Revolução Constitucionalista",
                               escopo="estadual", uf="SP")
        Feriado.objects.create(data=date(2026, 1, 25), nome="Aniversário de SP",
                               escopo="municipal", uf="SP", ibge="3550308", cidade="São Paulo")

    def _feriados(self, uf=None, ibge=None):
        # Há um Feriado nacional no setup → o fallback ao Nager não dispara.
        self.user.iam_permissions = ["calendario.evento.view"]
        self.client.force_authenticate(user=self.user)
        params = {"start": "2026-01-01T00:00:00-03:00", "end": "2026-12-31T00:00:00-03:00"}
        if uf:
            params["uf"] = uf
        if ibge:
            params["ibge"] = ibge
        resp = self.client.get("/api/calendar/events/", params)
        self.assertEqual(resp.status_code, 200)
        return [e for e in resp.json() if e.get("extendedProps", {}).get("type") == "holiday"]

    def test_sem_localidade_so_nacional(self):
        escopos = {f["extendedProps"]["scope"] for f in self._feriados()}
        self.assertEqual(escopos, {"nacional"})

    def test_com_uf_inclui_estadual(self):
        feriados = self._feriados(uf="SP")
        escopos = {f["extendedProps"]["scope"] for f in feriados}
        self.assertEqual(escopos, {"nacional", "estadual"})

    def test_com_ibge_inclui_municipal_com_cidade(self):
        feriados = self._feriados(uf="SP", ibge="3550308")
        municipais = [f for f in feriados if f["extendedProps"]["scope"] == "municipal"]
        self.assertEqual(len(municipais), 1)
        self.assertIn("São Paulo", municipais[0]["title"])

    @patch("modulocalendar.views.get_holidays", return_value=[])
    def test_mes_sem_feriado_nacional_nao_chama_api_externa(self, mock_holidays):
        """D147 — o plano B pergunta pelo ANO, não pela janela.

        Março de 2026 não tem feriado nacional nenhum, e isso é o calendário
        brasileiro, não tabela vazia. A condição anterior ("não vieram nacionais
        nesta janela") disparava a viagem à Nager.Date em cinco dos doze meses,
        a cada navegação — que era a demora que o dono via na tela.
        """
        self.user.iam_permissions = ["calendario.evento.view"]
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/calendar/events/", {
            "start": "2026-03-01T00:00:00-03:00", "end": "2026-03-31T23:59:59-03:00",
        })

        self.assertEqual(resp.status_code, 200)
        mock_holidays.assert_not_called()

    @patch("modulocalendar.views.get_holidays", return_value=[])
    def test_ano_fora_da_tabela_ainda_cai_no_plano_b(self, mock_holidays):
        """E o plano B continua existindo: 2031 não foi sincronizado."""
        self.user.iam_permissions = ["calendario.evento.view"]
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/calendar/events/", {
            "start": "2031-03-01T00:00:00-03:00", "end": "2031-03-31T23:59:59-03:00",
        })

        self.assertEqual(resp.status_code, 200)
        mock_holidays.assert_called_once_with(2031, "BR")


@override_settings(CACHES=DUMMY_CACHE)
class FeriadosStatusTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="st-a", nome="Status A")
        cls.user = Usuario.objects.create(username="st_user", tenant=cls.tenant)
        FeriadoSync.objects.create(pk=1, anos="2026", total=42)

    def test_superuser_ve_status(self):
        self.user.is_platform_admin = True
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/calendar/feriados/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 42)

    def test_usuario_comum_recebe_403(self):
        self.user.is_platform_admin = False
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/calendar/feriados/status/")
        self.assertEqual(resp.status_code, 403)


@override_settings(CACHES=DUMMY_CACHE)
class CalendarReminderCrudTests(APITestCase):
    """Fatia C: lembretes viajam no CRUD do evento (offsets em minutos) — criados,
    devolvidos no retrieve e substituídos no PATCH."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="rem-a", nome="Lembretes A")
        cls.user = Usuario.objects.create(username="rem_user", tenant=cls.tenant)

    def setUp(self):
        self.user.iam_permissions = ["calendario.evento.view", "calendario.evento.edit"]
        self.client.force_authenticate(user=self.user)

    def _payload(self, **extra):
        inicio = timezone.now()
        base = {
            "title": "Reunião",
            "start_time": inicio.isoformat(),
            "end_time": (inicio + timedelta(hours=1)).isoformat(),
            "all_day": False,
            "event_type": "reuniao",
        }
        base.update(extra)
        return base

    def test_cria_evento_com_lembretes(self):
        resp = self.client.post("/api/calendar/events/",
                                self._payload(reminders=[1440, 10, 10]), format="json")
        self.assertEqual(resp.status_code, 201)
        evento_id = resp.json()["id"]
        # Deduplicado e persistido.
        self.assertEqual(EventReminder.objects.filter(event_id=evento_id).count(), 2)
        # Retrieve devolve os offsets ordenados.
        detalhe = self.client.get(f"/api/calendar/events/{evento_id}/")
        self.assertEqual(detalhe.json()["reminders"], [10, 1440])

    def test_patch_substitui_lembretes(self):
        evento = CalendarEvent.objects.create(
            title="Evento", start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            user=self.user, tenant=self.tenant,
        )
        EventReminder.objects.create(event=evento, tenant=self.tenant, offset_minutes=10)

        resp = self.client.patch(f"/api/calendar/events/{evento.id}/",
                                 {"reminders": [30]}, format="json")
        self.assertEqual(resp.status_code, 200)
        offsets = list(evento.reminders.values_list("offset_minutes", flat=True))
        self.assertEqual(offsets, [30])

    def test_patch_sem_reminders_nao_altera(self):
        evento = CalendarEvent.objects.create(
            title="Evento", start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            user=self.user, tenant=self.tenant,
        )
        EventReminder.objects.create(event=evento, tenant=self.tenant, offset_minutes=10)

        resp = self.client.patch(f"/api/calendar/events/{evento.id}/",
                                 {"title": "Renomeado"}, format="json")
        self.assertEqual(resp.status_code, 200)
        # Lembrete preservado (payload sem a chave `reminders`).
        self.assertEqual(evento.reminders.count(), 1)


@override_settings(CACHES=DUMMY_CACHE)
class LembreteDispatchTests(APITestCase):
    """Fatia C: a task varre os lembretes vencendo, cria uma Notificacao in-app
    por ocorrência e não repete (dedupe por `last_sent_occurrence`)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="disp-a", nome="Dispatch A")
        cls.user = Usuario.objects.create(username="disp_user", tenant=cls.tenant)

    def _evento_com_lembrete(self, inicio, offset):
        evento = CalendarEvent.objects.create(
            title="Reunião de obra", start_time=inicio,
            end_time=inicio + timedelta(hours=1), user=self.user, tenant=self.tenant,
        )
        EventReminder.objects.create(event=evento, tenant=self.tenant, offset_minutes=offset)
        return evento

    def test_lembrete_vencendo_gera_notificacao(self):
        # Evento em 5 min, lembrete 10 min antes → aviso já venceu.
        self._evento_com_lembrete(timezone.now() + timedelta(minutes=5), offset=10)
        enviados = despachar_lembretes()
        self.assertEqual(enviados, 1)
        notif = Notificacao.objects.get(user=self.user)
        self.assertEqual(notif.tipo, Notificacao.Tipo.LEMBRETE)
        self.assertIn("Reunião de obra", notif.titulo)

    def test_nao_repete_no_segundo_ciclo(self):
        self._evento_com_lembrete(timezone.now() + timedelta(minutes=5), offset=10)
        despachar_lembretes()
        segundo = despachar_lembretes()
        self.assertEqual(segundo, 0)
        self.assertEqual(Notificacao.objects.filter(user=self.user).count(), 1)

    def test_evento_distante_nao_dispara(self):
        # Evento daqui a 2h com lembrete de 10 min → ainda não venceu.
        self._evento_com_lembrete(timezone.now() + timedelta(hours=2), offset=10)
        self.assertEqual(despachar_lembretes(), 0)
        self.assertEqual(Notificacao.objects.filter(user=self.user).count(), 0)


class DiaUtilBancarioTests(TestCase):
    """O vencimento que vai ao boleto — sábado, domingo e feriado empurram.

    A régua é bancária, não de obra: o `CalendarioTrabalho` do PDCA responde
    "a equipe trabalha neste dia?", e a resposta dele pode ser "sim" num sábado
    de mutirão. O banco não compensa nesse sábado, e é o banco que decide quando
    um boleto é pagável.
    """

    @classmethod
    def setUpTestData(cls):
        Feriado.objects.create(
            data=date(2026, 10, 12), nome="Nossa Senhora Aparecida", escopo="nacional")
        Feriado.objects.create(
            data=date(2026, 8, 11), nome="São Vicente de Paulo", escopo="estadual", uf="SC")
        Feriado.objects.create(
            data=date(2026, 6, 18), nome="Aniversário do município", escopo="municipal",
            uf="SC", ibge="4211900", cidade="Palhoça")

    def test_dia_util_fica_onde_esta(self):
        ajuste = dias_uteis.AjusteDeVencimento()
        self.assertEqual(ajuste(date(2026, 3, 10)), date(2026, 3, 10))  # terça

    def test_sabado_e_domingo_vao_para_segunda(self):
        ajuste = dias_uteis.AjusteDeVencimento()
        self.assertEqual(ajuste(date(2026, 3, 7)), date(2026, 3, 9))   # sábado
        self.assertEqual(ajuste(date(2026, 3, 8)), date(2026, 3, 9))   # domingo

    def test_feriado_nacional_vale_para_todo_mundo(self):
        """12/10/2026 é segunda-feira: sem a tabela de feriados, passaria."""
        self.assertEqual(
            dias_uteis.AjusteDeVencimento()(date(2026, 10, 12)), date(2026, 10, 13))

    def test_feriado_estadual_so_vale_com_a_uf(self):
        """Feriado de SC não pode adiar o boleto de um lote no Paraná."""
        self.assertEqual(
            dias_uteis.AjusteDeVencimento(uf="SC")(date(2026, 8, 11)), date(2026, 8, 12))
        self.assertEqual(
            dias_uteis.AjusteDeVencimento(uf="PR")(date(2026, 8, 11)), date(2026, 8, 11))

    def test_feriado_municipal_so_vale_com_o_codigo_ibge(self):
        """Nome de cidade não é chave — afirmar feriado municipal sem o código
        seria inventar dia parado."""
        com = dias_uteis.AjusteDeVencimento(uf="SC", ibge="4211900")
        sem = dias_uteis.AjusteDeVencimento(uf="SC")
        self.assertEqual(com(date(2026, 6, 18)), date(2026, 6, 19))
        self.assertEqual(sem(date(2026, 6, 18)), date(2026, 6, 18))

    def test_feriado_colado_no_fim_de_semana_atravessa_os_dois(self):
        """Sexta feriado + sábado + domingo: o vencimento cai na segunda."""
        Feriado.objects.create(data=date(2026, 3, 6), nome="Ponte", escopo="nacional")
        self.assertEqual(
            dias_uteis.AjusteDeVencimento()(date(2026, 3, 6)), date(2026, 3, 9))

    def test_explicar_diz_por_que_a_data_mudou(self):
        data, motivo = dias_uteis.AjusteDeVencimento().explicar(date(2026, 10, 12))
        self.assertEqual(data, date(2026, 10, 13))
        self.assertEqual(motivo, "Nossa Senhora Aparecida")
        self.assertEqual(
            dias_uteis.AjusteDeVencimento().explicar(date(2026, 3, 10)),
            (date(2026, 3, 10), ""),
        )

    def test_nunca_antecipa(self):
        """Antecipar cobraria o comprador antes do combinado — o ajuste só adia."""
        for dia in (date(2026, 3, 7), date(2026, 3, 8), date(2026, 10, 12)):
            self.assertGreaterEqual(dias_uteis.AjusteDeVencimento()(dia), dia)

    def test_sem_ajuste_devolve_a_data_intacta(self):
        self.assertEqual(dias_uteis.SEM_AJUSTE(date(2026, 3, 7)), date(2026, 3, 7))
        self.assertEqual(dias_uteis.SEM_AJUSTE.explicar(date(2026, 3, 7)), (date(2026, 3, 7), ""))

    def test_none_atravessa(self):
        """Título sem vencimento não é motivo para estourar no meio de uma emissão."""
        self.assertIsNone(dias_uteis.AjusteDeVencimento()(None))

    def test_base_vazia_e_um_estado_que_a_tela_precisa_saber(self):
        Feriado.objects.all().delete()
        self.assertFalse(dias_uteis.base_sincronizada())
        # Sem feriados o ajuste ainda existe — só não conhece feriado.
        self.assertEqual(dias_uteis.AjusteDeVencimento()(date(2026, 10, 12)), date(2026, 10, 12))
        self.assertEqual(dias_uteis.AjusteDeVencimento()(date(2026, 3, 7)), date(2026, 3, 9))

    def test_uma_consulta_por_ano_e_nao_por_parcela(self):
        """O carnê pede o ajuste centenas de vezes; a tabela é lida uma vez por
        ano tocado. Sem o cache, gerar 360 parcelas seriam 360 consultas."""
        ajuste = dias_uteis.AjusteDeVencimento(uf="SC", ibge="4211900")
        with self.assertNumQueries(2):  # 2026 e 2027, carregados na primeira chamada
            for mes in range(1, 13):
                ajuste(date(2026, mes, 10))
