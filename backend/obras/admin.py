# obras/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Obra, EtapaObra, DocumentoObra


class EtapaObraInline(admin.TabularInline):
    model = EtapaObra
    extra = 0
    fields = ('nome_etapa', 'ordem', 'status_etapa', 'percentual_conclusao', 'responsavel')


class DocumentoObraInline(admin.TabularInline):
    model = DocumentoObra
    extra = 0
    fields = ('tipo_documento', 'nome_documento', 'status_documento', 'versao')


@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):
    list_display = ['obra_id', 'nome_obra', 'empreendimento', 'endereco', 'status_obra', 'responsavel_tecnico', 'data_cadastro']
    list_filter = ['status_obra', 'data_inicio_prevista', 'data_fim_prevista', 'empreendimento']
    search_fields = ['nome_obra', 'endereco', 'descricao', 'empreendimento__nome_empreendimento']
    readonly_fields = ['obra_id', 'data_cadastro', 'data_atualizacao']
    ordering = ['nome_obra']
    
    fieldsets = (
        (_('Informações Básicas'), {
            'fields': ('obra_id', 'nome_obra', 'empreendimento', 'endereco')
        }),
        (_('Cronograma'), {
            'fields': ('data_inicio_prevista', 'data_fim_prevista', 'data_inicio_real', 'data_fim_real')
        }),
        (_('Financeiro'), {
            'fields': ('orcamento_previsto',)
        }),
        (_('Responsabilidade'), {
            'fields': ('responsavel_tecnico', 'status_obra')
        }),
        (_('Descrição'), {
            'fields': ('descricao',)
        }),
        (_('Controle'), {
            'fields': ('data_cadastro', 'data_atualizacao'),
            'classes': ('collapse',)
        })
    )
    
    inlines = [EtapaObraInline, DocumentoObraInline]


@admin.register(EtapaObra)
class EtapaObraAdmin(admin.ModelAdmin):
    list_display = ['etapa_id', 'obra', 'nome_etapa', 'ordem', 'status_etapa', 'percentual_conclusao', 'responsavel']
    list_filter = ['status_etapa', 'data_inicio_prevista', 'data_fim_prevista', 'responsavel']
    search_fields = ['obra__nome_obra', 'nome_etapa', 'descricao']
    readonly_fields = ['etapa_id', 'data_cadastro', 'data_atualizacao']
    ordering = ['obra', 'ordem']
    
    fieldsets = (
        (_('Identificação'), {
            'fields': ('etapa_id', 'obra', 'nome_etapa', 'ordem')
        }),
        (_('Cronograma'), {
            'fields': ('data_inicio_prevista', 'data_fim_prevista', 'data_inicio_real', 'data_fim_real')
        }),
        (_('Status e Progresso'), {
            'fields': ('status_etapa', 'percentual_conclusao')
        }),
        (_('Responsabilidade'), {
            'fields': ('responsavel', 'orcamento_previsto')
        }),
        (_('Descrição'), {
            'fields': ('descricao',)
        }),
        (_('Controle'), {
            'fields': ('data_cadastro', 'data_atualizacao'),
            'classes': ('collapse',)
        })
    )


@admin.register(DocumentoObra)
class DocumentoObraAdmin(admin.ModelAdmin):
    list_display = ['documento_id', 'obra', 'tipo_documento', 'nome_documento', 'versao', 'status_documento', 'data_emissao', 'responsavel']
    list_filter = ['tipo_documento', 'status_documento', 'data_emissao', 'data_aprovacao']
    search_fields = ['obra__nome_obra', 'nome_documento', 'descricao']
    readonly_fields = ['documento_id', 'data_cadastro', 'data_atualizacao']
    ordering = ['-data_cadastro']
    
    fieldsets = (
        (_('Identificação'), {
            'fields': ('documento_id', 'obra', 'tipo_documento', 'nome_documento', 'versao')
        }),
        (_('Arquivo'), {
            'fields': ('arquivo',)
        }),
        (_('Status e Datas'), {
            'fields': ('status_documento', 'data_emissao', 'data_aprovacao', 'aprovador')
        }),
        (_('Responsabilidade'), {
            'fields': ('responsavel',)
        }),
        (_('Descrição'), {
            'fields': ('descricao', 'observacoes')
        }),
        (_('Controle'), {
            'fields': ('data_cadastro', 'data_atualizacao'),
            'classes': ('collapse',)
        })
    )
