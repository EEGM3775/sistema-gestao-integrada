from django.contrib import admin

from .models import CentroCusto, FaixaPrecoOferta, OfertaFornecedor


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    list_display = ["centro_custo_id", "nome", "codigo", "tipo", "ativo", "tenant"]
    list_filter = ["tipo", "ativo"]
    search_fields = ["nome", "codigo"]


class FaixaPrecoOfertaInline(admin.TabularInline):
    model = FaixaPrecoOferta
    extra = 0


@admin.register(OfertaFornecedor)
class OfertaFornecedorAdmin(admin.ModelAdmin):
    list_display = ["oferta_id", "produto", "fornecedor", "preco_direto", "estoque_disponivel", "compra_direta", "visibilidade", "tenant"]
    list_filter = ["compra_direta", "visibilidade", "ativo"]
    search_fields = ["produto__descricao", "produto__codigo_interno"]
    raw_id_fields = ["produto", "fornecedor"]
    inlines = [FaixaPrecoOfertaInline]
