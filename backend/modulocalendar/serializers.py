
from rest_framework import serializers
from payment.planos import CALENDAR_MAX_OFFSET_LEMBRETE_MIN

from .models import CalendarEvent

# Teto do offset de um lembrete: 4 semanas em minutos (evita valores absurdos).
MAX_REMINDER_OFFSET = CALENDAR_MAX_OFFSET_LEMBRETE_MIN


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
            'excluded_dates', 'recurrence_master', 'original_start',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Lembretes do evento (deduplicados e ordenados) para o diálogo de edição.
        data['reminders'] = sorted(r.offset_minutes for r in instance.reminders.all())
        return data
