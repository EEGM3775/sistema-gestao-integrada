# clientes/models.py
from django.db import models
from django.core.validators import RegexValidator
from nucleo.tenancy import TenantScopedModel
from django.utils.translation import gettext_lazy as _

# Reusable validator
cpf_cnpj_validator = RegexValidator(
    regex=r'^\d+$',
    message=_("O CPF/CNPJ deve conter apenas números.")
)

class Cliente(TenantScopedModel):
    """
    Armazena os dados cadastrais dos clientes.
    """
    ESTADO_CIVIL_CHOICES = [
        ('solteiro', _('Solteiro(a)')),
        ('casado', _('Casado(a)')),
        ('divorciado', _('Divorciado(a)')),
        ('viuvo', _('Viúvo(a)')),
        ('uniao_estavel', _('União Estável')),
    ]

    cliente_id = models.AutoField(primary_key=True)
    nome_completo = models.CharField(max_length=255, verbose_name=_("Nome Completo"))
    cpf_cnpj = models.CharField(max_length=18, blank=False, verbose_name=_("CPF/CNPJ"), validators=[cpf_cnpj_validator])
    email = models.EmailField(max_length=255, blank=False, verbose_name=_("E-mail"))
    telefone = models.CharField(max_length=20, blank=True, verbose_name=_("Telefone"))
    endereco = models.TextField(blank=True, verbose_name=_("Endereço"))
    numero_endereco = models.CharField(max_length=10, blank=True, verbose_name=_("Número do Endereço"))
    complemento_endereco = models.CharField(max_length=100, blank=True, verbose_name=_("Complemento do Endereço"))
    bairro = models.CharField(max_length=100, blank=True, verbose_name=_("Bairro"))
    cidade = models.CharField(max_length=100, blank=True, verbose_name=_("Cidade"))
    estado = models.CharField(max_length=2, blank=True, verbose_name=_("Estado"))
    cep = models.CharField(max_length=10, blank=True, verbose_name=_("CEP"))
    cidade_ibge = models.CharField(max_length=10, blank=True, verbose_name=_("Código IBGE da Cidade"))
    data_nascimento = models.DateField(verbose_name=_("Data de Nascimento"))
    estado_civil = models.CharField(max_length=50, choices=ESTADO_CIVIL_CHOICES, null=True, blank=True, verbose_name=_("Estado Civil"))
    profissao = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Profissão"))
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Cadastro"))
    id_cliente_gateway = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("ID do Cliente no Gateway de Pagamento"))

    def __str__(self):
        return self.nome_completo

    class Meta:
        verbose_name = _("Cliente")
        verbose_name_plural = _("Clientes")
        ordering = ['nome_completo']
        # Unicidade por-tenant (Fase 8.3): dois tenants podem ter o mesmo
        # CPF/CNPJ ou e-mail; dentro de um tenant, não.
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'cpf_cnpj'], name='cliente_cpf_cnpj_unico_por_tenant'),
            models.UniqueConstraint(fields=['tenant', 'email'], name='cliente_email_unico_por_tenant'),
        ]


class ClienteEmpreendimento(TenantScopedModel):
    """
    Vincula um cliente a um empreendimento específico, registrando a aquisição.
    """
    CONDICOES_PAGAMENTO_CHOICES = [
        ('a_vista', _('À Vista')),
        ('financiamento_bancario', _('Financiamento Bancário')),
        ('financiamento_direto', _('Financiamento Direto com a Construtora')),
        ('permuta', _('Permuta')),
        ('cartao', _('Cartão de Crédito/Débito')),
        ('outro', _('Outro')),
    ]

    cliente_empreendimento_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.RESTRICT, verbose_name=_("Cliente"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.RESTRICT, verbose_name=_("Empreendimento"))
    unidade_comprada = models.CharField(max_length=50, verbose_name=_("Unidade Comprada"))
    endereco_unidade = models.CharField(max_length=255, verbose_name=_("Endereço da Unidade"))
    data_compra = models.DateField(verbose_name=_("Data da Compra"))
    valor_compra = models.DecimalField(max_digits=20, decimal_places=2, verbose_name=_("Valor da Compra"))
    condicoes_pagamento = models.CharField(max_length=50, choices=CONDICOES_PAGAMENTO_CHOICES, verbose_name=_("Condições de Pagamento"))
    observacoes_compra = models.TextField(null=True, blank=True, verbose_name=_("Observações da Compra"))

    def __str__(self):
        return f"{self.cliente} - {self.empreendimento} (Unidade {self.unidade_comprada})"

    class Meta:
        verbose_name = _("Aquisição de Empreendimento")
        verbose_name_plural = _("Aquisições de Empreendimentos")
        unique_together = ('empreendimento', 'unidade_comprada')


class ContratoCliente(TenantScopedModel):
    """
    Mantém os contratos firmados com os clientes.
    """
    STATUS_CONTRATO_CHOICES = [
        ('ativo', _('Ativo')),
        ('inativo', _('Inativo')),
        ('cancelado', _('Cancelado')),
        ('concluido', _('Concluído')),
    ]

    contrato_cliente_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='contratos', verbose_name=_('Cliente'))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.RESTRICT, related_name='contratos_gerados', verbose_name=_('Empreendimento'))
    cliente_empreendimento = models.ForeignKey('ClienteEmpreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Aquisição Vinculada"))
    numero_contrato = models.CharField(max_length=50, verbose_name=_("Número do Contrato"))
    data_assinatura = models.DateField(verbose_name=_("Data de Assinatura"), null=True, blank=True)
    objeto_contrato = models.TextField(verbose_name=_("Objeto do Contrato"))
    arquivo_contrato = models.URLField(max_length=512, null=True, blank=True, verbose_name=_("Arquivo do Contrato"))
    status_contrato = models.CharField(max_length=50, choices=STATUS_CONTRATO_CHOICES, default='ativo', verbose_name=_("Status do Contrato"))
    responsavel = models.ForeignKey('rh.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Responsável"))
    vendedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Vendedor"))

    def __str__(self):
        return f"Contrato {self.numero_contrato} - {self.cliente.nome_completo}"

    class Meta:
        verbose_name = _("Contrato do Cliente")
        verbose_name_plural = _("Contratos dos Clientes")
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'numero_contrato'], name='contrato_numero_unico_por_tenant'),
        ]


class DocumentoCliente(TenantScopedModel):
    """
    Armazena documentos diversos dos clientes (RG, CPF, etc.).
    """
    TIPO_DOCUMENTO_CHOICES = [
        ('rg', _('RG')),
        ('cpf', _('CPF')),
        ('cnh', _('CNH')),
        ('comprovante_residencia', _('Comprovante de Residência')),
        ('certidao_casamento', _('Certidão de Casamento')),
        ('outros', _('Outros')),
    ]

    documento_cliente_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='documentos', verbose_name=_('Cliente'))
    tipo_documento = models.CharField(max_length=50, choices=TIPO_DOCUMENTO_CHOICES, verbose_name=_("Tipo de Documento"))
    nome_documento = models.CharField(max_length=255, verbose_name=_("Nome do Documento"), help_text=_("Especifique o documento se 'Outros' for selecionado."))
    arquivo = models.FileField(upload_to='documentos_clientes/', verbose_name=_("Arquivo"))
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Upload"))

    def __str__(self):
        return f"{self.get_tipo_documento_display()} de {self.cliente.nome_completo}"

    class Meta:
        verbose_name = _("Documento do Cliente")
        verbose_name_plural = _("Documentos dos Clientes")


class DadoBancarioCliente(TenantScopedModel):
    """
    Guarda as informações bancárias dos clientes para faturamento.
    Relação One-to-One com Cliente.
    """
    TIPO_CONTA_CHOICES = [
        ('corrente', _('Conta Corrente')),
        ('poupanca', _('Conta Poupança')),
        ('investimento', _('Conta de Investimento')),
        ('salario', _('Conta Salário')),
        ('outros', _('Outros')),
    ]

    cliente = models.ForeignKey(
        'Cliente',
        on_delete=models.CASCADE,
        related_name='dados_bancarios',
        verbose_name=_("Cliente")
    )
    codigo_banco = models.CharField(max_length=10, verbose_name=_("Código do Banco"))
    agencia = models.CharField(max_length=10, verbose_name=_("Agência"))
    agencia_dv = models.CharField(max_length=1, verbose_name=_("Dígito Verificador da Agência"), null=True, blank=True)
    conta = models.CharField(max_length=20, verbose_name=_("Conta"))
    conta_dv = models.CharField(max_length=1, verbose_name=_("Dígito Verificador da Conta"), null=True, blank=True)
    tipo_conta = models.CharField(max_length=50, choices=TIPO_CONTA_CHOICES, verbose_name=_("Tipo de Conta"))
    titular_nome = models.CharField(max_length=255, verbose_name=_("Nome do Titular"))
    titular_cpf_cnpj = models.CharField(max_length=18, verbose_name=_("CPF/CNPJ do Titular"), validators=[cpf_cnpj_validator])
    chave_pix = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Chave PIX"))
    codigo_cedente = models.CharField(max_length=25, verbose_name=_("Código Cedente/Convênio"), help_text=_("Também conhecido como Convênio ou Código do Beneficiário."), blank=True)
    carteira = models.CharField(max_length=25, verbose_name=_("Carteira"), help_text=_("Código da carteira de cobrança (fornecido pelo banco)."), blank=True)
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    def __str__(self):
        return f"Dados Bancários de {self.cliente.nome_completo}"

    class Meta:
        verbose_name = _("Dado Bancário do Cliente")
        verbose_name_plural = _("Dados Bancários dos Clientes")
