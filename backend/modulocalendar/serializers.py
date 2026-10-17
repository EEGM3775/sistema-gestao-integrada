import re

from rest_framework import serializers
from payment.planos import CALENDAR_MAX_OFFSET_LEMBRETE_MIN, CALENDAR_TETO_CONVIDADOS

from nucleo.models import Usuario

from . import acesso
from .models import Calendar, CalendarEvent

# Teto do offset de um lembrete: 4 semanas em minutos (evita valores absurdos).
MAX_REMINDER_OFFSET = CALENDAR_MAX_OFFSET_LEMBRETE_MIN

COR_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def nome_de(usuario) -> str:
    """Como a pessoa aparece na agenda: o nome, ou o login se não há nome."""
    return (usuario.get_full_name() or usuario.username) if usuario else ''


def pessoas_da_empresa(request, ids):
    """Os `Usuario` ativos da empresa de quem pede, entre `ids`. Id de fora da
    empresa (ou inativo) é recusado — nunca se convida quem não está aqui."""
    ids = set(ids)
    if not ids:
        return []
    achadas = list(Usuario.objects.filter(
        pk__in=ids, tenant_id=getattr(request.user, 'tenant_id', None), is_active=True,
    ))
    if len(achadas) != len(ids):
        raise serializers.ValidationError('Há pessoa que não é desta empresa ou está inativa.')
    return achadas


class CalendarSerializer(serializers.ModelSerializer):
    """Agenda (Fatia D). `members` entra como lista de ids de usuário (só conta
    no escopo `equipe`); sai como `[{id, nome}]`."""

    members = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, write_only=True,
    )

    class Meta:
        model = Calendar
        fields = ['id', 'name', 'color', 'scope', 'owner', 'members', 'created_at']
        read_only_fields = ['owner', 'created_at']

    def validate_color(self, value):
        if not COR_HEX.match(value or ''):
            raise serializers.ValidationError('Cor no formato #rrggbb.')
        return value.lower()

    def validate_members(self, value):
        return pessoas_da_empresa(self.context['request'], value)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        data['members'] = [
            {'id': m.user_id, 'nome': nome_de(m.user)}
            for m in instance.members.select_related('user')
        ]
        data['owner_name'] = nome_de(instance.owner)
        data['can_manage'] = bool(request and acesso.gere_agenda(request.user, instance))
        return data


class CalendarEventSerializer(serializers.ModelSerializer):
    # Lembretes (Fatia C): lista de offsets em minutos antes do início (0 = na
    # hora). Escrita via este campo (write_only); a leitura é injetada em
    # `to_representation` a partir dos `EventReminder` relacionados. O ViewSet
    # sincroniza as linhas em `perform_create`/`perform_update`.
    reminders = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=MAX_REMINDER_OFFSET),
        required=False, write_only=True,
        help_text="Offsets em minutos antes do início (0 = na hora).",
    )
    # Convidados (Fatia D): ids de usuário da empresa. Ausente = não mexe;
    # presente (mesmo []) = substitui, preservando a resposta de quem fica.
    attendees = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, write_only=True,
        max_length=CALENDAR_TETO_CONVIDADOS,
        help_text="Ids dos convidados (usuários da empresa).",
    )

    class Meta:
        model = CalendarEvent
        fields = '__all__'
        # tenant e user são injetados pelo perform_create (Fase 8.2 / D3); o
        # cliente nunca envia dono — o evento pertence a quem o cria.
        # `recurrence_rule` é gravável (editor de repetição); os campos de
        # controle da recorrência (Fatia B) são geridos pelas actions do
        # ViewSet (editar/excluir este/todos/futuros), nunca pelo cliente.
        read_only_fields = [
            'tenant', 'user',
            'excluded_dates', 'recurrence_master', 'original_start', 'ical_uid',
        ]

    def validate_calendar(self, calendar):
        """Só se lança numa agenda que se vê."""
        request = self.context.get('request')
        if calendar is not None and request and not acesso.ve_agenda(request.user, calendar):
            raise serializers.ValidationError('Você não tem acesso a esta agenda.')
        return calendar

    def validate_attendees(self, value):
        return pessoas_da_empresa(self.context['request'], value)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        # Lembretes do evento (deduplicados e ordenados) para o diálogo de edição.
        data['reminders'] = sorted(r.offset_minutes for r in instance.reminders.all())
        data['attendees'] = [
            {'user': a.user_id, 'nome': nome_de(a.user), 'status': a.status}
            for a in instance.attendees.select_related('user')
        ]
        data['owner_name'] = nome_de(instance.user)
        if request is not None:
            me = request.user
            data['can_edit'] = acesso.pode_editar_evento(me, instance)
            data['my_status'] = next(
                (a['status'] for a in data['attendees'] if a['user'] == me.pk), None,
            )
        return data
