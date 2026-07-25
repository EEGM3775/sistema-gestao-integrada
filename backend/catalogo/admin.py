# backend/catalogo/admin.py
from django.contrib import admin

from .models import ComponenteComposicao, Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["item_id", "codigo_interno", "descricao", "unidade", "tipo", "estocavel", "ativo", "tenant"]
    list_filter = ["tipo", "estocavel", "compravel", "ativo"]
    search_fields = ["codigo_interno", "descricao", "gtin"]


@admin.register(ComponenteComposicao)
class ComponenteComposicaoAdmin(admin.ModelAdmin):
    list_display = ["componente_id", "item_pai", "item_filho", "coeficiente", "tenant"]
    raw_id_fields = ["item_pai", "item_filho"]
