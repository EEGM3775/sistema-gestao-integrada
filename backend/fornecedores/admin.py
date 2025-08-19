# fornecedores/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Fornecedor, DadoBancarioFornecedor, ProdutoServicoFornecedor


class DadoBancarioFornecedorInline(admin.TabularInline):
    model = DadoBancarioFornecedor
    extra = 0
    fields = ('codigo_banco', 'agencia', 'conta', 'tipo_conta', 'chave_pix')


class ProdutoServicoFornecedorInline(admin.TabularInline):
    model = ProdutoServicoFornecedor
    extra = 0
    fields = ('nome_produto_servico', 'tipo_produto_servico', 'preco_unitario', 'unidade_medida')


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ['fornecedor_id', 'razao_social', 'cnpj', 'email', 'telefone', 'contato']
    list_filter = ['contato']
    search_fields = ['razao_social', 'cnpj', 'email', 'telefone']
    readonly_fields = ['fornecedor_id']
    ordering = ['razao_social']
    
    fieldsets = (
        (_('Informações Básicas'), {
            'fields': ('fornecedor_id', 'razao_social', 'cnpj')
        }),
        (_('Contato'), {
            'fields': ('contato', 'email', 'telefone')
        }),
    )
    
    inlines = [DadoBancarioFornecedorInline, ProdutoServicoFornecedorInline]


@admin.register(DadoBancarioFornecedor)
class DadoBancarioFornecedorAdmin(admin.ModelAdmin):
    list_display = ['fornecedor', 'codigo_banco', 'agencia', 'conta', 'tipo_conta', 'data_atualizacao']
    list_filter = ['tipo_conta', 'codigo_banco', 'data_atualizacao']
    search_fields = ['fornecedor__razao_social', 'codigo_banco', 'agencia', 'conta', 'chave_pix']
    readonly_fields = ['data_atualizacao']
    ordering = ['fornecedor__razao_social']
    
    fieldsets = (
        (_('Fornecedor'), {
            'fields': ('fornecedor',)
        }),
        (_('Dados Bancários'), {
            'fields': ('codigo_banco', 'agencia', 'agencia_dv', 'conta', 'conta_dv', 'tipo_conta')
        }),
        (_('Informações Adicionais'), {
            'fields': ('chave_pix', 'codigo_cedente', 'carteira', 'observacoes', 'data_atualizacao')
        })
    )


@admin.register(ProdutoServicoFornecedor)
class ProdutoServicoFornecedorAdmin(admin.ModelAdmin):
    list_display = ['fornecedor', 'nome_produto_servico', 'tipo_produto_servico', 'preco_unitario', 'unidade_medida', 'data_cotacao']
    list_filter = ['tipo_produto_servico', 'fornecedor', 'data_cotacao']
    search_fields = ['fornecedor__razao_social', 'nome_produto_servico', 'descricao']
    ordering = ['fornecedor__razao_social', 'tipo_produto_servico', 'nome_produto_servico']
    
    fieldsets = (
        (_('Identificação'), {
            'fields': ('fornecedor', 'nome_produto_servico', 'tipo_produto_servico')
        }),
        (_('Descrição'), {
            'fields': ('descricao',)
        }),
        (_('Preço e Medidas'), {
            'fields': ('preco_unitario', 'unidade_medida', 'data_cotacao')
        })
    )
