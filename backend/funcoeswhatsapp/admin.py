# backend/funcoeswhatsapp/admin.py
from django.contrib import admin

from .models import CanalWhatsApp


@admin.register(CanalWhatsApp)
class CanalWhatsAppAdmin(admin.ModelAdmin):
    list_display = ('phone_number_id', 'nome_exibicao', 'tenant', 'ativo', 'data_atualizacao')
    list_filter = ('ativo',)
    search_fields = ('phone_number_id', 'nome_exibicao')
    # Segredos não aparecem na listagem; edição restrita ao admin de plataforma.
