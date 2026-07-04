# backend/moduloerp/models.py
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from nucleo.tenancy import TenantScopedModel

# Dependencies from other modules in the project
from empreendimentos.models import Empreendimento
from clientes.models import Cliente
from fornecedores.models import Fornecedor
from obras.models import Obra
from nucleo.models import Usuario


class StatusConta(models.TextChoices):
    """
    Status do ciclo de vida de um título (ContaPagar/ContaReceber).

    'Atrasado' não é persistido — é derivado de `data_vencimento < hoje` com
    status ABERTO/PARCIAL (ver aging em ERPDashboardView), evitando o drift
    que existia entre `Fatura.status` (persistido) e a data de vencimento.
    """
    ABERTO = 'ABERTO', _('Aberto')
    PARCIAL = 'PARCIAL', _('Parcialmente quitado')
    QUITADO = 'QUITADO', _('Quitado')
    CANCELADO = 'CANCELADO', _('Cancelado')


class StatusRevisaoBaixa(models.TextChoices):
    PENDENTE = 'PENDENTE', _('Pendente de revisão')
    APROVADA = 'APROVADA', _('Aprovada — baixa aplicada')
    REJEITADA = 'REJEITADA', _('Rejeitada')


class BaixaRequerRevisao(Exception):
    """
    Levantada por `ContaPagar.dar_baixa`/`ContaReceber.dar_baixa` quando o
    título já está QUITADO/CANCELADO: a baixa NÃO é aplicada (evita inflar
    `valor_pago` além de `total_devido` e duplicar `Transacao`); em vez disso
    fica registrada como `RevisaoBaixa` pendente da avaliação do papel
    `financeiro`. Quem chama `dar_baixa` (view manual ou webhook do Asaas em
    D.1.2) deve capturar esta exceção e responder de acordo — ver
    docs/modulos/moduloerp.md §15.
    """
    def __init__(self, revisao):
        self.revisao = revisao
        super().__init__(
            f"Título já {revisao.conta.get_status_display()} — baixa encaminhada "
            f"para revisão do financeiro (RevisaoBaixa #{revisao.revisao_id})."
        )


# --- Base Model (Transacao) ---

class Transacao(TenantScopedModel):
    """ Modelo que representa uma transação financeira (entrada ou saída) do caixa do ERP. """
    class TipoTransacao(models.TextChoices):
        ENTRADA = 'ENTRADA', _('Entrada')
        SAIDA = 'SAIDA', _('Saída')

    transacao_id = models.BigAutoField(primary_key=True, verbose_name="ID da Transação")
    conta_pagar = models.ForeignKey('ContaPagar', on_delete=models.PROTECT, null=True, blank=True, related_name='transacoes', verbose_name=_("Conta a Pagar associada"))
    conta_receber = models.ForeignKey('ContaReceber', on_delete=models.PROTECT, null=True, blank=True, related_name='transacoes', verbose_name=_("Conta a Receber associada"))
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
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(conta_pagar__isnull=False, conta_receber__isnull=True) |
                    models.Q(conta_pagar__isnull=True, conta_receber__isnull=False)
                ),
                name='transacao_associada_a_uma_conta'
            )
        ]

    def __str__(self):
        titulo = self.conta_pagar_id or self.conta_receber_id
        return f"Transação de R$ {self.valor} — título #{titulo}"


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

class NotaFiscalServico(TenantScopedModel):
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

class NotaFiscalProduto(TenantScopedModel):
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

class NotaFiscal(TenantScopedModel):
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


class ContaPagar(TenantScopedModel):
    """
    Registra as contas a pagar da empresa, como pagamentos a fornecedores.
    """
    conta_pagar_id = models.AutoField(primary_key=True, verbose_name=_("ID da Conta a Pagar"))
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.CASCADE, related_name='contas_a_pagar', verbose_name=_("Fornecedor"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    nota_fiscal = models.ForeignKey(NotaFiscal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Nota Fiscal Associada"))
    descricao = models.TextField(verbose_name=_("Descrição da Conta"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor da Conta"))
    data_emissao = models.DateField(null=True, blank=True, verbose_name=_("Data de Emissão"))
    data_vencimento = models.DateField(verbose_name=_("Data de Vencimento"))
    data_agendamento = models.DateField(null=True, blank=True, verbose_name=_("Data de Agendamento do Pagamento"))

    status = models.CharField(max_length=10, choices=StatusConta.choices, default=StatusConta.ABERTO, verbose_name=_("Status"))
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Valor Pago (acumulado)"))
    juros = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Juros"))
    multa = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Multa"))
    desconto = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Desconto"))
    data_pagamento = models.DateField(null=True, blank=True, verbose_name=_("Data da Última Baixa"))

    class Meta:
        verbose_name = _("Conta a Pagar")
        verbose_name_plural = _("Contas a Pagar")
        ordering = ['data_vencimento']
        db_table = 'financeiro_contapagar'

    def __str__(self):
        return f"Pagar a {self.fornecedor.razao_social} - Vence em {self.data_vencimento}"

    @property
    def total_devido(self):
        return self.valor + self.juros + self.multa - self.desconto

    @property
    def saldo_aberto(self):
        return self.total_devido - self.valor_pago

    def dar_baixa(self, *, valor, data, juros=Decimal('0'), multa=Decimal('0'), desconto=Decimal('0'),
                  meio_pagamento='', usuario=None, origem='manual', forcar=False):
        """
        Aplica uma baixa total ou parcial e registra a `Transacao` correspondente.

        Único caminho de baixa do título — usado tanto pela ação manual da UI
        (`dar_baixa` do ViewSet) quanto pela baixa automática futura via webhook
        (Asaas, D.1.2: chamar com `origem='asaas'`), garantindo que
        `valor_pago`/`status`/`Transacao` fiquem sempre consistentes
        independentemente de quem disparou a baixa.

        Título já QUITADO/CANCELADO: em vez de aplicar (o que infla `valor_pago`
        além de `total_devido` e duplica `Transacao`), registra uma
        `RevisaoBaixa` pendente e levanta `BaixaRequerRevisao` — quem chamou
        decide o que responder. `forcar=True` (usado só por `RevisaoBaixa.aprovar`)
        ignora o guard e aplica a baixa represada.
        """
        if self.status in (StatusConta.QUITADO, StatusConta.CANCELADO) and not forcar:
            revisao = RevisaoBaixa.objects.create(
                tenant=self.tenant,
                conta_pagar=self,
                valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
                meio_pagamento=meio_pagamento, origem=origem,
                motivo=f"Título já estava {self.get_status_display()} quando esta baixa foi recebida.",
                solicitado_por=usuario,
            )
            raise BaixaRequerRevisao(revisao)

        self.valor_pago += valor
        self.juros += juros
        self.multa += multa
        self.desconto += desconto
        self.status = (
            StatusConta.QUITADO if self.valor_pago >= self.total_devido
            else StatusConta.PARCIAL if self.valor_pago > 0
            else StatusConta.ABERTO
        )
        self.data_pagamento = data
        self.save()

        Transacao.objects.create(
            tenant=self.tenant,
            conta_pagar=self,
            empreendimento=self.empreendimento,
            descricao=f"Baixa de pagamento ({origem}) — {self.descricao[:200]}",
            valor=valor + juros + multa - desconto,
            tipo=Transacao.TipoTransacao.SAIDA,
            meio_pagamento=meio_pagamento or 'Não informado',
            usuario=usuario,
        )
        return self


class ContaReceber(TenantScopedModel):
    """
    Registra as contas a receber da empresa, como pagamentos de clientes.
    """
    conta_receber_id = models.AutoField(primary_key=True, verbose_name=_("ID da Conta a Receber"))
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.CASCADE, related_name='contas_a_receber', verbose_name=_("Cliente"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    nota_fiscal_recebida = models.ForeignKey(NotaFiscal, on_delete=models.SET_NULL, null=True, blank=True, related_name='contas_a_receber', verbose_name=_("Nota Fiscal Associada"))
    nota_fiscal_servico = models.OneToOneField('NotaFiscalServico', on_delete=models.SET_NULL, related_name='conta_receber_origem', null=True, blank=True, verbose_name=_("NFS-e emitida"))
    nota_fiscal_produto = models.OneToOneField('NotaFiscalProduto', on_delete=models.SET_NULL, related_name='conta_receber_origem', null=True, blank=True, verbose_name=_("NF-e emitida"))
    descricao = models.TextField(verbose_name=_("Descrição da Conta"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor da Conta"))
    data_emissao = models.DateField(null=True, blank=True, verbose_name=_("Data de Emissão"))
    data_vencimento = models.DateField(verbose_name=_("Data de Vencimento"))
    data_agendamento = models.DateField(null=True, blank=True, verbose_name=_("Data de Agendamento da Cobrança"))

    status = models.CharField(max_length=10, choices=StatusConta.choices, default=StatusConta.ABERTO, verbose_name=_("Status"))
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Valor Recebido (acumulado)"))
    juros = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Juros"))
    multa = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Multa"))
    desconto = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Desconto"))
    data_recebimento = models.DateField(null=True, blank=True, verbose_name=_("Data da Última Baixa"))

    class Meta:
        verbose_name = _("Conta a Receber")
        verbose_name_plural = _("Contas a Receber")
        ordering = ['data_vencimento']
        db_table = 'financeiro_contareceber'

    def __str__(self):
        return f"Receber de {self.cliente.nome_completo} - Vence em {self.data_vencimento}"

    @property
    def total_devido(self):
        return self.valor + self.juros + self.multa - self.desconto

    @property
    def saldo_aberto(self):
        return self.total_devido - self.valor_pago

    def dar_baixa(self, *, valor, data, juros=Decimal('0'), multa=Decimal('0'), desconto=Decimal('0'),
                  meio_pagamento='', usuario=None, origem='manual', forcar=False):
        """
        Aplica uma baixa total ou parcial e registra a `Transacao` correspondente.

        Espelha `ContaPagar.dar_baixa` — único caminho de baixa do título, seja
        a ação manual da UI ou a baixa automática futura via webhook (Asaas,
        D.1.2: chamar com `origem='asaas'`). Mesmo guard de título já
        QUITADO/CANCELADO: registra `RevisaoBaixa` e levanta `BaixaRequerRevisao`
        em vez de aplicar — ver docstring de `ContaPagar.dar_baixa`.
        """
        if self.status in (StatusConta.QUITADO, StatusConta.CANCELADO) and not forcar:
            revisao = RevisaoBaixa.objects.create(
                tenant=self.tenant,
                conta_receber=self,
                valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
                meio_pagamento=meio_pagamento, origem=origem,
                motivo=f"Título já estava {self.get_status_display()} quando esta baixa foi recebida.",
                solicitado_por=usuario,
            )
            raise BaixaRequerRevisao(revisao)

        self.valor_pago += valor
        self.juros += juros
        self.multa += multa
        self.desconto += desconto
        self.status = (
            StatusConta.QUITADO if self.valor_pago >= self.total_devido
            else StatusConta.PARCIAL if self.valor_pago > 0
            else StatusConta.ABERTO
        )
        self.data_recebimento = data
        self.save()

        Transacao.objects.create(
            tenant=self.tenant,
            conta_receber=self,
            empreendimento=self.empreendimento,
            descricao=f"Baixa de recebimento ({origem}) — {self.descricao[:200]}",
            valor=valor + juros + multa - desconto,
            tipo=Transacao.TipoTransacao.ENTRADA,
            meio_pagamento=meio_pagamento or 'Não informado',
            usuario=usuario,
        )
        return self


class RevisaoBaixa(TenantScopedModel):
    """
    Fila de revisão do papel `financeiro` para baixas tentadas em títulos já
    QUITADOS/CANCELADOS — criada por `ContaPagar.dar_baixa`/`ContaReceber.dar_baixa`
    quando o guard detecta a situação (em vez de aplicar e corromper `valor_pago`/
    `Transacao`). Decisão registrada em 07/06/2026 — ver docs/modulos/moduloerp.md §15.
    """
    revisao_id = models.AutoField(primary_key=True, verbose_name=_("ID da Revisão"))
    conta_pagar = models.ForeignKey(ContaPagar, on_delete=models.CASCADE, null=True, blank=True, related_name='revisoes_baixa', verbose_name=_("Conta a Pagar"))
    conta_receber = models.ForeignKey(ContaReceber, on_delete=models.CASCADE, null=True, blank=True, related_name='revisoes_baixa', verbose_name=_("Conta a Receber"))

    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor da baixa tentada"))
    data = models.DateField(verbose_name=_("Data da baixa tentada"))
    juros = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Juros"))
    multa = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Multa"))
    desconto = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Desconto"))
    meio_pagamento = models.CharField(max_length=50, blank=True, verbose_name=_("Meio de pagamento"))
    origem = models.CharField(max_length=20, default='manual', verbose_name=_("Origem da tentativa"), help_text=_("'manual' (UI/API) ou 'asaas' (webhook, D.1.2)"))
    motivo = models.CharField(max_length=255, verbose_name=_("Motivo do encaminhamento"))

    status = models.CharField(max_length=10, choices=StatusRevisaoBaixa.choices, default=StatusRevisaoBaixa.PENDENTE, verbose_name=_("Status da revisão"))
    solicitado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='revisoes_baixa_solicitadas', verbose_name=_("Solicitado por"))
    solicitado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Solicitado em"))
    revisado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='revisoes_baixa_avaliadas', verbose_name=_("Avaliado por"))
    revisado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Avaliado em"))
    observacao_revisor = models.TextField(blank=True, verbose_name=_("Observação do avaliador"))

    class Meta:
        verbose_name = _("Revisão de Baixa")
        verbose_name_plural = _("Revisões de Baixa")
        ordering = ['-solicitado_em']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(conta_pagar__isnull=False, conta_receber__isnull=True) |
                    models.Q(conta_pagar__isnull=True, conta_receber__isnull=False)
                ),
                name='revisao_baixa_associada_a_uma_conta'
            )
        ]

    def __str__(self):
        return f"Revisão de baixa #{self.revisao_id} — {self.get_status_display()} ({self.conta})"

    @property
    def conta(self):
        return self.conta_pagar or self.conta_receber

    def aprovar(self, *, usuario, observacao=''):
        """ Aplica a baixa represada (bypassa o guard via `forcar=True`) e marca a revisão como aprovada. """
        self.conta.dar_baixa(
            valor=self.valor, data=self.data, juros=self.juros, multa=self.multa, desconto=self.desconto,
            meio_pagamento=self.meio_pagamento, usuario=self.solicitado_por, origem=self.origem, forcar=True,
        )
        self.status = StatusRevisaoBaixa.APROVADA
        self.revisado_por = usuario
        self.revisado_em = timezone.now()
        self.observacao_revisor = observacao
        self.save()
        return self

    def rejeitar(self, *, usuario, observacao=''):
        """ Marca a revisão como rejeitada — a baixa tentada não é aplicada ao título. """
        self.status = StatusRevisaoBaixa.REJEITADA
        self.revisado_por = usuario
        self.revisado_em = timezone.now()
        self.observacao_revisor = observacao
        self.save()
        return self


class CentroCusto(TenantScopedModel):
    """
    Centro de custo para rateio de contas a pagar/receber (D.1.1 adianta um
    recorte mínimo de D.1.4 "Financeiro por obra" — aqui só o necessário para
    o rateio nascer com o formato definitivo: nome + vínculo opcional a uma
    obra/empreendimento).
    """
    centro_custo_id = models.AutoField(primary_key=True, verbose_name=_("ID do Centro de Custo"))
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    codigo = models.CharField(max_length=30, blank=True, verbose_name=_("Código"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, related_name='centros_custo', verbose_name=_("Empreendimento/Obra"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Centro de Custo")
        verbose_name_plural = _("Centros de Custo")
        ordering = ['nome']

    def __str__(self):
        return f"{self.codigo} — {self.nome}" if self.codigo else self.nome


class RateioContaPagar(TenantScopedModel):
    """ Divisão do valor de uma ContaPagar entre N centros de custo. """
    rateio_id = models.AutoField(primary_key=True)
    conta_pagar = models.ForeignKey(ContaPagar, on_delete=models.CASCADE, related_name='rateios', verbose_name=_("Conta a Pagar"))
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, related_name='rateios_conta_pagar', verbose_name=_("Centro de Custo"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor rateado"))

    class Meta:
        verbose_name = _("Rateio de Conta a Pagar")
        verbose_name_plural = _("Rateios de Contas a Pagar")
        constraints = [models.UniqueConstraint(fields=['conta_pagar', 'centro_custo'], name='rateio_pagar_unico_por_centro')]

    def __str__(self):
        return f"Conta #{self.conta_pagar_id} → {self.centro_custo.nome}: R$ {self.valor}"


class RateioContaReceber(TenantScopedModel):
    """ Divisão do valor de uma ContaReceber entre N centros de custo. """
    rateio_id = models.AutoField(primary_key=True)
    conta_receber = models.ForeignKey(ContaReceber, on_delete=models.CASCADE, related_name='rateios', verbose_name=_("Conta a Receber"))
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, related_name='rateios_conta_receber', verbose_name=_("Centro de Custo"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor rateado"))

    class Meta:
        verbose_name = _("Rateio de Conta a Receber")
        verbose_name_plural = _("Rateios de Contas a Receber")
        constraints = [models.UniqueConstraint(fields=['conta_receber', 'centro_custo'], name='rateio_receber_unico_por_centro')]

    def __str__(self):
        return f"Conta #{self.conta_receber_id} → {self.centro_custo.nome}: R$ {self.valor}"


class LoteRemessa(TenantScopedModel):
    """
    Registro de um lote de pagamento a ser enviado ao banco ("remessa bancária").

    Nesta entrega (D.1.1) o lote só agrupa títulos e controla o status de envio —
    a geração do arquivo CNAB propriamente dita (240/400 + layout por banco) fica
    para uma sub-fase dedicada (ver docs/modulos/moduloerp.md §13/§15): gerar o
    `arquivo_cnab` aqui exigiria layouts posicionais específicos por instituição,
    o que mereceria seu próprio ciclo de implementação e testes.
    """
    class StatusLote(models.TextChoices):
        GERADO = 'GERADO', _('Gerado')
        ENVIADO = 'ENVIADO', _('Enviado ao banco')
        PROCESSADO = 'PROCESSADO', _('Processado')
        CANCELADO = 'CANCELADO', _('Cancelado')

    lote_id = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=StatusLote.choices, default=StatusLote.GERADO, verbose_name=_("Status"))
    banco = models.CharField(max_length=100, blank=True, verbose_name=_("Banco de destino"))
    data_geracao = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Geração"))
    data_envio = models.DateTimeField(null=True, blank=True, verbose_name=_("Data de Envio"))
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Valor Total do Lote"))
    observacoes = models.TextField(blank=True, verbose_name=_("Observações"))
    contas_pagar = models.ManyToManyField(ContaPagar, related_name='lotes_remessa', blank=True, verbose_name=_("Contas a Pagar incluídas"))

    class Meta:
        verbose_name = _("Lote de Remessa")
        verbose_name_plural = _("Lotes de Remessa")
        ordering = ['-data_geracao']

    def __str__(self):
        return f"Lote #{self.lote_id} — {self.get_status_display()}"


class CobrancaCliente(TenantScopedModel):
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


class Boleto(TenantScopedModel):
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
