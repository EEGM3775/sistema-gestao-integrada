from django.contrib import admin

from .models import ConcessaoEmpreendimento, ConcessaoEntidade, Entidade, ParticipacaoEmpreendimento


@admin.register(Entidade)
class EntidadeAdmin(admin.ModelAdmin):
    list_display = ["entidade_id", "nome", "documento", "papel", "externa", "ativa", "tenant"]
    list_filter = ["papel", "externa", "ativa"]
    search_fields = ["nome", "nome_fantasia", "documento"]


@admin.register(ParticipacaoEmpreendimento)
class ParticipacaoAdmin(admin.ModelAdmin):
    list_display = ["participacao_id", "empreendimento", "entidade", "cota", "administradora", "tenant"]


@admin.register(ConcessaoEntidade)
class ConcessaoEntidadeAdmin(admin.ModelAdmin):
    list_display = ["concessao_id", "usuario", "entidade", "incluir_filiais", "tenant"]


@admin.register(ConcessaoEmpreendimento)
class ConcessaoEmpreendimentoAdmin(admin.ModelAdmin):
    list_display = ["concessao_id", "usuario", "empreendimento", "tenant"]
