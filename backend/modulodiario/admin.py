# backend/modulodiario/admin.py
from django.contrib import admin
from .models import DiarioObra, EntradaDiario, DocumentoDiario


class EntradaDiarioInline(admin.TabularInline):
    model = EntradaDiario
    extra = 0


class DocumentoDiarioInline(admin.TabularInline):
    model = DocumentoDiario
    extra = 0


@admin.register(DiarioObra)
class DiarioObraAdmin(admin.ModelAdmin):
    list_display = ('data', 'obra', 'criado_por', 'data_criacao')
    list_filter = ('obra', 'data')
    search_fields = ('descricao', 'condicoes_climaticas')
    date_hierarchy = 'data'
    inlines = [EntradaDiarioInline, DocumentoDiarioInline]


@admin.register(EntradaDiario)
class EntradaDiarioAdmin(admin.ModelAdmin):
    list_display = ('entrada_id', 'diario_obra', 'autor', 'origem', 'eh_ocorrencia', 'data_criacao')
    list_filter = ('origem', 'eh_ocorrencia', 'diario_obra__obra')
    search_fields = ('texto',)


@admin.register(DocumentoDiario)
class DocumentoDiarioAdmin(admin.ModelAdmin):
    list_display = ('diario_obra', 'arquivo', 'autor', 'origem', 'descricao', 'data_criacao')
    list_filter = ('origem', 'diario_obra__obra', 'diario_obra__data')
    search_fields = ('descricao',)
