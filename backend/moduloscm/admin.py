from django.contrib import admin

from .models import FaixaPrecoOferta, OfertaFornecedor




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
