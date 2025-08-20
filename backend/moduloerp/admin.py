# backend/moduloerp/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Fatura, Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto
)

class BoletoInline(admin.TabularInline):
    model = Boleto
    extra = 0
    readonly_fields = ('status', 'valor', 'data_vencimento', 'data_pagamento', 'gateway_id', 'url_pdf', 'linha_digitavel')
    can_delete = True

@admin.register(Boleto)
class BoletoAdmin(admin.ModelAdmin):
    list_display = ('boleto_id', 'conta_receber', 'conta_pagar', 'status', 'valor', 'data_vencimento')
    list_filter = ('status', 'data_vencimento')
    search_fields = ('conta_receber__cliente__nome_completo', 'conta_pagar__fornecedor__razao_social', 'gateway_id')
    readonly_fields = ('boleto_id', 'criado_em', 'atualizado_em')
    raw_id_fields = ('conta_receber', 'conta_pagar')

    fieldsets = (
        (None, {
            'fields': ('boleto_id', 'status', 'valor', 'data_vencimento', 'data_pagamento')
        }),
        (_('Relacionamentos'), {
            'fields': ('conta_receber', 'conta_pagar')
        }),
        (_('Dados do Gateway'), {
            'fields': ('gateway_id', 'url_pdf', 'linha_digitavel'),
            'classes': ('collapse',)
        }),
        (_('Datas de Controle'), {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',)
        })
    )

@admin.register(Fatura)
class FaturaAdmin(admin.ModelAdmin):
    list_display = ('fatura_id', 'descricao', 'tipo', 'status', 'valor', 'data_vencimento', 'data_pagamento', 'cliente', 'fornecedor')
    list_filter = ('tipo', 'status', 'data_vencimento')
    search_fields = ('descricao', 'cliente__nome', 'fornecedor__nome_fantasia')
    raw_id_fields = ('cliente', 'fornecedor', 'empreendimento', 'nota_fiscal_servico', 'nota_fiscal_produto', 'nota_fiscal_recebida')

@admin.register(Transacao)
class TransacaoAdmin(admin.ModelAdmin):
    list_display = ('transacao_id', 'fatura', 'valor', 'tipo', 'data_transacao')
    list_filter = ('tipo', 'data_transacao')
    search_fields = ('fatura__descricao',)
    raw_id_fields = ('fatura', 'empreendimento', 'obra', 'usuario')

@admin.register(NotaFiscalServico)
class NotaFiscalServicoAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'nfe_io_id', 'numero', 'data_emissao')
    list_filter = ('status', 'data_emissao')
    search_fields = ('nfe_io_id', 'numero')

@admin.register(NotaFiscalProduto)
class NotaFiscalProdutoAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'nfe_io_id', 'numero', 'data_emissao')
    list_filter = ('status', 'data_emissao')
    search_fields = ('nfe_io_id', 'numero')

@admin.register(NotaFiscal)
class NotaFiscalAdmin(admin.ModelAdmin):
    list_display = ['nota_fiscal_id', 'numero_nota', 'fornecedor', 'empreendimento', 'data_emissao', 'valor_total']
    list_filter = ['empreendimento', 'data_emissao', 'fornecedor']
    search_fields = ['numero_nota', 'chave_acesso', 'fornecedor__razao_social']
    readonly_fields = ['nota_fiscal_id', 'data_upload']
    ordering = ['-data_emissao']
    
    fieldsets = (
        (_('Informações da Nota Fiscal'), {
            'fields': ('nota_fiscal_id', 'numero_nota', 'chave_acesso', 'data_emissao', 'valor_total')
        }),
        (_('Relacionamentos'), {
            'fields': ('empreendimento', 'fornecedor')
        }),
        (_('Arquivos'), {
            'fields': ('arquivo_xml', 'arquivo_pdf')
        }),
        (_('Metadados'), {
            'fields': ('data_upload',),
            'classes': ('collapse',)
        })
    )


@admin.register(ContaPagar)
class ContaPagarAdmin(admin.ModelAdmin):
    list_display = ['conta_pagar_id', 'fornecedor', 'descricao', 'valor', 'data_vencimento', 'pago']
    list_filter = ['pago', 'empreendimento', 'data_vencimento', 'fornecedor']
    search_fields = ['descricao', 'fornecedor__razao_social']
    readonly_fields = ['conta_pagar_id']
    ordering = ['data_vencimento']
    inlines = [BoletoInline]
    
    fieldsets = (
        (_('Informações da Conta'), {
            'fields': ('conta_pagar_id', 'descricao', 'valor', 'data_vencimento')
        }),
        (_('Relacionamentos'), {
            'fields': ('fornecedor', 'empreendimento', 'nota_fiscal')
        }),
        (_('Pagamento'), {
            'fields': ('pago', 'data_pagamento')
        })
    )


@admin.register(ContaReceber)
class ContaReceberAdmin(admin.ModelAdmin):
    list_display = ['conta_receber_id', 'cliente', 'descricao', 'valor', 'data_vencimento', 'recebido']
    list_filter = ['recebido', 'empreendimento', 'data_vencimento', 'cliente']
    search_fields = ['descricao', 'cliente__nome_completo']
    readonly_fields = ['conta_receber_id']
    ordering = ['data_vencimento']
    inlines = [BoletoInline]
    
    fieldsets = (
        (_('Informações da Conta'), {
            'fields': ('conta_receber_id', 'descricao', 'valor', 'data_vencimento')
        }),
        (_('Relacionamentos'), {
            'fields': ('cliente', 'empreendimento')
        }),
        (_('Recebimento'), {
            'fields': ('recebido', 'data_recebimento')
        })
    )


@admin.register(CobrancaCliente)
class CobrancaClienteAdmin(admin.ModelAdmin):
    list_display = ['cobranca_cliente_id', 'cliente', 'valor_nominal', 'data_vencimento', 'status', 'forma_pagamento']
    list_filter = ['status', 'forma_pagamento', 'data_vencimento', 'data_pagamento']
    search_fields = ['cliente__nome_completo', 'contrato__numero_contrato', 'referencia_pagamento']
    readonly_fields = ['cobranca_cliente_id']
    ordering = ['data_vencimento']
    
    fieldsets = (
        (_('Informações da Cobrança'), {
            'fields': ('cobranca_cliente_id', 'cliente', 'contrato', 'valor_nominal', 'forma_pagamento', 'parcela')
        }),
        (_('Datas'), {
            'fields': ('data_vencimento', 'data_pagamento')
        }),
        (_('Pagamento'), {
            'fields': ('valor_pago', 'status', 'referencia_pagamento')
        }),
        (_('Observações'), {
            'fields': ('observacoes',),
            'classes': ('collapse',)
        })
    )