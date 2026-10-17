from datetime import timedelta

from rest_framework import filters, generics, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from payment.planos import CALENDAR_ICS_TETO_EVENTOS, CALENDAR_ICS_TETO_KB

from nucleo import autorizacao
from nucleo.busca import BuscaSemAcento
from nucleo.models import Notificacao, Usuario
from nucleo.notificacoes import criar_notificacao
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from nucleo import geo
from modulocrm.models import Interaction
from modulodiario.models import DiarioObra

from . import acesso, ics
from .feriados import FeriadosMunicipais
from .models import (
    Calendar, CalendarEvent, CalendarMember, EventAttendee, EventReminder, Feriado, FeriadoSync,
)
from .pagination import CalendarioPageNumberPagination
from .serializers import CalendarEventSerializer, CalendarSerializer, nome_de, pessoas_da_empresa
from .services import get_holidays
from . import recurrence

import logging

logger = logging.getLogger(__name__)

# Cores por escopo de feriado (Fatia F) — refletidas na legenda do frontend.
FERIADO_LOCAL_PAIS = "Brasil"

#: Onde o aviso de convite leva: a agenda já aberta no evento.
URL_EVENTO = "/app/calendario?evento={id}"


def limpar_cache_feed(user_ids):
    """Some com o feed em cache de cada um (`None` = de todos: agenda da empresa)."""
    try:
        if user_ids is None:
            cache.delete_pattern("calendar_events_*")
            return
        for uid in user_ids:
            cache.delete_pattern(f"calendar_events_{uid}_*")
    except Exception as e:  # cache tolerante a queda do Redis
        logger.error(f"Erro ao limpar o cache do calendário: {e}")


def _quando(event) -> str:
    inicio = timezone.localtime(event.start_time)
    return inicio.strftime("%d/%m/%Y") if event.all_day else inicio.strftime("%d/%m/%Y %H:%M")


class CalendarEventViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    # Camada 2 (Fase 9.B/D5): agenda é "base" (sem entitlement de módulo), mas a
    # escrita exige permissão. GET→calendario.evento.view · escrita→.edit
    # (as actions de recorrência são POST → .edit, como o CRUD).
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "calendario.evento"
    # Responder a um convite é ler a agenda, não editá-la: quem só tem `.view`
    # também aceita ou recusa (Fatia D).
    action_permission_map = {"responder": "calendario.evento.view"}
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        """Os eventos que a pessoa vê — os dela, os das agendas que vê e os
        convites (Fatia D). A janela do feed é aplicada em `list()` (recorrência
        exige tratar mestres fora da janela à parte)."""
        # prefetch dos lembretes/convidados: o retrieve (diálogo) os serializa.
        return (
            acesso.eventos_visiveis(self.request.user)
            .select_related('calendar', 'user')
            .prefetch_related('reminders', 'attendees__user')
        )

    def _exigir_edicao(self, event):
        """Ver não é editar: o convidado que não vê a agenda só responde."""
        if not acesso.pode_editar_evento(self.request.user, event):
            raise PermissionDenied("Você foi convidado para este evento, mas não pode alterá-lo.")

    # ------------------------------------------------------------------ CRUD
    def perform_create(self, serializer):
        # Injeta tenant (como o mixin) e o dono do evento numa única gravação —
        # o dono não pode vir do cliente.
        reminders = serializer.validated_data.pop('reminders', None)
        attendees = serializer.validated_data.pop('attendees', None)
        event = serializer.save(
            tenant_id=getattr(self.request.user, 'tenant_id', None),
            user=self.request.user,
        )
        if reminders is not None:
            self._sync_reminders(event, reminders)
        if attendees is not None:
            self._sync_attendees(event, attendees)
        limpar_cache_feed(acesso.interessados(event))

    def perform_update(self, serializer):
        self._exigir_edicao(serializer.instance)
        antes = acesso.interessados(serializer.instance)
        reminders = serializer.validated_data.pop('reminders', None)
        attendees = serializer.validated_data.pop('attendees', None)
        # Reforça o tenant do dono (como o mixin) — impede mover o evento de tenant.
        event = serializer.save(tenant_id=getattr(self.request.user, 'tenant_id', None))
        # `reminders` ausente do payload = não mexe; presente (mesmo []) = substitui.
        if reminders is not None:
            self._sync_reminders(event, reminders)
        if attendees is not None:
            self._sync_attendees(event, attendees)
        depois = acesso.interessados(event)
        limpar_cache_feed(None if antes is None or depois is None else antes | depois)

    @staticmethod
    def _sync_reminders(event, offsets):
        """Substitui os lembretes do evento pela lista de offsets (minutos).
        Deduplica; o tenant é herdado do evento (fora de request seria barrado
        pela RLS). Recria as linhas — os `last_sent_occurrence` reiniciam, o que
        é o comportamento correto quando o usuário mexe nos lembretes."""
        desejados = sorted(set(offsets))
        event.reminders.all().delete()
        EventReminder.objects.bulk_create([
            EventReminder(event=event, tenant_id=event.tenant_id, offset_minutes=off)
            for off in desejados
        ])

    @staticmethod
    def _sync_attendees(event, pessoas, *, avisar=True, respostas=None):
        """Deixa como convidados exatamente `pessoas` (Usuario). Quem fica guarda a
        resposta; quem entra nasce `pendente` e recebe o convite no sino; quem sai
        é avisado. O dono do evento não se convida. `respostas` ({user_id:
        status}) copia as respostas de uma série para o evento derivado dela."""
        respostas = respostas or {}
        desejados = {p.pk: p for p in pessoas if p.pk != event.user_id}
        atuais = {a.user_id: a for a in event.attendees.all()}
        saem = [uid for uid in atuais if uid not in desejados]
        entram = [p for uid, p in desejados.items() if uid not in atuais]
        if saem:
            event.attendees.filter(user_id__in=saem).delete()
        EventAttendee.objects.bulk_create([
            EventAttendee(
                event=event, tenant_id=event.tenant_id, user=p,
                status=respostas.get(p.pk, EventAttendee.Status.PENDENTE),
            )
            for p in entram
        ])
        if not avisar:
            return
        quem = nome_de(event.user)
        for p in entram:
            criar_notificacao(
                user=p, tenant_id=event.tenant_id,
                titulo=f"Convite: {event.title}"[:200],
                mensagem=f"{quem} convidou você para \"{event.title}\" em {_quando(event)}. "
                         "Responda na agenda.",
                url=URL_EVENTO.format(id=event.pk),
                nivel=Notificacao.Nivel.DECIDIR,
            )
        for uid in saem:
            criar_notificacao(
                user=atuais[uid].user, tenant_id=event.tenant_id,
                titulo=f"Convite retirado: {event.title}"[:200],
                mensagem=f"{quem} tirou você de \"{event.title}\" ({_quando(event)}).",
                url="/app/calendario",
            )

    @staticmethod
    def _reminders_for(payload, master):
        """Offsets de lembrete a aplicar numa ocorrência/série **derivada** do
        mestre (override de 'só esta' ou novo mestre de 'futuras'): os do payload
        quando o cliente os envia; senão herda os do mestre — para que editar a
        recorrência não perca os lembretes silenciosamente (C1)."""
        if payload.get('reminders') is not None:
            return payload['reminders']
        return [r.offset_minutes for r in master.reminders.all()]

    @staticmethod
    def _herdar_convidados(master, derivado):
        """O evento derivado de uma série (override ou novo mestre) leva os
        convidados e as respostas deles — sem novo convite: já foram convidados."""
        convites = list(master.attendees.select_related('user'))
        CalendarEventViewSet._sync_attendees(
            derivado, [a.user for a in convites], avisar=False,
            respostas={a.user_id: a.status for a in convites},
        )

    def perform_destroy(self, instance):
        self._exigir_edicao(instance)
        interessados = acesso.interessados(instance)
        convidados = list(instance.attendees.select_related('user'))
        self._avisar_cancelamento(instance, convidados)
        super().perform_destroy(instance)
        limpar_cache_feed(interessados)

    def _avisar_cancelamento(self, event, convidados):
        for a in convidados:
            if a.status == EventAttendee.Status.RECUSADO:
                continue
            criar_notificacao(
                user=a.user, tenant_id=event.tenant_id,
                titulo=f"Evento cancelado: {event.title}"[:200],
                mensagem=f"{nome_de(self.request.user)} cancelou \"{event.title}\" ({_quando(event)}).",
                url="/app/calendario",
            )

    # --------------------------------------------- Actions de recorrência
    @action(detail=True, methods=['post'], url_path='update-recurrence')
    def update_recurrence(self, request, pk=None):
        """Edita uma série: `scope` = `this` (só esta ocorrência → override),
        `all` (a série toda, deslocando pela diferença desta ocorrência) ou
        `future` (desta em diante → divide a série)."""
        master = self.get_object()
        self._exigir_edicao(master)
        scope = request.data.get('scope', 'this')
        occ_start = recurrence.parse_iso(request.data.get('occurrence_start'))
        payload = request.data.get('payload', {}) or {}
        new_start = recurrence.parse_iso(payload.get('start_time'))
        new_end = recurrence.parse_iso(payload.get('end_time'))
        base_duration = master.end_time - master.start_time

        if scope == 'this':
            if occ_start is None:
                return Response({'detail': 'occurrence_start é obrigatório.'}, status=400)
            self._exclude_occurrence(master, occ_start)
            override = CalendarEvent.objects.create(
                tenant_id=master.tenant_id,
                user=master.user,
                calendar=master.calendar,
                title=payload.get('title', master.title),
                description=payload.get('description', master.description),
                location=payload.get('location', master.location),
                event_type=payload.get('event_type', master.event_type),
                all_day=payload.get('all_day', master.all_day),
                start_time=new_start or occ_start,
                end_time=new_end or (occ_start + base_duration),
                recurrence_master=master,
                original_start=occ_start,
            )
            # Lembretes do override: os enviados ou, na ausência, herdados do
            # mestre (C1) — a ocorrência editada não fica sem aviso.
            self._sync_reminders(override, self._reminders_for(payload, master))
            self._herdar_convidados(master, override)
            limpar_cache_feed(acesso.interessados(master))
            return Response(CalendarEventSerializer(override).data, status=status.HTTP_201_CREATED)

        if scope == 'all':
            if new_start and occ_start:
                delta = new_start - occ_start
                duration = (new_end - new_start) if (new_start and new_end) else base_duration
                master.start_time = master.start_time + delta
                master.end_time = master.start_time + duration
            antes = acesso.interessados(master)
            for field in ('title', 'description', 'location', 'event_type', 'all_day', 'recurrence_rule'):
                if field in payload:
                    setattr(master, field, payload[field])
            if 'calendar' in payload:
                # Mudar a série de agenda: só para uma agenda que se vê.
                alvo = payload['calendar']
                if alvo in (None, ''):
                    master.calendar = None
                else:
                    calendar = acesso.agendas_visiveis(request.user).filter(pk=alvo).first()
                    if calendar is None:
                        return Response({'calendar': 'Você não tem acesso a esta agenda.'}, status=400)
                    master.calendar = calendar
            master.save()
            # A série toda: substitui os lembretes do mestre quando enviados
            # (valem para todas as ocorrências virtuais); ausente = não mexe.
            if payload.get('reminders') is not None:
                self._sync_reminders(master, payload['reminders'])
            if payload.get('attendees') is not None:
                self._sync_attendees(master, pessoas_da_empresa(request, payload['attendees']))
            depois = acesso.interessados(master)
            limpar_cache_feed(None if antes is None or depois is None else antes | depois)
            return Response(CalendarEventSerializer(master).data)

        if scope == 'future':
            if occ_start is None:
                return Response({'detail': 'occurrence_start é obrigatório.'}, status=400)
            original_rule = master.recurrence_rule
            duration = (new_end - new_start) if (new_start and new_end) else base_duration
            # Lembretes do novo mestre: capturados antes (herdam os do atual se o
            # payload não os enviar); o mestre truncado conserva os seus (C1).
            reminders = self._reminders_for(payload, master)
            # Trunca a série atual até imediatamente antes desta ocorrência.
            master.recurrence_rule = recurrence.truncate_rule_until(
                original_rule, occ_start - timedelta(seconds=1))
            master.save(update_fields=['recurrence_rule'])
            # Regra do novo mestre: a do payload (usuário redefiniu o padrão) ou a
            # original com o COUNT descontado das ocorrências já consumidas.
            new_rule = payload.get('recurrence_rule') or recurrence.split_rule_for_future(
                original_rule, master.start_time, occ_start)
            new_master = CalendarEvent.objects.create(
                tenant_id=master.tenant_id,
                user=master.user,
                calendar=master.calendar,
                title=payload.get('title', master.title),
                description=payload.get('description', master.description),
                location=payload.get('location', master.location),
                event_type=payload.get('event_type', master.event_type),
                all_day=payload.get('all_day', master.all_day),
                start_time=new_start or occ_start,
                end_time=new_end or (occ_start + duration),
                recurrence_rule=new_rule,
            )
            self._sync_reminders(new_master, reminders)
            self._herdar_convidados(master, new_master)
            limpar_cache_feed(acesso.interessados(master))
            return Response(CalendarEventSerializer(new_master).data, status=status.HTTP_201_CREATED)

        return Response({'detail': f'scope inválido: {scope}'}, status=400)

    @action(detail=True, methods=['post'], url_path='delete-recurrence')
    def delete_recurrence(self, request, pk=None):
        """Exclui de uma série: `scope` = `this` / `all` / `future`."""
        master = self.get_object()
        self._exigir_edicao(master)
        scope = request.data.get('scope', 'this')
        occ_start = recurrence.parse_iso(request.data.get('occurrence_start'))
        interessados = acesso.interessados(master)

        if scope == 'all':
            self._avisar_cancelamento(master, list(master.attendees.select_related('user')))
            master.delete()  # cascata nos overrides
        elif scope == 'future':
            if occ_start is None:
                return Response({'detail': 'occurrence_start é obrigatório.'}, status=400)
            master.recurrence_rule = recurrence.truncate_rule_until(
                master.recurrence_rule, occ_start - timedelta(seconds=1))
            master.save(update_fields=['recurrence_rule'])
            master.overrides.filter(original_start__gte=occ_start).delete()
        elif occ_start is not None:  # this
            self._exclude_occurrence(master, occ_start)
            master.overrides.filter(original_start=occ_start).delete()
        else:
            return Response({'detail': 'occurrence_start é obrigatório.'}, status=400)

        limpar_cache_feed(interessados)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _exclude_occurrence(master, occ_start):
        """Acrescenta uma EXDATE ao mestre (idempotente)."""
        iso = occ_start.isoformat()
        excl = master.excluded_dates_list()
        if iso not in excl:
            excl.append(iso)
            master.excluded_dates = ','.join(excl)
            master.save(update_fields=['excluded_dates'])

    # ------------------------------------------------- Convite (Fatia D)
    @action(detail=True, methods=['post'])
    def responder(self, request, pk=None):
        """`POST events/{id}/responder/ {status: aceito|recusado}` — o convidado
        responde. Numa série, a resposta vale para a série (responde-se no
        mestre). Quem organizou fica sabendo pelo sino."""
        event = self.get_object()
        novo = request.data.get('status')
        if novo not in (EventAttendee.Status.ACEITO, EventAttendee.Status.RECUSADO):
            return Response({'status': 'Responda "aceito" ou "recusado".'}, status=400)
        convite = event.attendees.filter(user=request.user).first()
        if convite is None:
            return Response({'detail': 'Você não foi convidado para este evento.'}, status=400)
        if convite.status != novo:
            convite.status = novo
            convite.responded_at = timezone.now()
            convite.save(update_fields=['status', 'responded_at'])
            verbo = 'aceitou' if novo == EventAttendee.Status.ACEITO else 'recusou'
            criar_notificacao(
                user=event.user, tenant_id=event.tenant_id,
                titulo=f"{nome_de(request.user)} {verbo}: {event.title}"[:200],
                mensagem=f"Resposta ao convite para \"{event.title}\" ({_quando(event)}).",
                url=URL_EVENTO.format(id=event.pk),
            )
            limpar_cache_feed(acesso.interessados(event))
        return Response(self.get_serializer(event).data)

    # ------------------------------------------------------ Busca (Fatia E)
    @action(detail=False, methods=['get'])
    def busca(self, request):
        """`GET events/busca/?q=` — os eventos que a pessoa vê, pelo título,
        descrição ou local, sem acento; paginado (rola infinito na tela). Uma
        série aparece uma vez (o mestre), com a regra de repetição."""
        # `search` é o nome que o `SelectComBusca` manda; `q` fica para links.
        termo = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
        qs = self.get_queryset().filter(recurrence_master__isnull=True)
        if termo:
            qs = qs.filter(
                Q(title__unaccent__icontains=termo)
                | Q(description__unaccent__icontains=termo)
                | Q(location__unaccent__icontains=termo)
            )
        qs = qs.order_by('-start_time', '-id')
        paginador = CalendarioPageNumberPagination()
        pagina = paginador.paginate_queryset(qs, request, view=self)
        return paginador.get_paginated_response([
            {
                'id': ev.pk, 'title': ev.title, 'start_time': ev.start_time,
                'end_time': ev.end_time, 'all_day': ev.all_day, 'location': ev.location,
                'calendar': ev.calendar_id,
                'calendar_name': ev.calendar.name if ev.calendar_id else None,
                'color': ev.calendar.color if ev.calendar_id else None,
                'recurrence_rule': ev.recurrence_rule,
                'owner_name': nome_de(ev.user),
            }
            for ev in pagina
        ])

    # ----------------------------------------------- iCalendar (Fatia E)
    def _eventos_da_agenda(self, request):
        """O recorte do `.ics`: `?calendar=<id>` (uma agenda que se vê) ou
        `?calendar=meus` (a agenda pessoal implícita). Sem nada: tudo o que se vê."""
        alvo = request.query_params.get('calendar') or request.data.get('calendar') or ''
        qs = self.get_queryset()
        if alvo in ('', None):
            return qs, None
        if alvo == 'meus':
            return qs.filter(calendar__isnull=True, user=request.user), None
        calendar = acesso.agendas_visiveis(request.user).filter(pk=alvo).first()
        if calendar is None:
            raise PermissionDenied('Você não tem acesso a esta agenda.')
        return qs.filter(calendar=calendar), calendar

    @action(detail=False, methods=['get'], url_path='exportar-ics')
    def exportar_ics(self, request):
        qs, calendar = self._eventos_da_agenda(request)
        eventos = qs.select_related('recurrence_master').order_by('start_time')
        dominio = request.get_host().split(':')[0] or 'sgi'
        nome = (calendar.name if calendar else 'agenda').replace('"', '')
        resposta = HttpResponse(ics.escrever(eventos, dominio), content_type='text/calendar; charset=utf-8')
        resposta['Content-Disposition'] = f'attachment; filename="{nome}.ics"'
        return resposta

    @action(detail=False, methods=['post'], url_path='importar-ics')
    def importar_ics(self, request):
        """Importa um `.ics` na agenda escolhida. **Só cria, e é tudo ou nada**
        (regra do dono para toda importação): qualquer evento ilegível, ou um UID
        que já está nesta agenda, recusa o arquivo inteiro e diz o porquê."""
        arquivo = request.FILES.get('arquivo')
        if arquivo is None:
            return Response({'arquivo': 'Envie o arquivo .ics.'}, status=400)
        if arquivo.size > CALENDAR_ICS_TETO_KB * 1024:
            return Response(
                {'arquivo': f'O arquivo passa de {CALENDAR_ICS_TETO_KB // 1024} MB.'}, status=400,
            )
        _qs, calendar = self._eventos_da_agenda(request)
        try:
            texto = arquivo.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'arquivo': 'O arquivo não está em UTF-8.'}, status=400)
        try:
            lidos, erros = ics.ler(texto)
        except ics.IcsInvalido as exc:
            return Response({'arquivo': str(exc)}, status=400)
        if len(lidos) > CALENDAR_ICS_TETO_EVENTOS:
            erros.append(
                f'O arquivo tem {len(lidos)} eventos; o limite é {CALENDAR_ICS_TETO_EVENTOS}.'
            )

        series = [ev for ev in lidos if ev.recorrencia_de is None]
        excecoes = [ev for ev in lidos if ev.recorrencia_de is not None]
        uids = [ev.uid for ev in series if ev.uid]
        repetidos = {u for u in uids if uids.count(u) > 1}
        for u in sorted(repetidos):
            erros.append(f'O UID {u} aparece mais de uma vez no arquivo.')
        destino = CalendarEvent.objects.filter(calendar=calendar)
        if calendar is None:
            destino = destino.filter(user=request.user)
        ja = set(destino.filter(ical_uid__in=uids).values_list('ical_uid', flat=True))
        for u in sorted(ja):
            erros.append(f'O evento {u} já foi importado nesta agenda.')
        do_arquivo = set(uids)
        for ev in excecoes:
            if ev.uid not in do_arquivo:
                erros.append(f'Evento da linha {ev.linha}: exceção de uma série que não está no arquivo.')
        if not lidos and not erros:
            erros.append('O arquivo não tem nenhum evento.')
        if erros:
            return Response({'detail': 'Nada foi importado.', 'erros': erros}, status=400)

        tenant_id = getattr(request.user, 'tenant_id', None)
        with transaction.atomic():
            mestres = {}
            for ev in series:
                novo = CalendarEvent.objects.create(
                    tenant_id=tenant_id, user=request.user, calendar=calendar,
                    title=ev.titulo[:200], description=ev.descricao or None, location=ev.local,
                    start_time=ev.inicio, end_time=ev.fim, all_day=ev.dia_inteiro,
                    recurrence_rule=ev.regra, ical_uid=ev.uid,
                    excluded_dates=','.join(d.isoformat() for d in ev.excluidas),
                )
                if ev.uid:
                    mestres[ev.uid] = novo
            for ev in excecoes:
                mestre = mestres[ev.uid]
                CalendarEvent.objects.create(
                    tenant_id=tenant_id, user=request.user, calendar=calendar,
                    title=ev.titulo[:200], description=ev.descricao or None, location=ev.local,
                    start_time=ev.inicio, end_time=ev.fim, all_day=ev.dia_inteiro,
                    recurrence_master=mestre, original_start=ev.recorrencia_de,
                )
        limpar_cache_feed(
            {request.user.pk} if calendar is None else acesso.interessados_da_agenda(calendar)
        )
        return Response({'criados': len(lidos)}, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------------- Feed (list)
    def _crm_events(self, user, start_dt, end_dt):
        """Tarefas/reuniões do CRM do usuário, consultadas in-process — antes
        vinham por HTTP do microsserviço funcoeslead (absorvido na Fase 11.2)."""
        interacoes = Interaction.objects.filter(
            type__in=[Interaction.TypeChoices.TAREFA, Interaction.TypeChoices.REUNIAO],
            due_date__gte=start_dt,
            due_date__lte=end_dt,
        ).filter(
            Q(assigned_to_content_type=ContentType.objects.get_for_model(user),
              assigned_to_object_id=user.pk)
            | Q(lead__assigned_to=user)
        ).distinct()
        if getattr(user, 'tenant_id', None):
            interacoes = interacoes.filter(tenant_id=user.tenant_id)
        return [
            {
                'id': str(interacao.id),
                'title': interacao.subject,
                'start': interacao.due_date.isoformat(),
                'end': interacao.due_date.isoformat(),
                'allDay': True,
                'extendedProps': {
                    'type': interacao.type.lower(),
                    'notes': interacao.notes,
                    'completed': interacao.completed,
                },
            }
            for interacao in interacoes
        ]


    def _local_events(self, user, start_dt, end_dt):
        """Eventos próprios do feed: únicos + overrides concretos na janela e as
        ocorrências **virtuais** expandidas dos mestres recorrentes.

        "Próprios" desde a Fatia D são os que a pessoa **vê**: os dela, os das
        agendas que vê e os convites. Cada um diz a agenda (`calendarId`, `color`),
        se a pessoa pode editá-lo (`canEdit`) e, se é convite, a resposta dela."""
        base = (
            acesso.eventos_visiveis(user)
            .select_related('calendar', 'user')
            .prefetch_related('attendees')
        )
        agendas = set(acesso.agendas_visiveis(user).values_list('id', flat=True))
        events = []

        def comuns(ev):
            convite = next((a for a in ev.attendees.all() if a.user_id == user.pk), None)
            props = {
                'type': 'local',
                'calendarId': ev.calendar_id,
                'color': ev.calendar.color if ev.calendar_id else None,
                'canEdit': ev.user_id == user.pk or ev.calendar_id in agendas,
                'location': ev.location,
                'attendeesCount': len(ev.attendees.all()),
            }
            if ev.user_id != user.pk:
                props['ownerName'] = nome_de(ev.user)
            if convite is not None:
                props['myStatus'] = convite.status
            return props

        # Não-recorrentes (inclui overrides concretos) que caem na janela.
        concrete = base.filter(recurrence_rule='')
        if start_dt and end_dt:
            concrete = concrete.filter(start_time__lte=end_dt, end_time__gte=start_dt)
        for ev in concrete:
            props = comuns(ev)
            if ev.recurrence_master_id:
                props.update({
                    'masterId': ev.recurrence_master_id,
                    'occurrenceStart': ev.original_start.isoformat() if ev.original_start else None,
                    'isOverride': True,
                })
            events.append({
                'id': ev.id,
                'title': ev.title,
                'start': ev.start_time.isoformat(),
                'end': ev.end_time.isoformat(),
                'allDay': ev.all_day,
                'extendedProps': props,
            })

        # Mestres recorrentes → ocorrências virtuais dentro da janela.
        if start_dt and end_dt:
            masters = (base.exclude(recurrence_rule='')
                       .filter(start_time__lte=end_dt)
                       .prefetch_related('overrides'))
            for master in masters:
                props_mestre = comuns(master)
                for occ_start, occ_end in recurrence.expand_occurrences(master, start_dt, end_dt):
                    events.append({
                        # id composto: não colide com o pk usado no CRUD do mestre.
                        'id': f"occ-{master.id}-{occ_start.isoformat()}",
                        'title': master.title,
                        'start': occ_start.isoformat(),
                        'end': occ_end.isoformat(),
                        'allDay': master.all_day,
                        'extendedProps': {
                            **props_mestre,
                            'masterId': master.id,
                            'occurrenceStart': occ_start.isoformat(),
                            'isRecurring': True,
                            'recurrenceRule': master.recurrence_rule,
                            'eventType': master.event_type,
                            'description': master.description,
                        },
                    })
        return events

    # ------------------------------------------------------------- Feriados
    @staticmethod
    def _feriado_local(feriado):
        """Rótulo da localidade do feriado: país / estado / cidade."""
        if feriado.escopo == 'municipal':
            return f"{feriado.cidade}/{feriado.uf}" if feriado.cidade else (feriado.uf or 'Município')
        if feriado.escopo == 'estadual':
            return feriado.uf or 'Estado'
        return FERIADO_LOCAL_PAIS

    def _feriados(self, start_dt, end_dt, uf, ibge):
        """Feriados do período por escopo: nacional sempre; estadual se `uf`;
        municipal se `ibge`. Cada evento traz `scope` + `local` p/ cor e rótulo."""
        inicio = start_dt.date()
        fim = (end_dt or start_dt).date()
        filtro = Q(escopo='nacional')
        if uf:
            filtro |= Q(escopo='estadual', uf=uf)
        feriados = list(Feriado.objects.filter(filtro, data__gte=inicio, data__lte=fim))

        eventos = []
        for feriado in feriados:
            local = self._feriado_local(feriado)
            eventos.append(self._evento_feriado(
                feriado.nome, feriado.data, feriado.escopo, local,
                f"Feriado {feriado.get_escopo_display()} — {local}",
            ))
        if ibge:
            eventos.extend(self._feriados_municipais(inicio, fim, ibge))

        # Plano B: a TABELA não tem o nacional daqueles anos (sync ainda não
        # rodou, ou rodou sem cobrir o ano que se está olhando) → Nager.Date,
        # para o feed ser útil antes da 1ª sincronização.
        #
        # **A pergunta é sobre o ANO, não sobre a janela** (D147). A condição
        # anterior era "não vieram nacionais nesta janela", e isso confundia
        # *ausente* com *inexistente*: fevereiro, março, junho, julho e agosto
        # não TÊM feriado nacional, então abrir qualquer um desses meses com a
        # tabela cheia disparava a viagem à API externa — cinco dos doze meses
        # do ano, em toda navegação. Era esta a demora que o dono via na tela.
        if not self._tem_nacional_na_tabela(inicio, fim):
            eventos.extend(self._feriados_nager(start_dt, end_dt))
        return eventos

    @staticmethod
    def _evento_feriado(nome, dia, escopo, local, descricao, projetado=False):
        return {
            'title': f"{nome} · {local}",
            'start': dia.isoformat(),
            'allDay': True,
            'extendedProps': {
                'type': 'holiday',
                'scope': escopo,  # nacional | estadual | municipal
                'local': local,
                'description': descricao,
                'projetado': projetado,
            },
        }

    def _feriados_municipais(self, inicio, fim, ibge):
        """Os municipais da janela, publicados **ou projetados** (item 61).

        O dataset público só tem alguns anos de cada município (hoje 2025–2026);
        ler só a tabela deixava a agenda sem feriado municipal em 2027 em diante,
        enquanto o vencimento do boleto já os enxergava pela projeção. A agenda
        passa a perguntar ao mesmo `FeriadosMunicipais` — os dois nunca discordam
        sobre se o dia é feriado na cidade — e o projetado diz que é projeção.
        """
        municipio = (
            Feriado.objects.filter(escopo='municipal', ibge=ibge)
            .values('cidade', 'uf').first()
        )
        if not municipio:
            return []
        local = (
            f"{municipio['cidade']}/{municipio['uf']}" if municipio['cidade']
            else (municipio['uf'] or 'Município')
        )
        fonte = FeriadosMunicipais(ibge)
        eventos = []
        for ano in range(inicio.year, fim.year + 1):
            do_ano = fonte.do_ano(ano)
            projetado = ano in fonte.projetados
            for dia, nome in sorted(do_ano.items()):
                if not inicio <= dia <= fim:
                    continue
                descricao = f"Feriado Municipal — {local}"
                if projetado:
                    descricao += " (projetado pela data dos anos publicados — confirme na prefeitura)"
                eventos.append(self._evento_feriado(nome, dia, 'municipal', local, descricao, projetado))
        return eventos

    @staticmethod
    def _tem_nacional_na_tabela(inicio, fim) -> bool:
        """A tabela cobre os **anos** tocados pela janela? Uma consulta só.

        Cobre = tem ao menos um feriado nacional em cada ano tocado. Ano sem
        nenhum é ano não sincronizado: não existe calendário brasileiro sem 1º
        de janeiro.
        """
        anos = set(range(inicio.year, fim.year + 1))
        cobertos = set(
            Feriado.objects.filter(escopo='nacional', data__year__in=anos)
            .values_list('data__year', flat=True)
            .distinct()
        )
        return anos.issubset(cobertos)

    def _feriados_nager(self, start_dt, end_dt):
        eventos = []
        end_year = end_dt.year if end_dt is not None else start_dt.year
        for year in range(start_dt.year, end_year + 1):
            for holiday in get_holidays(year, 'BR'):
                eventos.append({
                    'title': f"{holiday.get('localName')} · {FERIADO_LOCAL_PAIS}",
                    'start': holiday.get('date'),
                    'allDay': True,
                    'extendedProps': {
                        'type': 'holiday', 'scope': 'nacional',
                        'local': FERIADO_LOCAL_PAIS,
                        'description': f"Feriado Nacional - {holiday.get('name')}",
                    },
                })
        return eventos

    def list(self, request, *args, **kwargs):
        user = request.user
        start_str = request.query_params.get('start', None)
        end_str = request.query_params.get('end', None)

        uf_q = (request.query_params.get('uf') or '').upper()
        ibge_q = request.query_params.get('ibge') or ''
        cache_key = f"calendar_events_{user.id}_{start_str}_{end_str}_{uf_q}_{ibge_q}"
        cached_events = cache.get(cache_key)
        if cached_events:
            return Response(cached_events)

        start_dt = recurrence.parse_iso(start_str)
        end_dt = recurrence.parse_iso(end_str)

        all_events = self._local_events(user, start_dt, end_dt)
        processed_titles_dates = {(e['title'], e['start']) for e in all_events}

        # --- Diário de obra (dia inteiro, somente leitura) ---
        diarios_queryset = DiarioObra.objects.filter(criado_por=user).select_related('obra')
        if start_dt is not None:
            diarios_queryset = diarios_queryset.filter(data__gte=start_dt.date())
        if end_dt is not None:
            diarios_queryset = diarios_queryset.filter(data__lte=end_dt.date())

        for diario in diarios_queryset:
            start_date_str = diario.data.isoformat()
            end_date_str = (diario.data + timedelta(days=1)).isoformat()
            titulo_diario = (
                f"Diário de Obra - {diario.obra.nome_obra}"
                if getattr(diario, 'obra', None) and getattr(diario.obra, 'nome_obra', None)
                else f"Diário de Obra #{diario.diario_obra_id}"
            )
            event_key = (titulo_diario, start_date_str)
            if event_key in processed_titles_dates:
                continue
            all_events.append({
                'title': titulo_diario,
                'start': start_date_str,
                'end': end_date_str,
                'allDay': True,
                'extendedProps': {
                    'type': 'diario_obra',
                    'diarioId': diario.diario_obra_id,
                    'obraId': getattr(diario.obra, 'obra_id', None) if getattr(diario, 'obra', None) else None,
                    'descricao': diario.descricao,
                }
            })
            processed_titles_dates.add(event_key)

        # --- Feriados por localidade (Fatia F): nacional sempre; estadual se a UF
        # foi informada; municipal se o IBGE foi informado. Cada um com escopo +
        # nome da localidade (país/estado/cidade) e cor própria no frontend. ---
        if start_dt is not None:
            uf = (request.query_params.get('uf') or '').upper()
            ibge = request.query_params.get('ibge') or ''
            for feriado in self._feriados(start_dt, end_dt, uf, ibge):
                event_tuple = (feriado['title'], feriado['start'])
                if event_tuple not in processed_titles_dates:
                    all_events.append(feriado)
                    processed_titles_dates.add(event_tuple)

        # --- Tarefas/reuniões do CRM (somente leitura) ---
        if start_dt is not None and end_dt is not None:
            for event in self._crm_events(user, start_dt, end_dt):
                event_tuple = (event['title'], event['start'].split('T')[0])
                if event_tuple not in processed_titles_dates:
                    all_events.append(event)
                    processed_titles_dates.add(event_tuple)

        cache.set(cache_key, all_events, timeout=30)
        return Response(all_events)


class LocalidadesObrasView(APIView):
    """`GET /api/calendar/localidades/` → obras do tenant com a localidade
    resolvida do endereço (`uf`/`ibge`/`cidade`), para o seletor de obra do
    calendário determinar estado+município. Tenant-scoped pela RLS armada na
    autenticação (o `Obra.objects.all()` só devolve as do tenant)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from obras.models import Obra
        resultado = []
        for obra in Obra.objects.all().only('obra_id', 'nome_obra', 'endereco'):
            loc = geo.resolver(endereco=obra.endereco) if obra.endereco else None
            resultado.append({
                'obra_id': obra.obra_id,
                'nome': obra.nome_obra,
                'uf': (loc or {}).get('uf', ''),
                'ibge': (loc or {}).get('ibge', ''),
                'cidade': (loc or {}).get('cidade', ''),
            })
        return Response({'obras': resultado})


class FeriadosStatusView(APIView):
    """`GET /api/calendar/feriados/status/` → carimbo da última sincronização de
    feriados. Restrito ao **superuser/dono da plataforma** — é a mensagem "sistema
    atualizado com os feriados". Demais usuários recebem 403 (o front oculta)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (autorizacao.supervisiona(user) or getattr(user, 'is_superuser', False)):
            return Response({'detail': 'Restrito ao superuser.'}, status=status.HTTP_403_FORBIDDEN)
        sync = FeriadoSync.objects.first()
        if sync is None:
            return Response({'atualizado_em': None, 'total': 0, 'anos': '', 'detalhes': {}})
        return Response({
            'atualizado_em': sync.atualizado_em.isoformat(),
            'total': sync.total,
            'anos': sync.anos,
            'detalhes': sync.detalhes,
        })


class CalendarViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """`/api/calendar/calendars/` — as agendas (Fatia D): as que a pessoa vê,
    com nome, cor, escopo e membros. Criar é de quem lança no calendário; mexer
    numa agenda existente é só do dono (ou do admin da empresa)."""

    serializer_class = CalendarSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "calendario.evento"
    pagination_class = None

    def get_queryset(self):
        return (
            acesso.agendas_visiveis(self.request.user)
            .select_related('owner')
            .prefetch_related('members__user')
        )

    def perform_create(self, serializer):
        membros = serializer.validated_data.pop('members', None)
        calendar = serializer.save(
            tenant_id=getattr(self.request.user, 'tenant_id', None), owner=self.request.user,
        )
        self._sync_members(calendar, membros or [])
        limpar_cache_feed(acesso.interessados_da_agenda(calendar))

    def perform_update(self, serializer):
        calendar = serializer.instance
        if not acesso.gere_agenda(self.request.user, calendar):
            raise PermissionDenied('Só quem criou a agenda pode alterá-la.')
        antes = acesso.interessados_da_agenda(calendar)
        membros = serializer.validated_data.pop('members', None)
        calendar = serializer.save(tenant_id=getattr(self.request.user, 'tenant_id', None))
        if membros is not None:
            self._sync_members(calendar, membros)
        depois = acesso.interessados_da_agenda(calendar)
        limpar_cache_feed(None if antes is None or depois is None else antes | depois)

    def perform_destroy(self, instance):
        if not acesso.gere_agenda(self.request.user, instance):
            raise PermissionDenied('Só quem criou a agenda pode apagá-la.')
        interessados = acesso.interessados_da_agenda(instance)
        instance.delete()  # cascata nos eventos da agenda
        limpar_cache_feed(interessados)

    def _sync_members(self, calendar, pessoas):
        """Membros só existem na agenda de equipe. Quem entra fica sabendo."""
        if calendar.scope != Calendar.Scope.EQUIPE:
            calendar.members.all().delete()
            return
        desejados = {p.pk: p for p in pessoas if p.pk != calendar.owner_id}
        atuais = set(calendar.members.values_list('user_id', flat=True))
        calendar.members.exclude(user_id__in=desejados.keys()).delete()
        entram = [p for uid, p in desejados.items() if uid not in atuais]
        CalendarMember.objects.bulk_create([
            CalendarMember(calendar=calendar, user=p, tenant_id=calendar.tenant_id) for p in entram
        ])
        for p in entram:
            criar_notificacao(
                user=p, tenant_id=calendar.tenant_id,
                titulo=f"Agenda compartilhada: {calendar.name}"[:200],
                mensagem=f"{nome_de(calendar.owner)} incluiu você na agenda de equipe "
                         f"\"{calendar.name}\". Os eventos dela já aparecem no seu calendário.",
                url="/app/calendario",
            )


class PessoasView(generics.ListAPIView):
    """`GET /api/calendar/pessoas/?search=` — quem da empresa pode ser convidado
    ou entrar numa agenda de equipe (Fatia D). Só o nome: é a lista do seletor,
    não o cadastro de usuários. Paginado e com busca no servidor — o
    `SelectComBusca` rola até o último."""

    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_permission = "calendario.evento.view"
    pagination_class = CalendarioPageNumberPagination
    filter_backends = [BuscaSemAcento]
    search_fields = ['first_name', 'last_name', 'username']

    def get_queryset(self):
        return Usuario.objects.filter(
            tenant_id=getattr(self.request.user, 'tenant_id', None), is_active=True,
        ).order_by('first_name', 'last_name', 'username', 'id')

    def list(self, request, *args, **kwargs):
        pagina = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([
            {'id': u.pk, 'nome': nome_de(u), 'username': u.username} for u in pagina
        ])
