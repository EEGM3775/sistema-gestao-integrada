# backend/modulodiario/admin.py
from django.contrib import admin
from .models import DiarioObra, DocumentoDiario

class DocumentoDiarioInline(admin.TabularInline):
    """
    Permite a edição de documentos diretamente na página do Diário de Obra.
    """
    model = DocumentoDiario
    extra = 1  # Quantidade de campos extras para upload

@admin.register(DiarioObra)
class DiarioObraAdmin(admin.ModelAdmin):
    """
    Configura a exibição do Diário de Obra na interface de administração.
    """
    list_display = ('data', 'obra', 'usuario', 'data_criacao')
    list_filter = ('obra', 'data', 'usuario')
    search_fields = ('descricao', 'problemas_ocorrencias')
    date_hierarchy = 'data'
    inlines = [DocumentoDiarioInline]

@admin.register(DocumentoDiario)
class DocumentoDiarioAdmin(admin.ModelAdmin):
    """
    Configura a exibição dos Documentos do Diário na interface de administração.
    """
    list_display = ('diario_obra', 'arquivo', 'descricao', 'data_criacao')
    list_filter = ('diario_obra__obra', 'diario_obra__data')
    search_fields = ('descricao',)
