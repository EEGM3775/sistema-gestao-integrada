# clientes/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente
)


class DocumentoClienteInline(admin.TabularInline):
    model = DocumentoCliente
    extra = 0
    fields = (
        'tipo_documento',
        'nome_documento',
        'arquivo',
        'data_upload'
    )
    readonly_fields = ('data_upload',)


class DadoBancarioClienteInline(admin.TabularInline):
    model = DadoBancarioCliente
    extra = 0
    fields = (
        'codigo_banco',
        'agencia',
        'agencia_dv',
        'conta',
        'conta_dv',
        'tipo_conta',
        'chave_pix'
    )


class ClienteEmpreendimentoInline(admin.TabularInline):
    model = ClienteEmpreendimento
    extra = 1


class ContratoClienteInline(admin.TabularInline):
    model = ContratoCliente
    extra = 0
    fields = (
        'numero_contrato',
        'empreendimento',
        'data_assinatura',
        'status_contrato',
        'responsavel'
    )
    readonly_fields = ('numero_contrato',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        'cliente_id',
        'nome_completo',
        'cpf_cnpj',
        'email',
        'telefone',
        'estado_civil',
        'data_cadastro'
    )
    list_filter = (
        'estado_civil',
        'profissao',
        'data_cadastro',
        'data_nascimento'
    )
    search_fields = (
        'nome_completo',
        'cpf_cnpj',
        'email',
        'telefone'
    )
    ordering = ('nome_completo',)
    readonly_fields = ('cliente_id', 'data_cadastro')
    
    fieldsets = (
        (_('Informações Pessoais'), {
            'fields': (
                'cliente_id',
                'nome_completo',
                'cpf_cnpj',
                'data_nascimento',
                'estado_civil',
                'profissao'
            )
        }),
        (_('Contato'), {
            'fields': (
                'email',
                'telefone',
                'endereco'
            )
        }),
        (_('Sistema'), {
            'fields': (
                'id_cliente_gateway',
                'data_cadastro'
            )
        }),
    )
    
    inlines = [
        DocumentoClienteInline,
        DadoBancarioClienteInline,
        ClienteEmpreendimentoInline,
        ContratoClienteInline
    ]


@admin.register(ClienteEmpreendimento)
class ClienteEmpreendimentoAdmin(admin.ModelAdmin):
    list_display = (
        'cliente_empreendimento_id',
        'cliente',
        'empreendimento',
        'unidade_comprada',
        'data_compra',
        'valor_compra',
        'condicoes_pagamento'
    )
    list_filter = (
        'condicoes_pagamento',
        'data_compra',
        'empreendimento'
    )
    search_fields = (
        'cliente__nome_completo',
        'empreendimento__empreendimento',
        'unidade_comprada',
        'endereco_unidade'
    )
    ordering = ('-data_compra',)
    readonly_fields = ('cliente_empreendimento_id',)
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'cliente_empreendimento_id',
                'cliente',
                'empreendimento'
            )
        }),
        (_('Detalhes da Aquisição'), {
            'fields': (
                'unidade_comprada',
                'endereco_unidade',
                'data_compra',
                'valor_compra',
                'condicoes_pagamento'
            )
        }),
        (_('Observações'), {
            'fields': (
                'observacoes_compra',
            )
        }),
    )


@admin.register(ContratoCliente)
class ContratoClienteAdmin(admin.ModelAdmin):
    list_display = (
        'contrato_cliente_id',
        'numero_contrato',
        'cliente',
        'empreendimento',
        'data_assinatura',
        'status_contrato',
        'responsavel',
        'vendedor'
    )
    list_filter = (
        'status_contrato',
        'data_assinatura',
        'empreendimento',
        'responsavel',
        'vendedor'
    )
    search_fields = (
        'numero_contrato',
        'cliente__nome_completo',
        'empreendimento__empreendimento',
        'objeto_contrato'
    )
    ordering = ('-data_assinatura',)
    readonly_fields = ('contrato_cliente_id',)
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'contrato_cliente_id',
                'numero_contrato',
                'cliente',
                'empreendimento',
                'cliente_empreendimento'
            )
        }),
        (_('Detalhes do Contrato'), {
            'fields': (
                'data_assinatura',
                'objeto_contrato',
                'arquivo_contrato',
                'status_contrato',
                'responsavel',
                'vendedor'
            )
        }),
    )


@admin.register(DocumentoCliente)
class DocumentoClienteAdmin(admin.ModelAdmin):
    list_display = (
        'documento_cliente_id',
        'cliente',
        'tipo_documento',
        'nome_documento',
        'data_upload'
    )
    list_filter = (
        'tipo_documento',
        'data_upload'
    )
    search_fields = (
        'cliente__nome_completo',
        'nome_documento',
        'tipo_documento'
    )
    ordering = ('-data_upload',)
    readonly_fields = ('documento_cliente_id', 'data_upload')
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'documento_cliente_id',
                'cliente',
                'tipo_documento'
            )
        }),
        (_('Arquivo'), {
            'fields': (
                'nome_documento',
                'arquivo',
                'data_upload'
            )
        }),
    )


@admin.register(DadoBancarioCliente)
class DadoBancarioClienteAdmin(admin.ModelAdmin):
    list_display = (
        'cliente',
        'codigo_banco',
        'agencia',
        'conta',
        'tipo_conta',
        'titular_nome',
        'data_atualizacao'
    )
    list_filter = (
        'tipo_conta',
        'codigo_banco',
        'data_atualizacao'
    )
    search_fields = (
        'cliente__nome_completo',
        'titular_nome',
        'titular_cpf_cnpj',
        'codigo_banco',
        'agencia',
        'conta',
        'chave_pix'
    )
    ordering = ('cliente__nome_completo',)
    readonly_fields = ('data_atualizacao',)
    
    fieldsets = (
        (_('Cliente'), {
            'fields': (
                'cliente',
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
        (_('Titular'), {
            'fields': (
                'titular_nome',
                'titular_cpf_cnpj'
            )
        }),
        (_('Informações Adicionais'), {
            'fields': (
                'chave_pix',
                'codigo_cedente',
                'carteira',
                'observacoes',
                'data_atualizacao'
            )
        }),
    )