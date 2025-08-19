# financeiro/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente

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
        (_('Gateway/Boleto'), {
            'fields': ('gateway_id', 'boleto_url', 'boleto_linha_digitavel'),
            'classes': ('collapse',)
        }),
        (_('Observações'), {
            'fields': ('observacoes',),
            'classes': ('collapse',)
        })
    )
