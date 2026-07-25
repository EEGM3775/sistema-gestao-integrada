# backend/modulosil/admin.py
from django.contrib import admin

from .models import (
    Devolucao,
    EmprestimoFerramenta,
    EntregaEPI,
    Ferramenta,
    Inventario,
    LocalEstoque,
    Lote,
    MovimentacaoEstoque,
    Requisicao,
    SaldoEstoque,
    Transferencia,
)


@admin.register(LocalEstoque)
class LocalEstoqueAdmin(admin.ModelAdmin):
    list_display = ["local_id", "nome", "tipo", "obra", "ativo", "tenant"]
    list_filter = ["tipo", "ativo"]
    search_fields = ["nome"]


@admin.register(SaldoEstoque)
class SaldoEstoqueAdmin(admin.ModelAdmin):
    list_display = ["saldo_id", "item", "local", "quantidade", "custo_medio", "reservado", "ponto_reposicao", "tenant"]
    raw_id_fields = ["item", "local"]


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = ["mov_id", "tipo", "item", "local", "quantidade", "custo_unitario", "criado_em", "tenant"]
    list_filter = ["tipo"]
    raw_id_fields = ["item", "local", "lote", "obra", "requisicao", "transferencia", "devolucao", "inventario"]


@admin.register(EntregaEPI)
class EntregaEPIAdmin(admin.ModelAdmin):
    list_display = ["entrega_epi_id", "item", "colaborador", "colaborador_nome", "ca_numero", "ca_validade", "status", "tenant"]
    list_filter = ["status"]
    raw_id_fields = ["item", "colaborador", "local", "obra"]


@admin.register(Ferramenta)
class FerramentaAdmin(admin.ModelAdmin):
    list_display = ["ferramenta_id", "nome", "patrimonio", "estado", "local", "proxima_calibracao", "tenant"]
    list_filter = ["estado", "calibravel"]
    search_fields = ["nome", "patrimonio"]


@admin.register(EmprestimoFerramenta)
class EmprestimoFerramentaAdmin(admin.ModelAdmin):
    list_display = ["emprestimo_id", "ferramenta", "colaborador", "colaborador_nome", "status", "data_emprestimo", "data_prevista_devolucao", "tenant"]
    list_filter = ["status"]
    raw_id_fields = ["ferramenta", "colaborador", "obra"]


admin.site.register([Lote, Requisicao, Transferencia, Devolucao, Inventario])
