# rh/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import (
    Cargo,
    Funcionario,
    DadoMedicoFuncionario,
    ASOFuncionario,
    DocumentoFuncionario,
    DadoBancarioFuncionario,
    PagamentoFuncionario,
    FolhaPagamento
)


class DadoMedicoFuncionarioInline(admin.StackedInline):
    model = DadoMedicoFuncionario
    extra = 0
    fields = (
        ('numero_cartao_sus', 'tipo_sanguineo'),
        ('contato_emergencia_nome', 'contato_emergencia_telefone'),
        'alergias',
        'medicamentos',
        'historico_doencas',
        'observacoes_medicas'
    )


class ASOFuncionarioInline(admin.TabularInline):
    model = ASOFuncionario
    extra = 0
    fields = (
        'tipo_exame',
        'data_exame',
        'data_validade',
        'status',
        'arquivo'
    )


class DocumentoFuncionarioInline(admin.TabularInline):
    model = DocumentoFuncionario
    extra = 0
    fields = (
        'tipo_documento',
        'nome_documento',
        'arquivo',
        'data_upload'
    )
    readonly_fields = ('data_upload',)


class DadoBancarioFuncionarioInline(admin.TabularInline):
    model = DadoBancarioFuncionario
    extra = 0
    fields = (
        'codigo_banco',
        'agencia',
        'conta',
        'tipo_conta',
        'chave_pix'
    )


class PagamentoFuncionarioInline(admin.TabularInline):
    model = PagamentoFuncionario
    extra = 0
    fields = (
        'data_pagamento',
        'salario_base',
        'salario_liquido',
        'forma_pagamento',
        'parcela'
    )
    readonly_fields = ('salario_liquido',)


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = (
        'cargo_id',
        'nome_cargo',
        'departamento',
        'funcionarios_count'
    )
    list_filter = (
        'departamento',
    )
    search_fields = (
        'nome_cargo',
        'descricao',
        'departamento'
    )
    ordering = ('nome_cargo',)
    readonly_fields = ('cargo_id', 'funcionarios_count')
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'cargo_id',
                'nome_cargo',
                'departamento'
            )
        }),
        (_('Descrição'), {
            'fields': (
                'descricao',
                'funcionarios_count'
            )
        }),
    )

    def funcionarios_count(self, obj):
        count = obj.funcionario_set.count()
        if count > 0:
            return format_html('<span style="color: green;">{} funcionários</span>', count)
        return format_html('<span style="color: gray;">0 funcionários</span>')
    funcionarios_count.short_description = _('Funcionários no Cargo')


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        'funcionario_id',
        'nome_completo',
        'cargo',
        'cpf',
        'email_pessoal',
        'telefone_celular',
        'status_contrato',
        'data_admissao',
        'salario_base'
    )
    list_filter = (
        'status_contrato',
        'cargo',
        'genero',
        'estado_civil',
        'data_admissao',
        'data_demissao'
    )
    search_fields = (
        'nome_completo',
        'cpf',
        'rg',
        'email_pessoal',
        'telefone_celular',
        'pis_pasep',
        'numero_ctps'
    )
    ordering = ('nome_completo',)
    readonly_fields = ('funcionario_id', 'data_cadastro', 'data_atualizacao')
    
    fieldsets = (
        (_('Informações Pessoais'), {
            'fields': (
                'funcionario_id',
                'nome_completo',
                'cpf',
                'rg',
                'data_nascimento',
                'genero',
                'estado_civil'
            )
        }),
        (_('Contato'), {
            'fields': (
                'telefone_pessoal',
                'telefone_celular',
                'email_pessoal',
                'endereco_completo'
            )
        }),
        (_('Trabalho'), {
            'fields': (
                'usuario',
                'cargo',
                'empreendimento_vinculado',
                'data_admissao',
                'data_demissao',
                'salario_base',
                'status_contrato'
            )
        }),
        (_('Documentos Trabalhistas'), {
            'fields': (
                'numero_ctps',
                'serie_ctps',
                'pis_pasep',
                'carteira_trabalho',
                'carteira_trabalho_data_emissao',
                'carteira_trabalho_serie',
                'carteira_trabalho_numero',
                'carteira_trabalho_uf',
                'carteira_trabalho_data_validade',
                'carteira_trabalho_observacoes'
            )
        }),
        (_('Controle'), {
            'fields': (
                'data_cadastro',
                'data_atualizacao'
            )
        }),
    )
    
    inlines = [
        DadoMedicoFuncionarioInline,
        ASOFuncionarioInline,
        DocumentoFuncionarioInline,
        DadoBancarioFuncionarioInline,
        PagamentoFuncionarioInline
    ]


@admin.register(DadoMedicoFuncionario)
class DadoMedicoFuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        'funcionario',
        'numero_cartao_sus',
        'tipo_sanguineo'
    )
    list_filter = (
        'tipo_sanguineo',
    )
    search_fields = (
        'funcionario__nome_completo',
        'numero_cartao_sus',
        'contato_emergencia_nome',
        'contato_emergencia_telefone'
    )
    ordering = ('funcionario__nome_completo',)
    
    fieldsets = (
        (_('Funcionário'), {
            'fields': (
                'funcionario',
            )
        }),
        (_('Dados Médicos Básicos'), {
            'fields': (
                'numero_cartao_sus',
                'tipo_sanguineo',
                'alergias',
                'medicamentos',
                'historico_doencas'
            )
        }),
        (_('Contato de Emergência'), {
            'fields': (
                'contato_emergencia_nome',
                'contato_emergencia_telefone'
            )
        }),
        (_('Observações'), {
            'fields': (
                'observacoes_medicas',
            )
        }),
    )


@admin.register(DocumentoFuncionario)
class DocumentoFuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        'documento_id',
        'funcionario',
        'tipo_documento',
        'nome_documento',
        'data_upload'
    )
    list_filter = (
        'tipo_documento',
        'data_upload'
    )
    search_fields = (
        'funcionario__nome_completo',
        'nome_documento',
        'tipo_documento'
    )
    ordering = ('-data_upload',)
    readonly_fields = ('documento_id', 'data_upload')
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'documento_id',
                'funcionario',
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


@admin.register(ASOFuncionario)
class ASOFuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        'aso_id',
        'funcionario',
        'tipo_exame',
        'data_exame',
        'data_validade',
        'status'
    )
    list_filter = (
        'tipo_exame',
        'status',
        'data_exame'
    )
    search_fields = (
        'funcionario__nome_completo',
    )
    ordering = ('-data_exame',)
    readonly_fields = ('aso_id',)

    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'aso_id',
                'funcionario',
                'tipo_exame',
                'status'
            )
        }),
        (_('Exame'), {
            'fields': (
                'data_exame',
                'data_validade',
                'arquivo'
            )
        }),
        (_('Observações'), {
            'fields': (
                'observacoes',
            )
        }),
    )


@admin.register(DadoBancarioFuncionario)
class DadoBancarioFuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        'funcionario',
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
        'funcionario__nome_completo',
        'titular_nome',
        'titular_cpf_cnpj',
        'codigo_banco',
        'agencia',
        'conta',
        'chave_pix'
    )
    ordering = ('funcionario__nome_completo',)
    readonly_fields = ('data_atualizacao',)
    
    fieldsets = (
        (_('Funcionário'), {
            'fields': (
                'funcionario',
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


@admin.register(PagamentoFuncionario)
class PagamentoFuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        'funcionario',
        'data_pagamento',
        'salario_base',
        'descontos',
        'adicionais',
        'salario_liquido',
        'forma_pagamento',
        'parcela'
    )
    list_filter = (
        'forma_pagamento',
        'data_pagamento',
        'funcionario'
    )
    search_fields = (
        'funcionario__nome_completo',
        'referencia_pagamento',
        'observacoes'
    )
    ordering = ('-data_pagamento', 'funcionario__nome_completo')
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'funcionario',
                'data_pagamento',
                'parcela'
            )
        }),
        (_('Valores'), {
            'fields': (
                'salario_base',
                'descontos',
                'adicionais',
                'extras',
                'bonus',
                'salario_liquido'
            )
        }),
        (_('Detalhes dos Valores'), {
            'fields': (
                'tipos_descontos',
                'tipos_adicionais',
                'tipos_extras',
                'tipos_bonus'
            )
        }),
        (_('Pagamento'), {
            'fields': (
                'forma_pagamento',
                'referencia_pagamento',
                'link_holerite'
            )
        }),
        (_('Observações'), {
            'fields': (
                'observacoes',
            )
        }),
    )


@admin.register(FolhaPagamento)
class FolhaPagamentoAdmin(admin.ModelAdmin):
    list_display = (
        'folha_id',
        'funcionario',
        'mes_referencia',
        'salario_bruto',
        'total_descontos',
        'total_proventos',
        'salario_liquido',
        'data_pagamento'
    )
    list_filter = (
        'mes_referencia',
        'data_pagamento',
        'funcionario'
    )
    search_fields = (
        'funcionario__nome_completo',
    )
    ordering = ('-mes_referencia', 'funcionario__nome_completo')
    readonly_fields = ('folha_id',)
    
    fieldsets = (
        (_('Identificação'), {
            'fields': (
                'folha_id',
                'funcionario',
                'mes_referencia'
            )
        }),
        (_('Valores'), {
            'fields': (
                'salario_bruto',
                'total_descontos',
                'total_proventos',
                'salario_liquido'
            )
        }),
        (_('Pagamento'), {
            'fields': (
                'data_pagamento',
                'holerite'
            )
        }),
    )
