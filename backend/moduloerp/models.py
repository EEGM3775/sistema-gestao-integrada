# backend/moduloerp/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _

# Dependencies from other modules in the project
from empreendimentos.models import Empreendimento
from clientes.models import Cliente
from fornecedores.models import Fornecedor
from obras.models import Obra
from nucleo.models import Usuario

# --- Base Models (Fatura and Transacao) ---

class Fatura(models.Model):
    class TipoFatura(models.TextChoices):
        A_PAGAR = 'PAGAR', _('A Pagar')
        A_RECEBER = 'RECEBER', _('A Receber')

    class StatusFatura(models.TextChoices):
        PENDENTE = 'PENDENTE', _('Pendente')
        PAGA = 'PAGA', _('Paga')
        ATRASADA = 'ATRASADA', _('Atrasada')
        CANCELADA = 'CANCELADA', _('Cancelada')

    fatura_id = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=10, choices=TipoFatura.choices)
    status = models.CharField(max_length=10, choices=StatusFatura.choices, default=StatusFatura.PENDENTE)
    descricao = models.TextField(_("Descrição"))
    valor = models.DecimalField(_("Valor"), max_digits=12, decimal_places=2)
    data_emissao = models.DateField(_("Data de Emissão"))
    data_vencimento = models.DateField(_("Data de Vencimento"))
    data_pagamento = models.DateField(_("Data de Pagamento/Recebimento"), null=True, blank=True)

    empreendimento = models.ForeignKey(Empreendimento, on_delete=models.PROTECT, related_name='faturas_erp', null=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='faturas_erp', null=True, blank=True)
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT, related_name='faturas_erp', null=True, blank=True)

    # Link to a received invoice (from a supplier)
    nota_fiscal_recebida = models.ForeignKey('NotaFiscal', on_delete=models.SET_NULL, related_name='faturas', null=True, blank=True, verbose_name=_("Nota Fiscal Recebida"))

    # Links to the specialized invoice models
    nota_fiscal_servico = models.OneToOneField('NotaFiscalServico', on_delete=models.SET_NULL, related_name='fatura_origem', null=True, blank=True)
    nota_fiscal_produto = models.OneToOneField('NotaFiscalProduto', on_delete=models.SET_NULL, related_name='fatura_origem', null=True, blank=True)

    class Meta:
        verbose_name = _("Fatura ERP")
        verbose_name_plural = _("Faturas ERP")
        ordering = ['data_vencimento']

    def __str__(self):
        return f"#{self.fatura_id} - {self.descricao}"

class Transacao(models.Model):
    """ Modelo que representa uma transação financeira (entrada ou saída) associada a uma fatura. """
    class TipoTransacao(models.TextChoices):
        ENTRADA = 'ENTRADA', _('Entrada')
        SAIDA = 'SAIDA', _('Saída')

    transacao_id = models.BigAutoField(primary_key=True, verbose_name="ID da Transação")
    fatura = models.ForeignKey(Fatura, on_delete=models.PROTECT, related_name='transacoes')
    empreendimento = models.ForeignKey(Empreendimento, on_delete=models.CASCADE, related_name='transacoes_erp_empreendimento', null=True, blank=True, verbose_name="Empreendimento")
    obra = models.ForeignKey(Obra, on_delete=models.SET_NULL, null=True, blank=True, related_name='transacoes_erp_obra')
    descricao = models.CharField(max_length=255, verbose_name="Descrição da Transação")
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor da Transação")
    tipo = models.CharField(max_length=7, choices=TipoTransacao.choices, verbose_name="Tipo da Transação")
    data_transacao = models.DateTimeField(auto_now_add=True, verbose_name="Data da Transação")
    meio_pagamento = models.CharField(max_length=50, help_text="Ex: PIX, Boleto, Cartão")
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='transacoes_erp_usuario', verbose_name="Usuário Responsável")

    class Meta:
        verbose_name = _("Transação ERP")
        verbose_name_plural = _("Transações ERP")
        ordering = ['-data_transacao']

    def __str__(self):
        return f"Transação de R$ {self.valor} para fatura #{self.fatura.fatura_id}"


# --- Specialized Nota Fiscal Models ---

class StatusNFE(models.TextChoices):
    AGUARDANDO = 'AGUARDANDO', _('Aguardando Emissão')
    PROCESSANDO = 'PROCESSANDO', _('Processando Emissão')
    EMITIDA = 'EMITIDA', _('Emitida com Sucesso')
    ERRO = 'ERRO', _('Erro na Emissão')
    CANCELADA = 'CANCELADA', _('Cancelada')

def nf_file_path(instance, filename):
    # Helper to organize file uploads
    year = instance.data_emissao.year if instance.data_emissao else "unknown_year"
    month = instance.data_emissao.month if instance.data_emissao else "unknown_month"
    return f'notas_fiscais/{instance._meta.model_name}/{year}/{month}/{filename}'

class NotaFiscalServico(models.Model):
    """ Model for Service Invoices (NFS-e). """
    id = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=StatusNFE.choices, default=StatusNFE.AGUARDANDO)
    nfe_io_id = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True, help_text="ID retornado pela API NFE.io")
    
    # Service data
    city_service_code = models.CharField(max_length=20, help_text="Código de Serviço do Município")
    description = models.TextField(help_text="Discriminação do Serviço")
    services_amount = models.DecimalField(max_digits=12, decimal_places=2)
    borrower_data = models.JSONField(help_text="Dados do tomador (cliente) enviados para a API")

    # Response data
    chave_acesso = models.CharField(_("Chave de Acesso"), max_length=44, null=True, blank=True)
    numero = models.CharField(_("Número da NF"), max_length=20, null=True, blank=True)
    data_emissao = models.DateTimeField(_("Data e Hora da Emissão"), null=True, blank=True)
    arquivo_pdf = models.FileField(_("Arquivo PDF"), upload_to=nf_file_path, null=True, blank=True)
    arquivo_xml = models.FileField(_("Arquivo XML"), upload_to=nf_file_path, null=True, blank=True)
    dados_retorno_api = models.JSONField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Nota Fiscal de Serviço (NFS-e)")
        verbose_name_plural = _("Notas Fiscais de Serviço (NFS-e)")

class NotaFiscalProduto(models.Model):
    """ Model for Product Invoices (NF-e). """
    id = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=StatusNFE.choices, default=StatusNFE.AGUARDANDO)
    nfe_io_id = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True, help_text="ID retornado pela API NFE.io")

    # Product data
    buyer_data = models.JSONField(help_text="Dados do comprador enviados para a API")
    items_data = models.JSONField(help_text="Lista de itens da nota enviada para a API")

    # Response data
    chave_acesso = models.CharField(_("Chave de Acesso"), max_length=44, null=True, blank=True)
    numero = models.CharField(_("Número da NF"), max_length=20, null=True, blank=True)
    data_emissao = models.DateTimeField(_("Data e Hora da Emissão"), null=True, blank=True)
    arquivo_pdf = models.FileField(_("Arquivo PDF"), upload_to=nf_file_path, null=True, blank=True)
    arquivo_xml = models.FileField(_("Arquivo XML"), upload_to=nf_file_path, null=True, blank=True)
    dados_retorno_api = models.JSONField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Nota Fiscal de Produto (NF-e)")
        verbose_name_plural = _("Notas Fiscais de Produto (NF-e)")

# --- Models from financeiro app ---

class NotaFiscal(models.Model):
    """
    Armazena as informações das notas fiscais recebidas de fornecedores,
    vinculadas a um empreendimento.
    """
    nota_fiscal_id = models.AutoField(primary_key=True)
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.CASCADE, related_name='notas_fiscais', verbose_name=_("Empreendimento"))
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.CASCADE, related_name='notas_fiscais_emitidas', verbose_name=_("Fornecedor"))
    numero_nota = models.CharField(max_length=50, unique=True, verbose_name=_("Número da Nota Fiscal"))
    chave_acesso = models.CharField(max_length=44, unique=True, help_text=_("Chave de Acesso de 44 dígitos da NF-e"))
    data_emissao = models.DateField(verbose_name=_("Data de Emissão"), help_text=_("Data em que a NF-e foi emitida"))
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor Total da NF-e"))
    arquivo_xml = models.FileField(upload_to='nfe_xmls/%Y/%m/', verbose_name=_("Arquivo XML da NF-e"))
    arquivo_pdf = models.FileField(upload_to='notas_fiscais/pdf/', null=True, blank=True, verbose_name=_("Arquivo PDF da NF-e (opcional)"))
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Upload"))

    class Meta:
        verbose_name = _("Nota Fiscal")
        verbose_name_plural = _("Notas Fiscais")
        ordering = ['-data_emissao']
        db_table = 'financeiro_notafiscal'

    def __str__(self):
        return f"NF {self.numero_nota} - {self.fornecedor.razao_social}"


class ContaPagar(models.Model):
    """
    Registra as contas a pagar da empresa, como pagamentos a fornecedores.
    """
    conta_pagar_id = models.AutoField(primary_key=True, verbose_name=_("ID da Conta a Pagar"))
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.CASCADE, related_name='contas_a_pagar', verbose_name=_("Fornecedor"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    nota_fiscal = models.ForeignKey(NotaFiscal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Nota Fiscal Associada"))
    descricao = models.TextField(verbose_name=_("Descrição da Conta"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor da Conta"))
    data_vencimento = models.DateField(verbose_name=_("Data de Vencimento"))
    pago = models.BooleanField(default=False, verbose_name=_("Pago"))
    data_pagamento = models.DateField(null=True, blank=True, verbose_name=_("Data de Pagamento"))

    class Meta:
        verbose_name = _("Conta a Pagar")
        verbose_name_plural = _("Contas a Pagar")
        ordering = ['data_vencimento']
        db_table = 'financeiro_contapagar'

    def __str__(self):
        return f"Pagar a {self.fornecedor.razao_social} - Vence em {self.data_vencimento}"


class ContaReceber(models.Model):
    """
    Registra as contas a receber da empresa, como pagamentos de clientes.
    """
    conta_receber_id = models.AutoField(primary_key=True, verbose_name=_("ID da Conta a Receber"))
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.CASCADE, related_name='contas_a_receber', verbose_name=_("Cliente"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    descricao = models.TextField(verbose_name=_("Descrição da Conta"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor da Conta"))
    data_vencimento = models.DateField(verbose_name=_("Data de Vencimento"))
    recebido = models.BooleanField(default=False, verbose_name=_("Recebido"))
    data_recebimento = models.DateField(null=True, blank=True, verbose_name=_("Data de Recebimento"))

    class Meta:
        verbose_name = _("Conta a Receber")
        verbose_name_plural = _("Contas a Receber")
        ordering = ['data_vencimento']
        db_table = 'financeiro_contareceber'

    def __str__(self):
        return f"Receber de {self.cliente.nome_completo} - Vence em {self.data_vencimento}"


class CobrancaCliente(models.Model):
    """
    Registra as cobranças (parcelas) geradas para os clientes.
    O boleto associado, se houver, é um objeto separado no modelo Boleto.
    """
    FORMA_PAGAMENTO_CHOICES = [
        ('boleto', _('Boleto Bancário')),
        ('pix', _('PIX')),
        ('transferencia', _('Transferência Bancária (TED/DOC)')),
        ('cartao_credito', _('Cartão de Crédito')),
        ('cartao_debito', _('Cartão de Débito')),
        ('dinheiro', _('Dinheiro')),
    ]

    STATUS_COBRANCA_CHOICES = [
        ('pendente', _('Pendente')),
        ('pago', _('Pago')),
        ('vencido', _('Vencido')),
        ('cancelado', _('Cancelado')),
    ]

    cobranca_cliente_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.CASCADE, related_name='cobrancas', verbose_name=_("Cliente"))
    contrato = models.ForeignKey('clientes.ContratoCliente', on_delete=models.RESTRICT, null=True, blank=True, verbose_name=_("Contrato Vinculado"))
    valor_nominal = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor Nominal"))
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor Pago"), null=True, blank=True)
    data_vencimento = models.DateField(verbose_name=_("Data de Vencimento"))
    data_pagamento = models.DateField(verbose_name=_("Data do Pagamento"), null=True, blank=True)
    forma_pagamento = models.CharField(max_length=50, choices=FORMA_PAGAMENTO_CHOICES, verbose_name=_("Forma de Pagamento"))
    parcela = models.IntegerField(verbose_name=_("Número da Parcela"), default=1)
    referencia_pagamento = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Referência do Pagamento"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    status = models.CharField(max_length=50, choices=STATUS_COBRANCA_CHOICES, default='pendente', verbose_name=_("Status da Cobrança"))

    def __str__(self):
        return f"Cobrança de {self.cliente.nome_completo} - Venc: {self.data_vencimento}"

    class Meta:
        verbose_name = _("Cobrança do Cliente")
        verbose_name_plural = _("Cobranças dos Clientes")
        ordering = ['data_vencimento']
        db_table = 'financeiro_cobrancacliente'


class Boleto(models.Model):
    """
    Representa um boleto bancário, que pode ser emitido para um cliente (via Conta a Receber)
    ou recebido de um fornecedor (via Conta a Pagar).
    """
    class StatusBoleto(models.TextChoices):
        AGUARDANDO = 'AGUARDANDO', _('Aguardando Emissão')
        EMITIDO = 'EMITIDO', _('Emitido')
        PAGO = 'PAGO', _('Pago')
        VENCIDO = 'VENCIDO', _('Vencido')
        CANCELADO = 'CANCELADO', _('Cancelado')
        ERRO = 'ERRO', _('Erro')

    boleto_id = models.AutoField(primary_key=True)
    
    conta_receber = models.ForeignKey(
        ContaReceber, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='boletos',
        verbose_name=_("Conta a Receber Associada")
    )
    conta_pagar = models.ForeignKey(
        ContaPagar, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='boletos',
        verbose_name=_("Conta a Pagar Associada")
    )

    status = models.CharField(max_length=20, choices=StatusBoleto.choices, default=StatusBoleto.AGUARDANDO)
    valor = models.DecimalField(_("Valor do Boleto"), max_digits=15, decimal_places=2)
    data_vencimento = models.DateField(_("Data de Vencimento"))
    data_emissao = models.DateTimeField(_("Data de Emissão"), auto_now_add=True)
    data_pagamento = models.DateTimeField(_("Data de Pagamento"), null=True, blank=True)

    # Dados específicos do boleto/gateway
    gateway_id = models.CharField(max_length=512, null=True, blank=True, db_index=True, verbose_name=_("ID no Gateway de Pagamento"))
    url_pdf = models.URLField(max_length=512, null=True, blank=True, verbose_name=_("Link do Boleto (PDF)"))
    linha_digitavel = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Linha Digitável"))

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Boleto")
        verbose_name_plural = _("Boletos")
        ordering = ['-data_vencimento']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(conta_receber__isnull=False, conta_pagar__isnull=True) |
                    models.Q(conta_receber__isnull=True, conta_pagar__isnull=False)
                ),
                name='apenas_uma_associacao_de_boleto'
            )
        ]

    def __str__(self):
        return f"Boleto {self.boleto_id} - R$ {self.valor} - Venc: {self.data_vencimento}"
