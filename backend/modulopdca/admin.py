# backend/modulopdca/admin.py
"""Admin do PDCA — leitura de apoio à operação, não porta de edição.

O `/admin` é do supervisor da plataforma, e ele **não altera dado de empresa**
(docs/acesso-e-permissoes.md). Por isso o que se registra aqui é o mínimo que
ajuda a diagnosticar: ver a árvore de uma obra e o calendário que ela usa quando
alguém reclama que "o prazo saiu errado".
"""
from django.contrib import admin

from .models import (
    ApontamentoAvanco, CalendarioTrabalho, ExcecaoCalendario, LocalObra,
)


@admin.register(LocalObra)
class LocalObraAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "nivel", "obra", "profundidade", "ativo")
    list_filter = ("nivel", "ativo")
    search_fields = ("codigo", "nome")
    raw_id_fields = ("obra", "pai", "maps_local", "unidade", "tenant")


class ExcecaoInline(admin.TabularInline):
    model = ExcecaoCalendario
    extra = 0
    raw_id_fields = ("tenant",)


@admin.register(CalendarioTrabalho)
class CalendarioTrabalhoAdmin(admin.ModelAdmin):
    list_display = ("nome", "obra", "padrao", "horas_por_dia", "considera_feriados", "ativo")
    list_filter = ("padrao", "considera_feriados", "ativo")
    search_fields = ("nome",)
    raw_id_fields = ("obra", "tenant")
    inlines = [ExcecaoInline]


@admin.register(ApontamentoAvanco)
class ApontamentoAvancoAdmin(admin.ModelAdmin):
    """**Somente leitura, e aqui isso é regra de negócio, não cautela de admin.**

    O apontamento é append-only: o model recusa o segundo `save()`, e um
    formulário de edição no `/admin` só produziria um erro feio na cara do
    supervisor. Diagnosticar "o avanço da obra está errado" é ler a lista e ver
    qual lançamento não bate — corrigir é do dono do dado, pelo estorno.
    """

    list_display = ("data", "atividade", "percentual", "origem", "apontado_por", "estorna")
    list_filter = ("origem", "data")
    search_fields = ("observacao", "apontado_por")
    raw_id_fields = ("atividade", "local", "estorna", "tenant")
    date_hierarchy = "data"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
