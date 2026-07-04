# backend/funcoescobrancas/admin.py
from django.contrib import admin

from .models import EventoWebhookAsaas


@admin.register(EventoWebhookAsaas)
class EventoWebhookAsaasAdmin(admin.ModelAdmin):
    list_display = ['evento_id', 'tipo', 'boleto', 'resultado', 'recebido_em', 'processado_em']
    list_filter = ['tipo']
    search_fields = ['evento_id', 'resultado']
    readonly_fields = ['evento_id', 'tipo', 'payload', 'recebido_em', 'processado_em']
    raw_id_fields = ['boleto']
    ordering = ['-recebido_em']
