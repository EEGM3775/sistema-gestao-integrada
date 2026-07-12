
from rest_framework import viewsets, permissions
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from .models import CalendarEvent
from .serializers import CalendarEventSerializer
from django.shortcuts import render


from rest_framework.response import Response
from datetime import datetime, timedelta
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.core.cache import cache

from modulocrm.models import Interaction
from modulodiario.models import DiarioObra
from .services import get_holidays

import logging

logger = logging.getLogger(__name__)

class CalendarEventViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    # Camada 2 (Fase 9.B/D5): agenda é "base" (sem entitlement de módulo), mas a
    # escrita exige permissão. GET→calendario.evento.view · escrita→.edit. Token
    # legado (sem `permissions`) cai no fallback (sem papel exigido → passa).
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "calendario.evento"

    def get_queryset(self):
        """Filtra eventos pelo usuário e pelo período solicitado (se houver)."""
        queryset = CalendarEvent.objects.filter(user=self.request.user)
        
        start_str = self.request.query_params.get('start', None)
        end_str = self.request.query_params.get('end', None)

        if start_str and end_str:
            queryset = queryset.filter(
                start_time__lte=end_str, end_time__gte=start_str
            )
        return queryset

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

    def _clear_cache(self, user_id):
        """Limpa o cache de calendário para um usuário específico."""
        try:
            cache_key_pattern = f"calendar_events_{user_id}_*"
            logger.info(f"Limpando cache com o padrão: {cache_key_pattern}")
            cache.delete_pattern(cache_key_pattern)
        except Exception as e:
            logger.error(f"Erro ao tentar limpar o cache do calendário: {e}")

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._clear_cache(self.request.user.id)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._clear_cache(self.request.user.id)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self._clear_cache(self.request.user.id)

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        start_str = request.query_params.get('start', None)
        end_str = request.query_params.get('end', None)

        # Constrói uma chave de cache única
        cache_key = f"calendar_events_{user_id}_{start_str}_{end_str}"
        cached_events = cache.get(cache_key)

        if cached_events:
            logger.info(f"Retornando eventos do cache para a chave: {cache_key}")
            return Response(cached_events)
        
        logger.info(f"Cache miss para a chave: {cache_key}. Buscando eventos...")

        # O resto da lógica permanece o mesmo...
        user_events = list(self.get_queryset().values('id', 'title', 'start_time', 'end_time', 'all_day'))
        user_events_formatted = [
            {
                'id': event['id'],
                'title': event['title'],
                'start': event['start_time'].isoformat(),
                'end': event['end_time'].isoformat(),
                'allDay': event['all_day'],
                'extendedProps': {'type': 'local'}
            } for event in user_events
        ]

        all_events = user_events_formatted
        processed_titles_dates = {(e['title'], e['start']) for e in all_events}

        def _parse_iso_datetime(value):
            if not value:
                return None
            parsed = parse_datetime(value)
            if parsed is not None:
                return parsed
            try:
                cleaned = value.replace('Z', '+00:00')
                return datetime.fromisoformat(cleaned)
            except ValueError:
                return None

        diarios_queryset = DiarioObra.objects.filter(criado_por=request.user).select_related('obra')

        start_dt = _parse_iso_datetime(start_str)
        end_dt = _parse_iso_datetime(end_str)

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

        if start_dt is not None:
            end_year = end_dt.year if end_dt is not None else start_dt.year
            for year in range(start_dt.year, end_year + 1):
                for holiday in get_holidays(year, 'BR'):
                    event_tuple = (holiday.get('localName'), holiday.get('date'))
                    if event_tuple not in processed_titles_dates:
                        all_events.append({
                            'title': holiday.get('localName'),
                            'start': holiday.get('date'),
                            'allDay': True,
                            'extendedProps': {
                                'type': 'holiday',
                                'description': f"Feriado Nacional - {holiday.get('name')}"
                            }
                        })
                        processed_titles_dates.add(event_tuple)

        if start_dt is not None and end_dt is not None:
            for event in self._crm_events(request.user, start_dt, end_dt):
                event_tuple = (event['title'], event['start'].split('T')[0])
                if event_tuple not in processed_titles_dates:
                    all_events.append(event)
                    processed_titles_dates.add(event_tuple)


        # Salva o resultado no cache por 0.5 minutos
        cache.set(cache_key, all_events, timeout=30)
        logger.info(f"Salvando eventos no cache com a chave: {cache_key}")

        return Response(all_events)
