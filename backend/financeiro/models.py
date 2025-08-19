# financeiro/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _

# A model Fornecedor ainda será criada, mas a referência já é incluída.
# from fornecedores.models import Fornecedor 

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

    def __str__(self):
        return f"Receber de {self.cliente.nome_completo} - Vence em {self.data_vencimento}"


class CobrancaCliente(models.Model):
    """
    Registra as cobranças (boletos, parcelas) geradas para os clientes.
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

    # CAMPOS ESPECÍFICOS PARA GATEWAY/BOLETO
    gateway_id = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("ID da Cobrança no Gateway"))
    boleto_url = models.URLField(max_length=512, null=True, blank=True, verbose_name=_("Link do Boleto"))
    boleto_linha_digitavel = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Linha Digitável"))
    status = models.CharField(max_length=50, choices=STATUS_COBRANCA_CHOICES, default='pendente', verbose_name=_("Status da Cobrança"))

    def __str__(self):
        return f"Cobrança de {self.cliente.nome_completo} - Venc: {self.data_vencimento}"

    class Meta:
        verbose_name = _("Cobrança do Cliente")
        verbose_name_plural = _("Cobranças dos Clientes")
        ordering = ['data_vencimento']

