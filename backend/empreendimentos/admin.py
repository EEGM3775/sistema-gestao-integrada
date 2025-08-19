# empreendimentos/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import (
    Empreendimento,
    ContaBancariaEmpreendimento,
    CustoEmpreendimento
)


class ContaBancariaEmpreendimentoInline(admin.TabularInline):
    model = ContaBancariaEmpreendimento
    extra = 0
    fields = (
        'codigo_banco',
        'agencia',
        'agencia_dv',
        'conta',
        'conta_dv',
        'tipo_conta',
        'is_principal'
    )


class CustoEmpreendimentoInline(admin.TabularInline):
    model = CustoEmpreendimento
    extra = 0
    fields = (
        'tipo_custo',
        'fornecedor',
        'produto_servico',
        'valor',
        'quantidade',
        'valor_total',
        'data_custo'
    )
    readonly_fields = ('valor_total',)


@admin.register(Empreendimento)
class EmpreendimentoAdmin(admin.ModelAdmin):
    list_display = (
        'empreendimento_id',
        'empreendimento',
        'razao_social',
        'cnpj',
        'status_empreendimento',
        'data_inicio_prevista',
        'data_fim_prevista',
        'orcamento_total',
        'data_criacao'
    )
    list_filter = (
        'status_empreendimento',
        'data_inicio_prevista',
        'data_fim_prevista',
        'data_criacao'
    )
    search_fields = (
        'empreendimento',
        'razao_social',
        'cnpj',
        'telefone',
        'endereco'
    )
    ordering = ('-data_criacao',)
    readonly_fields = ('empreendimento_id', 'data_criacao', 'data_atualizacao')
    
    fieldsets = (
        (_('Informações Básicas'), {
            'fields': (
                'empreendimento_id',
                'empreendimento',
                'razao_social',
                'cnpj'
            )
        }),
        (_('Contato e Localização'), {
            'fields': (
                'telefone',
                'endereco'
            )
        }),
        (_('Cronograma'), {
            'fields': (
                'data_inicio_prevista',
                'data_fim_prevista',
                'data_inicio_real',
                'data_fim_real'
            )
        }),
        (_('Financeiro'), {
            'fields': (
                'orcamento_total',
            )
        }),
        (_('Status e Descrição'), {
            'fields': (
                'status_empreendimento',
                'descricao'
            )
        }),
        (_('Controle'), {
            'fields': (
                'data_criacao',
                'data_atualizacao'
            )
        }),
    )
    
    inlines = [
        ContaBancariaEmpreendimentoInline,
        CustoEmpreendimentoInline
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related()


@admin.register(ContaBancariaEmpreendimento)
class ContaBancariaEmpreendimentoAdmin(admin.ModelAdmin):
    list_display = (
        'empreendimento',
        'codigo_banco',
        'agencia',
        'conta',
        'tipo_conta',
        'is_principal_display',
        'data_atualizacao'
    )
    list_filter = (
        'tipo_conta',
        'codigo_banco',
        'is_principal',
        'data_criacao'
    )
    search_fields = (
        'empreendimento__empreendimento',
        'codigo_banco',
        'agencia',
        'conta',
        'numero_agencia',
        'numero_conta'
    )
    ordering = ('empreendimento', '-is_principal', 'codigo_banco')
    readonly_fields = ('data_criacao', 'data_atualizacao')
    
    fieldsets = (
        (_('Empreendimento'), {
            'fields': (
                'empreendimento',
            )
        }),
        (_('Dados Bancários'), {
            'fields': (
                'codigo_banco',
                'agencia',
                'agencia_dv',
                'conta',
                'conta_dv',
                'tipo_conta'
            )
        }),
        (_('Informações Complementares'), {
            'fields': (
                'numero_agencia',
                'numero_conta',
                'codigo_cedente',
                'carteira',
                'codigo_pix'
            )
        }),
        (_('Configurações'), {
            'fields': (
                'is_principal',
                'observacoes'
            )
        }),
        (_('Controle'), {
            'fields': (
                'data_criacao',
                'data_atualizacao'
            )
        }),
    )

    def is_principal_display(self, obj):
        if obj.is_principal == 1:
            return format_html('<span style="color: green;">✓ Sim</span>')
        return format_html('<span style="color: red;">✗ Não</span>')
    is_principal_display.short_description = _('É Principal')


@admin.register(CustoEmpreendimento)
class CustoEmpreendimentoAdmin(admin.ModelAdmin):
    list_display = (
        'custo_id',
        'empreendimento',
        'tipo_custo',
        'fornecedor',
        'produto_servico',
        'valor',
        'quantidade',
        'valor_total',
        'data_custo',
        'nota_fiscal'
    )
    list_filter = (
        'tipo_custo',
        'data_custo',
        'data_emissao',
        'fornecedor',
        'empreendimento'
    )
    search_fields = (
        'empreendimento__empreendimento',
        'fornecedor__nome',
        'produto_servico__nome',
        'descricao',
        'chave_acesso',
        'nota_fiscal'
    )
    ordering = ('-data_custo', '-data_emissao')
    readonly_fields = ('custo_id', 'data_emissao', 'data_upload', 'valor_total_calculated')
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'custo_id',
                'empreendimento',
                'tipo_custo'
            )
        }),
        (_('Fornecedor e Produto/Serviço'), {
            'fields': (
                'fornecedor',
                'produto_servico',
                'descricao'
            )
        }),
        (_('Valores'), {
            'fields': (
                'valor',
                'quantidade',
                'valor_total',
                'valor_total_calculated'
            )
        }),
        (_('Datas'), {
            'fields': (
                'data_custo',
                'data_emissao'
            )
        }),
        (_('Nota Fiscal'), {
            'fields': (
                'nota_fiscal',
                'chave_acesso',
                'arquivo_xml',
                'data_upload'
            )
        }),
    )

    def valor_total_calculated(self, obj):
        if obj.valor and obj.quantidade:
            return obj.valor * obj.quantidade
        return '-'
    valor_total_calculated.short_description = _('Valor Total Calculado')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'empreendimento', 
            'fornecedor', 
            'produto_servico'
        )