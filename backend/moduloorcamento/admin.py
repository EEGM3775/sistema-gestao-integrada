# backend/moduloorcamento/admin.py
from django.contrib import admin

from .models import BaseReferencial, ComposicaoReferenciaItem, InsumoReferencia


@admin.register(BaseReferencial)
class BaseReferencialAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fonte", "uf", "mes_referencia", "regime_encargos",
                    "total_insumos", "total_composicoes", "ativa")
    list_filter = ("fonte", "uf", "regime_encargos", "ativa")
    search_fields = ("rotulo",)


@admin.register(InsumoReferencia)
class InsumoReferenciaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "unidade", "tipo", "custo_unitario", "base")
    list_filter = ("tipo", "base")
    search_fields = ("codigo", "descricao")


@admin.register(ComposicaoReferenciaItem)
class ComposicaoReferenciaItemAdmin(admin.ModelAdmin):
    list_display = ("composicao", "filho", "coeficiente")
    search_fields = ("composicao__codigo", "filho__codigo")
