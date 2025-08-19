# backend/funcoesia/admin.py
from django.contrib import admin
from .models import AnaliseImagemIA

@admin.register(AnaliseImagemIA)
class AnaliseImagemIAAdmin(admin.ModelAdmin):
    """
    Configura a exibição das Análises de IA na interface de administração.
    """
    list_display = ('documento', 'status', 'data_criacao', 'data_atualizacao')
    list_filter = ('status',)
    search_fields = ('documento__diario_obra__obra__nome',)
    readonly_fields = ('data_criacao', 'data_atualizacao')
