
from datetime import timedelta

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.core.cache import cache

from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from nucleo import geo
from modulocrm.models import Interaction
from modulodiario.models import DiarioObra

from .models import CalendarEvent, EventReminder, Feriado, FeriadoSync
from .serializers import CalendarEventSerializer
from .services import get_holidays
from . import recurrence

import logging

logger = logging.getLogger(__name__)

# Cores por escopo de feriado (Fatia F) — refletidas na legenda do frontend.
FERIADO_LOCAL_PAIS = "Brasil"


class CalendarEventViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    # Camada 2 (Fase 9.B/D5): agenda é "base" (sem entitlement de módulo), mas a
    # escrita exige permissão. GET→calendario.evento.view · escrita→.edit
    # (as actions de recorrência são POST → .edit, como o CRUD).
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "calendario.evento"

    def get_queryset(self):
        """Todos os eventos próprios do usuário. A janela do feed é aplicada em
        `list()` (recorrência exige tratar mestres fora da janela à parte)."""
        # prefetch dos lembretes: o retrieve (diálogo de edição) os serializa.
        return CalendarEvent.objects.filter(user=self.request.user).prefetch_related('reminders')

    # ------------------------------------------------------------------ CRUD
    def perform_create(self, serializer):
        # Injeta tenant (como o mixin) e o dono do evento numa única gravação —
        # o get_queryset filtra por `user`, então o dono não pode vir do cliente.
        reminders = serializer.validated_data.pop('reminders', None)
        event = serializer.save(
            tenant_id=getattr(self.request.user, 'tenant_id', None),
            user=self.request.user,
        )
        if reminders is not None:
            self._sync_reminders(event, reminders)
        self._clear_cache(self.request.user.id)

    def perform_update(self, serializer):
        reminders = serializer.validated_data.pop('reminders', None)
        # Reforça o tenant do dono (como o mixin) — impede mover o evento de tenant.
        event = serializer.save(tenant_id=getattr(self.request.user, 'tenant_id', None))
        # `reminders` ausente do payload = não mexe; presente (mesmo []) = substitui.
        if reminders is not None:
            self._sync_reminders(event, reminders)
        self._clear_cache(self.request.user.id)

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
    def _reminders_for(payload, master):
        """Offsets de lembrete a aplicar numa ocorrência/série **derivada** do
        mestre (override de 'só esta' ou novo mestre de 'futuras'): os do payload
        quando o cliente os envia; senão herda os do mestre — para que editar a
        recorrência não perca os lembretes silenciosamente (C1)."""
        if payload.get('reminders') is not None:
            return payload['reminders']
        return [r.offset_minutes for r in master.reminders.all()]

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self._clear_cache(self.request.user.id)

    def _clear_cache(self, user_id):
        try:
            cache.delete_pattern(f"calendar_events_{user_id}_*")
        except Exception as e:  # cache tolerante a queda do Redis
            logger.error(f"Erro ao limpar o cache do calendário: {e}")

    # --------------------------------------------- Actions de recorrência
    @action(detail=True, methods=['post'], url_path='update-recurrence')
    def update_recurrence(self, request, pk=None):
        """Edita uma série: `scope` = `this` (só esta ocorrência → override),
        `all` (a série toda, deslocando pela diferença desta ocorrência) ou
        `future` (desta em diante → divide a série)."""
        master = self.get_object()
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
                title=payload.get('title', master.title),
                description=payload.get('description', master.description),
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
            self._clear_cache(request.user.id)
            return Response(CalendarEventSerializer(override).data, status=status.HTTP_201_CREATED)

        if scope == 'all':
            if new_start and occ_start:
                delta = new_start - occ_start
                duration = (new_end - new_start) if (new_start and new_end) else base_duration
                master.start_time = master.start_time + delta
                master.end_time = master.start_time + duration
            for field in ('title', 'description', 'event_type', 'all_day', 'recurrence_rule'):
                if field in payload:
                    setattr(master, field, payload[field])
            master.save()
            # A série toda: substitui os lembretes do mestre quando enviados
            # (valem para todas as ocorrências virtuais); ausente = não mexe.
            if payload.get('reminders') is not None:
                self._sync_reminders(master, payload['reminders'])
            self._clear_cache(request.user.id)
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
                title=payload.get('title', master.title),
                description=payload.get('description', master.description),
                event_type=payload.get('event_type', master.event_type),
                all_day=payload.get('all_day', master.all_day),
                start_time=new_start or occ_start,
                end_time=new_end or (occ_start + duration),
                recurrence_rule=new_rule,
            )
            self._sync_reminders(new_master, reminders)
            self._clear_cache(request.user.id)
            return Response(CalendarEventSerializer(new_master).data, status=status.HTTP_201_CREATED)

        return Response({'detail': f'scope inválido: {scope}'}, status=400)

    @action(detail=True, methods=['post'], url_path='delete-recurrence')
    def delete_recurrence(self, request, pk=None):
        """Exclui de uma série: `scope` = `this` / `all` / `future`."""
        master = self.get_object()
        scope = request.data.get('scope', 'this')
        occ_start = recurrence.parse_iso(request.data.get('occurrence_start'))

        if scope == 'all':
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

        self._clear_cache(request.user.id)
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
        ocorrências **virtuais** expandidas dos mestres recorrentes."""
        base = CalendarEvent.objects.filter(user=user)
        events = []

        # Não-recorrentes (inclui overrides concretos) que caem na janela.
        concrete = base.filter(recurrence_rule='')
        if start_dt and end_dt:
            concrete = concrete.filter(start_time__lte=end_dt, end_time__gte=start_dt)
        for ev in concrete:
            props = {'type': 'local'}
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
                for occ_start, occ_end in recurrence.expand_occurrences(master, start_dt, end_dt):
                    events.append({
                        # id composto: não colide com o pk usado no CRUD do mestre.
                        'id': f"occ-{master.id}-{occ_start.isoformat()}",
                        'title': master.title,
                        'start': occ_start.isoformat(),
                        'end': occ_end.isoformat(),
                        'allDay': master.all_day,
                        'extendedProps': {
                            'type': 'local',
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
        if ibge:
            filtro |= Q(escopo='municipal', ibge=ibge)
        feriados = list(Feriado.objects.filter(filtro, data__gte=inicio, data__lte=fim))

        eventos = []
        for feriado in feriados:
            local = self._feriado_local(feriado)
            eventos.append({
                'title': f"{feriado.nome} · {local}",
                'start': feriado.data.isoformat(),
                'allDay': True,
                'extendedProps': {
                    'type': 'holiday',
                    'scope': feriado.escopo,  # nacional | estadual | municipal
                    'local': local,
                    'description': f"Feriado {feriado.get_escopo_display()} — {local}",
                },
            })

        # Fallback: sem nacional na tabela (sync ainda não rodou) → Nager.Date só
        # p/ o nacional, mantendo o feed útil antes da 1ª sincronização.
        if not any(f.escopo == 'nacional' for f in feriados):
            eventos.extend(self._feriados_nager(start_dt, end_dt))
        return eventos

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
        if not (getattr(user, 'is_platform_admin', False) or getattr(user, 'is_superuser', False)):
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
