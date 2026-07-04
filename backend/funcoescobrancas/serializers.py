# backend/funcoescobrancas/serializers.py
from rest_framework import serializers

from .models import EventoWebhookAsaas


class EventoWebhookAsaasSerializer(serializers.ModelSerializer):
    """
    Somente leitura — alimenta a timeline de eventos do webhook Asaas exibida
    no detalhe do `Boleto` (UI, D.1.2): cada linha mostra o tipo do evento, o
    resultado do processamento (`dar_baixa`/`RevisaoBaixa`/idempotência) e os
    timestamps de recebimento/processamento.
    """
    class Meta:
        model = EventoWebhookAsaas
        fields = [
            'id', 'evento_id', 'tipo', 'payload', 'boleto',
            'recebido_em', 'processado_em', 'resultado',
        ]
        read_only_fields = fields
