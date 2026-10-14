# backend/moduloerp/models.py
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from nucleo.tenancy import Excluivel, TenantScopedModel


def _data_baixa_para_datetime(data):
    """
    Converte a data da baixa (um `date`) no `datetime` de competência gravado na
    `Transacao` (L7). Antes a `data_transacao` era `auto_now_add` — o ledger
    registrava o instante do processamento, não a data real do pagamento; a baixa
    do webhook Asaas (que pode chegar dias depois) caía no mês errado do fluxo de
    caixa. Agora a competência acompanha a data informada na baixa.
    """
    dt = data if isinstance(data, datetime) else datetime.combine(data, time.min)
    if settings.USE_TZ and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt

# Dependencies from other modules in the project
from empreendimentos.models import Empreendimento
from clientes.models import Cliente
from fornecedores.models import Fornecedor
from obras.models import Obra
from nucleo.models import Usuario


class NaturezaIntercompany(models.TextChoices):
    """O que um título entre entidades do grupo é na DRE (docs/modulos/entidades.md §3).

    Vazio = título comum (com cliente ou fornecedor). Com natureza, a contraparte
    é a entidade e o título não gera boleto nem nota.
    """
    NENHUMA = '', _('—')
    REPASSE_DESPESA = 'repasse_despesa', _('Repasse de despesa')
    REPASSE_RECEITA = 'repasse_receita', _('Repasse de receita')


def _entidade_fk(related_name='+'):
    return models.ForeignKey(
        'entidades.Entidade', on_delete=models.PROTECT, related_name=related_name,
        verbose_name=_("Entidade"),
    )


def _contraparte_fk():
    return models.ForeignKey(
        'entidades.Entidade', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
        verbose_name=_("Entidade contraparte (intercompany)"),
    )


def _natureza_field():
    return models.CharField(
        max_length=20, choices=NaturezaIntercompany.choices, blank=True, default='',
        verbose_name=_("Natureza intercompany"),
    )


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
    # O caixa de quem: a entidade do título baixado (docs/modulos/entidades.md §2).
    entidade = _entidade_fk()
    conta_pagar = models.ForeignKey('ContaPagar', on_delete=models.PROTECT, null=True, blank=True, related_name='transacoes', verbose_name=_("Conta a Pagar associada"))
    conta_receber = models.ForeignKey('ContaReceber', on_delete=models.PROTECT, null=True, blank=True, related_name='transacoes', verbose_name=_("Conta a Receber associada"))
    empreendimento = models.ForeignKey(Empreendimento, on_delete=models.CASCADE, related_name='transacoes_erp_empreendimento', null=True, blank=True, verbose_name="Empreendimento")
    obra = models.ForeignKey(Obra, on_delete=models.SET_NULL, null=True, blank=True, related_name='transacoes_erp_obra')
    descricao = models.CharField(max_length=255, verbose_name="Descrição da Transação")
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor da Transação")
    tipo = models.CharField(max_length=7, choices=TipoTransacao.choices, verbose_name="Tipo da Transação")
    # L7: data de COMPETÊNCIA (data real do pagamento). Deixou de ser
    # `auto_now_add` para que a baixa — sobretudo a do webhook Asaas — lance a
    # transação no mês em que o pagamento ocorreu, não no de processamento.
    data_transacao = models.DateTimeField(default=timezone.now, verbose_name="Data da Transação (competência)")
    # Carimbo imutável de quando a linha foi registrada no sistema (auditoria):
    # preserva o "quando lançamos" que o `auto_now_add` de `data_transacao` dava.
    data_lancamento = models.DateTimeField(auto_now_add=True, verbose_name="Data de Lançamento no Sistema")
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

    def save(self, *args, **kwargs):
        if not self.entidade_id:
            conta = self.conta_pagar or self.conta_receber
            self.entidade_id = conta.entidade_id
        super().save(*args, **kwargs)


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
    # A emitente: a entidade dona do título (docs/modulos/entidades.md §5).
    entidade = models.ForeignKey('entidades.Entidade', on_delete=models.PROTECT, null=True, blank=True, related_name='+', verbose_name=_("Entidade emitente"))
    status = models.CharField(max_length=20, choices=StatusNFE.choices, default=StatusNFE.AGUARDANDO)
    nfe_io_id = models.CharField(max_length=255, null=True, blank=True, db_index=True, help_text="ID retornado pela API NFE.io")

    # Service data
    city_service_code = models.CharField(max_length=20, help_text="Código de Serviço do Município")
    description = models.TextField(help_text="Discriminação do Serviço")
    services_amount = models.DecimalField(max_digits=12, decimal_places=2)
    borrower_data = models.JSONField(help_text="Dados do tomador (cliente) enviados para a API")

    # Response data
    chave_acesso = models.CharField(_("Chave de Acesso"), max_length=44, null=True, blank=True)
    numero = models.CharField(_("Número da NF"), max_length=20, null=True, blank=True)
    data_emissao = models.DateTimeField(_("Data e Hora da Emissão"), null=True, blank=True)
    data_cancelamento = models.DateTimeField(_("Data e Hora do Cancelamento"), null=True, blank=True)
    arquivo_pdf = models.FileField(_("Arquivo PDF"), upload_to=nf_file_path, null=True, blank=True)
    arquivo_xml = models.FileField(_("Arquivo XML"), upload_to=nf_file_path, null=True, blank=True)
    dados_retorno_api = models.JSONField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Nota Fiscal de Serviço (NFS-e)")
        verbose_name_plural = _("Notas Fiscais de Serviço (NFS-e)")
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'nfe_io_id'], name='nfse_nfeio_id_unico_por_tenant'),
        ]

class NotaFiscalProduto(TenantScopedModel):
    """ Model for Product Invoices (NF-e). """
    id = models.AutoField(primary_key=True)
    entidade = models.ForeignKey('entidades.Entidade', on_delete=models.PROTECT, null=True, blank=True, related_name='+', verbose_name=_("Entidade emitente"))
    status = models.CharField(max_length=20, choices=StatusNFE.choices, default=StatusNFE.AGUARDANDO)
    nfe_io_id = models.CharField(max_length=255, null=True, blank=True, db_index=True, help_text="ID retornado pela API NFE.io")

    # Product data
    buyer_data = models.JSONField(help_text="Dados do comprador enviados para a API")
    items_data = models.JSONField(help_text="Lista de itens da nota enviada para a API")

    # Response data
    chave_acesso = models.CharField(_("Chave de Acesso"), max_length=44, null=True, blank=True)
    numero = models.CharField(_("Número da NF"), max_length=20, null=True, blank=True)
    data_emissao = models.DateTimeField(_("Data e Hora da Emissão"), null=True, blank=True)
    data_cancelamento = models.DateTimeField(_("Data e Hora do Cancelamento"), null=True, blank=True)
    arquivo_pdf = models.FileField(_("Arquivo PDF"), upload_to=nf_file_path, null=True, blank=True)
    arquivo_xml = models.FileField(_("Arquivo XML"), upload_to=nf_file_path, null=True, blank=True)
    dados_retorno_api = models.JSONField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Nota Fiscal de Produto (NF-e)")
        verbose_name_plural = _("Notas Fiscais de Produto (NF-e)")
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'nfe_io_id'], name='nfprod_nfeio_id_unico_por_tenant'),
        ]

# --- Models from financeiro app ---

class NotaFiscal(TenantScopedModel, Excluivel):
    """
    Armazena as informações das notas fiscais recebidas de fornecedores,
    vinculadas a um empreendimento.
    """
    nota_fiscal_id = models.AutoField(primary_key=True)
    # A destinatária: quem comprou (docs/modulos/entidades.md §2).
    entidade = _entidade_fk()
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.CASCADE, related_name='notas_fiscais', verbose_name=_("Empreendimento"))
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.CASCADE, related_name='notas_fiscais_emitidas', verbose_name=_("Fornecedor"))
    numero_nota = models.CharField(max_length=50, verbose_name=_("Número da Nota Fiscal"))
    chave_acesso = models.CharField(max_length=44, help_text=_("Chave de Acesso de 44 dígitos da NF-e"))
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
        # Número e chave de acesso únicos por-tenant (Fase 8.3).
        constraints = [
            # Número é por FORNECEDOR: a NF 1234 de duas empreiteiras são duas notas.
            models.UniqueConstraint(fields=['tenant', 'fornecedor', 'numero_nota'], condition=models.Q(excluido_em__isnull=True), name='nf_numero_unico_por_fornecedor'),
            models.UniqueConstraint(fields=['tenant', 'chave_acesso'], condition=models.Q(excluido_em__isnull=True), name='nf_chave_acesso_unica_por_tenant'),
        ]

    def __str__(self):
        return f"NF {self.numero_nota} - {self.fornecedor.razao_social}"

    def save(self, *args, **kwargs):
        from entidades.regras import preencher
        preencher(self, obra_attr=None)
        super().save(*args, **kwargs)


class ContaPagar(TenantScopedModel, Excluivel):
    """
    Registra as contas a pagar da empresa, como pagamentos a fornecedores.
    """
    conta_pagar_id = models.AutoField(primary_key=True, verbose_name=_("ID da Conta a Pagar"))
    # Quem paga (docs/modulos/entidades.md §2). O `save()` aplica a regra quando
    # quem cria o título não informa.
    entidade = _entidade_fk()
    # Vazio só no título entre entidades do grupo: lá a contraparte é a entidade.
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.CASCADE, null=True, blank=True, related_name='contas_a_pagar', verbose_name=_("Fornecedor"))
    contraparte = _contraparte_fk()
    natureza = _natureza_field()
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    # D.1.4 — a dimensão de obra na despesa. Sem ela, o "realizado" do Orçamento
    # só via o que passou por pedido de compra. A etapa é opcional e afina o
    # orçado × realizado por etapa; tem de ser da mesma obra. Quem rateia por
    # centro de custo com obra (`CentroCusto.obra`) atribui a fração rateada —
    # ver `financeiro_obra.atribuicao`.
    obra = models.ForeignKey('obras.Obra', on_delete=models.SET_NULL, null=True, blank=True, related_name='contas_a_pagar', verbose_name=_("Obra"))
    etapa = models.ForeignKey('obras.EtapaObra', on_delete=models.SET_NULL, null=True, blank=True, related_name='contas_a_pagar', verbose_name=_("Etapa da obra"))
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

    # --- A compra que gerou o título (Suprimentos, 11/10/2026 — D284) ---
    # Seam frouxo, sem FK, pelo mesmo motivo do `PedidoCompra.conta_pagar_ref`
    # do outro lado: o ERP não depende do SCM. A NF-e da compra mora no SCM (lá
    # ela pode nascer só com o número, antes do documento); aqui fica o que o
    # financeiro precisa ver na linha do título para não pagar sem nota.
    class SituacaoNfe(models.TextChoices):
        NAO_SE_APLICA = "", _("—")
        AGUARDANDO_NOTA = "aguardando_nota", _("Aguardando NF-e")
        AGUARDANDO_DOCUMENTO = "aguardando_documento", _("NF-e informada, aguardando documento")
        CONFERIDA = "conferida", _("NF-e conferida")
        DIVERGENTE = "divergente", _("NF-e divergente")

    pedido_compra_ref = models.PositiveIntegerField(null=True, blank=True, db_index=True, verbose_name=_("Pedido de compra (Suprimentos)"))
    nfe_numero = models.CharField(max_length=20, blank=True, verbose_name=_("Número da NF-e da compra"))
    nfe_situacao = models.CharField(
        max_length=20, choices=SituacaoNfe.choices, blank=True, default="",
        verbose_name=_("Situação da NF-e da compra"),
    )

    class Meta:
        verbose_name = _("Conta a Pagar")
        verbose_name_plural = _("Contas a Pagar")
        ordering = ['data_vencimento']
        db_table = 'financeiro_contapagar'
        # A ordem padrão da grade (listao.py), só das linhas vivas — as da lixeira
        # nunca aparecem nela.
        indexes = [
            models.Index(
                fields=['tenant', 'data_vencimento'], condition=models.Q(excluido_em__isnull=True),
                name='cp_vencimento_vivo',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(fornecedor__isnull=False, contraparte__isnull=True, natureza='')
                    | models.Q(fornecedor__isnull=True, contraparte__isnull=False) & ~models.Q(natureza='')
                ),
                name='cp_fornecedor_ou_contraparte',
            ),
        ]

    def __str__(self):
        return f"Pagar a {self.nome_da_pessoa} - Vence em {self.data_vencimento}"

    @property
    def nome_da_pessoa(self) -> str:
        if self.fornecedor_id:
            return self.fornecedor.razao_social
        return str(self.contraparte) if self.contraparte_id else ''

    def save(self, *args, **kwargs):
        from entidades.regras import preencher
        preencher(self)
        super().save(*args, **kwargs)

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

        Título já QUITADO/CANCELADO **ou baixa que ultrapassa o saldo** (L6): em
        vez de aplicar (o que infla `valor_pago` além de `total_devido` e duplica
        `Transacao`), registra uma `RevisaoBaixa` pendente e levanta
        `BaixaRequerRevisao` — quem chamou decide o que responder. `forcar=True`
        (usado só por `RevisaoBaixa.aprovar`) ignora o guard e aplica a baixa
        represada.

        L5: o read-modify-write roda sob `select_for_update()` numa transação —
        há dois produtores reais concorrentes (baixa manual da UI × webhook do
        Asaas) e sem o lock de linha um sobrescreve o `valor_pago` do outro (o
        lock só é efetivo no Postgres; no SQLite é no-op).
        """
        with transaction.atomic():
            # Trava a linha do título e recarrega o estado corrente sob o lock.
            type(self).objects.select_for_update().get(pk=self.pk)
            self.refresh_from_db()

            novo_total_devido = (
                self.valor + (self.juros + juros) + (self.multa + multa) - (self.desconto + desconto)
            )
            # O que entrou (ou saiu) de caixa: principal + encargos - desconto —
            # o mesmo número da `Transacao` abaixo. Somar só o principal deixava
            # a conta paga com juros eternamente "Parcial" (achado no item 55).
            novo_valor_pago = self.valor_pago + valor + juros + multa - desconto
            ja_encerrado = self.status in (StatusConta.QUITADO, StatusConta.CANCELADO)
            excede_saldo = novo_valor_pago > novo_total_devido

            if forcar or not (ja_encerrado or excede_saldo):
                self.valor_pago = novo_valor_pago
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
                    obra_id=self.obra_id,  # D.1.4
                    descricao=f"Baixa de pagamento ({origem}) — {self.descricao[:200]}",
                    valor=valor + juros + multa - desconto,
                    tipo=Transacao.TipoTransacao.SAIDA,
                    meio_pagamento=meio_pagamento or 'Não informado',
                    usuario=usuario,
                    data_transacao=_data_baixa_para_datetime(data),  # L7
                )

                # Auditoria (Fase 9.E): a baixa é o evento financeiro sensível por
                # excelência — registra os dois caminhos (manual e webhook Asaas), que
                # compartilham este choke point. `valor`/status não são PII.
                from nucleo.auditoria import registrar_auditoria
                registrar_auditoria(
                    acao="baixa", instance=self, usuario=usuario,
                    detalhes={
                        "valor": str(valor), "origem": origem,
                        "meio_pagamento": meio_pagamento or "", "novo_status": self.status,
                    },
                )
                # Intercompany: o mesmo dinheiro quita o espelho na outra entidade.
                if self.natureza and origem != 'espelho':
                    from .intercompany import espelhar_baixa
                    espelhar_baixa(self, valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
                                   meio_pagamento=meio_pagamento, usuario=usuario)
                return self

        # Represado (fora do lock): título já encerrado ou baixa em excesso (L6).
        if ja_encerrado:
            motivo = f"Título já estava {self.get_status_display()} quando esta baixa foi recebida."
        else:
            saldo = novo_total_devido - self.valor_pago
            motivo = f"Baixa de R$ {valor} excede o saldo em aberto do título (R$ {saldo})."
        revisao = RevisaoBaixa.objects.create(
            tenant=self.tenant,
            conta_pagar=self,
            valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
            meio_pagamento=meio_pagamento, origem=origem,
            motivo=motivo,
            solicitado_por=usuario,
        )
        raise BaixaRequerRevisao(revisao)


class ContaReceber(TenantScopedModel, Excluivel):
    """
    Registra as contas a receber da empresa, como pagamentos de clientes.
    """
    conta_receber_id = models.AutoField(primary_key=True, verbose_name=_("ID da Conta a Receber"))
    # Quem recebe — ver ContaPagar.entidade.
    entidade = _entidade_fk()
    # Vazio só no título entre entidades do grupo: lá a contraparte é a entidade.
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.CASCADE, null=True, blank=True, related_name='contas_a_receber', verbose_name=_("Cliente"))
    contraparte = _contraparte_fk()
    natureza = _natureza_field()
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    # D.1.4 — a receita da obra: a construtora contratada (empreitada,
    # administração) recebe por obra. A venda de unidade fica no empreendimento.
    obra = models.ForeignKey('obras.Obra', on_delete=models.SET_NULL, null=True, blank=True, related_name='contas_a_receber', verbose_name=_("Obra"))
    # A parcela aponta para a unidade que ela paga. Sem isto, um cliente com dois
    # lotes no mesmo loteamento tem a inadimplência somada num balaio só e a
    # carteira por unidade seria um número inventado. Opcionais porque parcelas
    # anteriores a este vínculo existem e continuam válidas — elas contam no
    # total do cliente e ficam fora do rateio por unidade.
    cliente_empreendimento = models.ForeignKey(
        'clientes.ClienteEmpreendimento', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contas_a_receber', verbose_name=_("Aquisição (unidade) vinculada"),
    )
    contrato = models.ForeignKey(
        'clientes.ContratoCliente', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contas_a_receber', verbose_name=_("Contrato vinculado"),
    )
    nota_fiscal_recebida = models.ForeignKey(NotaFiscal, on_delete=models.SET_NULL, null=True, blank=True, related_name='contas_a_receber', verbose_name=_("Nota Fiscal Associada"))
    nota_fiscal_servico = models.OneToOneField('NotaFiscalServico', on_delete=models.SET_NULL, related_name='conta_receber_origem', null=True, blank=True, verbose_name=_("NFS-e emitida"))
    nota_fiscal_produto = models.OneToOneField('NotaFiscalProduto', on_delete=models.SET_NULL, related_name='conta_receber_origem', null=True, blank=True, verbose_name=_("NF-e emitida"))
    descricao = models.TextField(verbose_name=_("Descrição da Conta"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor da Conta"))
    # ─── Correção monetária (contratos com índice) ────────────────────────────
    # `valor` é o que se cobra hoje — é ele que o boleto carrega. `valor_nominal`
    # preserva o que o contrato dizia na assinatura, e os três campos abaixo são
    # a memória do reajuste. Sem eles, o cliente que pergunta "por que subiu"
    # recebe um número sem origem, e conferir o reajuste exigiria refazer a conta
    # à mão sobre uma série que pode ter sido revisada desde então.
    valor_nominal = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("Valor nominal (sem correção)"),
        help_text=_("O valor do contrato na assinatura. Vazio = título nunca corrigido."),
    )
    fator_correcao = models.DecimalField(
        max_digits=12, decimal_places=8, null=True, blank=True,
        verbose_name=_("Fator de correção aplicado"),
    )
    correcao_ate_competencia = models.DateField(
        null=True, blank=True, verbose_name=_("Índice acumulado até"),
    )
    corrigido_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Corrigido em"),
    )
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
        # Ver ContaPagar.Meta — mesma grade, mesma ordem padrão.
        indexes = [
            models.Index(
                fields=['tenant', 'data_vencimento'], condition=models.Q(excluido_em__isnull=True),
                name='cr_vencimento_vivo',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(cliente__isnull=False, contraparte__isnull=True, natureza='')
                    | models.Q(cliente__isnull=True, contraparte__isnull=False) & ~models.Q(natureza='')
                ),
                name='cr_cliente_ou_contraparte',
            ),
        ]

    def __str__(self):
        return f"Receber de {self.nome_da_pessoa} - Vence em {self.data_vencimento}"

    @property
    def nome_da_pessoa(self) -> str:
        if self.cliente_id:
            return self.cliente.nome_completo
        return str(self.contraparte) if self.contraparte_id else ''

    def save(self, *args, **kwargs):
        from entidades.regras import preencher
        preencher(self)
        super().save(*args, **kwargs)

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
        a ação manual da UI ou a baixa automática via webhook (Asaas, D.1.2:
        `origem='asaas'`). Mesmos guards (título já QUITADO/CANCELADO ou baixa em
        excesso → `RevisaoBaixa`, L6) e mesmo lock de linha (L5) — ver docstring
        de `ContaPagar.dar_baixa`.
        """
        with transaction.atomic():
            # Trava a linha do título e recarrega o estado corrente sob o lock (L5).
            type(self).objects.select_for_update().get(pk=self.pk)
            self.refresh_from_db()

            novo_total_devido = (
                self.valor + (self.juros + juros) + (self.multa + multa) - (self.desconto + desconto)
            )
            # O que entrou (ou saiu) de caixa: principal + encargos - desconto —
            # o mesmo número da `Transacao` abaixo. Somar só o principal deixava
            # a conta paga com juros eternamente "Parcial" (achado no item 55).
            novo_valor_pago = self.valor_pago + valor + juros + multa - desconto
            ja_encerrado = self.status in (StatusConta.QUITADO, StatusConta.CANCELADO)
            excede_saldo = novo_valor_pago > novo_total_devido

            if forcar or not (ja_encerrado or excede_saldo):
                self.valor_pago = novo_valor_pago
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
                    obra_id=self.obra_id,  # D.1.4
                    descricao=f"Baixa de recebimento ({origem}) — {self.descricao[:200]}",
                    valor=valor + juros + multa - desconto,
                    tipo=Transacao.TipoTransacao.ENTRADA,
                    meio_pagamento=meio_pagamento or 'Não informado',
                    usuario=usuario,
                    data_transacao=_data_baixa_para_datetime(data),  # L7
                )

                # Auditoria (Fase 9.E): mesmo choke point da baixa manual e do webhook
                # Asaas (espelha `ContaPagar.dar_baixa`).
                from nucleo.auditoria import registrar_auditoria
                registrar_auditoria(
                    acao="baixa", instance=self, usuario=usuario,
                    detalhes={
                        "valor": str(valor), "origem": origem,
                        "meio_pagamento": meio_pagamento or "", "novo_status": self.status,
                    },
                )

                # D3: propaga a quitação para os boletos vinculados. `dar_baixa` é o
                # único caminho de baixa (manual ou webhook Asaas), mas até aqui só o
                # handler do Asaas marcava o boleto como PAGO — uma baixa **manual**
                # deixava o boleto preso em EMITIDO na listagem/detalhe ("como se a
                # mudança não tivesse sido aplicada"). Só quando o título fica QUITADO
                # e apenas para boletos em estado não-terminal (não reabre PAGO/CANCELADO).
                if self.status == StatusConta.QUITADO:
                    self.boletos.exclude(
                        status__in=(Boleto.StatusBoleto.PAGO, Boleto.StatusBoleto.CANCELADO),
                    ).update(
                        status=Boleto.StatusBoleto.PAGO,
                        data_pagamento=_data_baixa_para_datetime(data),
                    )
                # Intercompany: ver ContaPagar.dar_baixa.
                if self.natureza and origem != 'espelho':
                    from .intercompany import espelhar_baixa
                    espelhar_baixa(self, valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
                                   meio_pagamento=meio_pagamento, usuario=usuario)
                return self

        # Represado (fora do lock): título já encerrado ou baixa em excesso (L6).
        if ja_encerrado:
            motivo = f"Título já estava {self.get_status_display()} quando esta baixa foi recebida."
        else:
            saldo = novo_total_devido - self.valor_pago
            motivo = f"Baixa de R$ {valor} excede o saldo em aberto do título (R$ {saldo})."
        revisao = RevisaoBaixa.objects.create(
            tenant=self.tenant,
            conta_receber=self,
            valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
            meio_pagamento=meio_pagamento, origem=origem,
            motivo=motivo,
            solicitado_por=usuario,
        )
        raise BaixaRequerRevisao(revisao)


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
    O centro de custo da plataforma — um só, para o rateio do ERP e para a
    alocação da compra no Suprimentos (docs/modulos/entidades.md §2). Nome +
    vínculo opcional a obra/empreendimento + a entidade dona. Rateio para centro
    de custo de outra entidade gera intercompany.

    Vertical-agnóstico: obra é só um `tipo` (caso construtora); loja usa
    filial/almoxarifado. `local_estoque_ref` é o seam leve para o modulosil.
    """
    class Tipo(models.TextChoices):
        OBRA = "obra", _("Obra")
        EMPREENDIMENTO = "empreendimento", _("Empreendimento")
        ALMOXARIFADO = "almoxarifado", _("Almoxarifado / Central")
        FILIAL = "filial", _("Filial")
        ADMINISTRATIVO = "administrativo", _("Administrativo")
        OUTRO = "outro", _("Outro")

    centro_custo_id = models.AutoField(primary_key=True, verbose_name=_("ID do Centro de Custo"))
    entidade = _entidade_fk()
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    codigo = models.CharField(max_length=30, blank=True, verbose_name=_("Código"))
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.OUTRO, verbose_name=_("Tipo"))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, related_name='centros_custo', verbose_name=_("Empreendimento"))
    # D.1.4 — rateio para a obra: a parte da conta rateada a este centro conta
    # como despesa (ou receita) desta obra.
    obra = models.ForeignKey('obras.Obra', on_delete=models.SET_NULL, null=True, blank=True, related_name='centros_custo_erp', verbose_name=_("Obra"))
    local_estoque_ref = models.CharField(
        max_length=100, blank=True, verbose_name=_("Local de estoque (referência)"),
        help_text=_("Seam p/ o modulosil: identifica o local de estoque até o módulo existir."),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Centro de Custo")
        verbose_name_plural = _("Centros de Custo")
        ordering = ['nome']

    def __str__(self):
        return f"{self.codigo} — {self.nome}" if self.codigo else self.nome

    def save(self, *args, **kwargs):
        from entidades.regras import preencher
        preencher(self)
        super().save(*args, **kwargs)


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


class AnotacaoContaPagar(TenantScopedModel):
    """O que aconteceu fora do ERP e mexe no título — escrito na linha dele.

    *Dono, 11/10/2026:* "essas edições também têm que ir como anotações ao ERP.
    Caso o item venha a mais ou a menos". O pedido de compra muda depois de virar
    título (item a mais, saldo encerrado, nota divergente, valor editado), e quem
    paga só olha o ERP. A anotação **não altera o título**: o valor e o
    vencimento continuam sendo decididos por quem tem a baixa — ela diz o que
    mudou, onde, e por quê.

    Só se acrescenta (não há edição nem exclusão pela API): é trilha.
    """

    class Tipo(models.TextChoices):
        COBRANCA = "cobranca", _("Cobrança")
        EDICAO = "edicao", _("Pedido editado")
        DIVERGENCIA = "divergencia", _("Divergência no recebimento")
        NFE = "nfe", _("NF-e")
        CANCELAMENTO = "cancelamento", _("Cancelamento")
        NOTA = "nota", _("Anotação")

    anotacao_id = models.AutoField(primary_key=True)
    conta_pagar = models.ForeignKey(ContaPagar, on_delete=models.CASCADE, related_name='anotacoes', verbose_name=_("Conta a Pagar"))
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.NOTA, verbose_name=_("Tipo"))
    origem = models.CharField(max_length=20, blank=True, verbose_name=_("Módulo de origem"), help_text=_("'scm', 'manual'…"))
    texto = models.TextField(verbose_name=_("Texto"))
    #: O valor que a anotação põe em jogo (a divergência, o saldo encerrado), quando há.
    valor = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Valor envolvido"))
    autor = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name=_("Autor"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Anotação de Conta a Pagar")
        verbose_name_plural = _("Anotações de Contas a Pagar")
        ordering = ['-criado_em', '-anotacao_id']

    def __str__(self):
        return f"Conta #{self.conta_pagar_id} · {self.get_tipo_display()}"


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
    # O pagador: um lote vai ao banco de uma entidade só.
    entidade = models.ForeignKey('entidades.Entidade', on_delete=models.PROTECT, null=True, blank=True, related_name='+', verbose_name=_("Entidade pagadora"))
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
    # O beneficiário: a entidade do título (docs/modulos/entidades.md §5).
    entidade = _entidade_fk()

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
    # Segunda via de título vencido (item 55): o boleto carrega saldo + multa +
    # juros até a nova data. As duas parcelas ficam separadas aqui porque é
    # assim que a baixa precisa lançá-las — somar tudo como principal jogaria o
    # pagamento em "baixa acima do saldo" e o título para revisão manual.
    valor_multa = models.DecimalField(_("Multa embutida"), max_digits=15, decimal_places=2, default=Decimal('0'))
    valor_juros = models.DecimalField(_("Juros embutidos"), max_digits=15, decimal_places=2, default=Decimal('0'))
    data_vencimento = models.DateField(_("Data de Vencimento"))
    data_emissao = models.DateTimeField(_("Data de Emissão"), auto_now_add=True)
    data_pagamento = models.DateTimeField(_("Data de Pagamento"), null=True, blank=True)
    data_cancelamento = models.DateTimeField(_("Data de Cancelamento"), null=True, blank=True)

    # Dados específicos do boleto/gateway
    gateway_id = models.CharField(max_length=512, null=True, blank=True, db_index=True, verbose_name=_("ID no Gateway de Pagamento"))
    url_pdf = models.URLField(max_length=512, null=True, blank=True, verbose_name=_("Link do Boleto (PDF)"))
    linha_digitavel = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Linha Digitável"))
    # Payloads crus do gateway: erro de emissão (códigos+descrições do Asaas),
    # resposta de cancelamento e última verificação ao vivo. É o que a UI abre no
    # popup de "detalhes do erro" e o que sustenta o fallback offline do documento.
    dados_retorno_api = models.JSONField(_("Retorno do Gateway"), null=True, blank=True)

    # ─── Canal de emissão (item 52) ───────────────────────────────────────────
    # `asaas`: o gateway emite, registra e avisa o pagamento pelo webhook.
    # `cnab`: o boleto é registrado direto no banco da empresa por arquivo de
    # remessa; o nosso número e o código de barras são nossos, e o pagamento
    # chega pelo arquivo de retorno.
    class Canal(models.TextChoices):
        ASAAS = 'asaas', _('Asaas')
        CNAB = 'cnab', _('Banco (CNAB)')

    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.ASAAS)
    conta_cobranca = models.ForeignKey(
        'ContaCobrancaBancaria', on_delete=models.PROTECT, null=True, blank=True, related_name='boletos',
        verbose_name=_("Carteira de cobrança"),
    )
    nosso_numero = models.CharField(_("Nosso número"), max_length=30, blank=True, default='')
    codigo_barras = models.CharField(_("Código de barras"), max_length=44, blank=True, default='')
    remessa = models.ForeignKey(
        'RemessaCnab', on_delete=models.SET_NULL, null=True, blank=True, related_name='boletos',
        verbose_name=_("Remessa"),
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Boleto")
        verbose_name_plural = _("Boletos")
        ordering = ['-data_vencimento']
        indexes = [models.Index(fields=['tenant', 'data_vencimento'], name='boleto_vencimento')]
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

    def save(self, *args, **kwargs):
        if not self.entidade_id:
            conta = self.conta_receber or self.conta_pagar
            self.entidade_id = conta.entidade_id
        super().save(*args, **kwargs)


# --- Emissão em lote e cobrança registrada no banco (item 52) ---

class LoteCobranca(TenantScopedModel):
    """Um clique de "gerar boletos" sobre várias contas.

    Cada conta vira um item com a sua própria sorte — emitido, recusado ou
    ignorado, com o motivo. É o que deixa a tela responder "dos 480, quais não
    saíram e por quê" em vez de "processado".
    """
    lote_id = models.AutoField(primary_key=True)
    canal = models.CharField(max_length=10, choices=Boleto.Canal.choices, default=Boleto.Canal.ASAAS)
    conta_cobranca = models.ForeignKey(
        'ContaCobrancaBancaria', on_delete=models.PROTECT, null=True, blank=True, related_name='lotes',
    )
    remessa = models.ForeignKey('RemessaCnab', on_delete=models.SET_NULL, null=True, blank=True, related_name='lotes')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    total = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Lote de cobrança")
        verbose_name_plural = _("Lotes de cobrança")
        ordering = ['-criado_em']


class ItemLoteCobranca(TenantScopedModel):
    class Situacao(models.TextChoices):
        PENDENTE = 'PENDENTE', _('Na fila')
        EMITIDO = 'EMITIDO', _('Emitido')
        ERRO = 'ERRO', _('Não emitido')
        IGNORADO = 'IGNORADO', _('Fora do lote')

    item_id = models.BigAutoField(primary_key=True)
    lote = models.ForeignKey(LoteCobranca, on_delete=models.CASCADE, related_name='itens')
    conta_receber = models.ForeignKey(ContaReceber, on_delete=models.CASCADE, related_name='+')
    vencimento = models.DateField(null=True, blank=True)
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.PENDENTE)
    mensagem = models.TextField(blank=True, default='')
    boleto = models.ForeignKey(Boleto, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Item de lote de cobrança")
        verbose_name_plural = _("Itens de lote de cobrança")
        ordering = ['item_id']


class ContaCobrancaBancaria(TenantScopedModel):
    """A carteira de cobrança da empresa num banco — de onde sai o CNAB.

    Os dados vêm do contrato de cobrança que a empresa assinou com o banco
    (convênio, carteira, código do beneficiário). O nosso número e o
    sequencial da remessa são contadores **desta** carteira: o banco recusa
    nosso número repetido e remessa fora de ordem.
    """
    class Layout(models.TextChoices):
        CNAB240 = '240', _('CNAB 240 (FEBRABAN)')
        CNAB400 = '400', _('CNAB 400')

    conta_cobranca_id = models.AutoField(primary_key=True)
    # A beneficiária: a carteira é de uma entidade, e só cobra título dela.
    entidade = _entidade_fk()
    nome = models.CharField(_("Nome"), max_length=80, help_text=_('Ex.: "Itaú — carteira 109".'))
    banco = models.CharField(_("Banco"), max_length=3)
    layout = models.CharField(_("Layout"), max_length=3, choices=Layout.choices, default=Layout.CNAB240)
    agencia = models.CharField(_("Agência"), max_length=5)
    agencia_dv = models.CharField(_("DV da agência"), max_length=1, blank=True, default='')
    conta = models.CharField(_("Conta"), max_length=12)
    conta_dv = models.CharField(_("DV da conta"), max_length=2, blank=True, default='')
    convenio = models.CharField(
        _("Convênio / código do beneficiário"), max_length=20, blank=True, default='',
        help_text=_("O número que o banco deu ao contrato de cobrança."),
    )
    carteira = models.CharField(_("Carteira"), max_length=3)
    variacao_carteira = models.CharField(_("Variação da carteira"), max_length=3, blank=True, default='')
    beneficiario_nome = models.CharField(_("Nome do beneficiário"), max_length=120)
    beneficiario_documento = models.CharField(_("CNPJ/CPF do beneficiário"), max_length=14)
    proximo_nosso_numero = models.BigIntegerField(_("Próximo nosso número"), default=1)
    proximo_sequencial_remessa = models.PositiveIntegerField(_("Próximo sequencial de remessa"), default=1)
    instrucoes = models.CharField(
        _("Instruções do boleto"), max_length=200, blank=True, default='',
        help_text=_('Impressas no boleto. Ex.: "Não receber após 60 dias do vencimento."'),
    )
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Carteira de cobrança")
        verbose_name_plural = _("Carteiras de cobrança")
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.entidade_id:
            from entidades.regras import matriz
            self.entidade_id = matriz(self.tenant_id).pk
        super().save(*args, **kwargs)


class RemessaCnab(TenantScopedModel):
    """O arquivo que vai ao banco. Guardado inteiro: é documento, e é o que se
    reenvia quando o banco diz que não recebeu."""
    remessa_id = models.AutoField(primary_key=True)
    conta_cobranca = models.ForeignKey(ContaCobrancaBancaria, on_delete=models.PROTECT, related_name='remessas')
    sequencial = models.PositiveIntegerField()
    nome_arquivo = models.CharField(max_length=40)
    conteudo = models.TextField()
    quantidade = models.PositiveIntegerField(default=0)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = _("Remessa CNAB")
        verbose_name_plural = _("Remessas CNAB")
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'conta_cobranca', 'sequencial'], name='remessa_sequencial_unico'),
        ]


class RetornoCnab(TenantScopedModel):
    """O arquivo que o banco devolve, com o que aconteceu com cada boleto."""
    retorno_id = models.AutoField(primary_key=True)
    conta_cobranca = models.ForeignKey(ContaCobrancaBancaria, on_delete=models.PROTECT, related_name='retornos')
    nome_arquivo = models.CharField(max_length=120)
    conteudo = models.TextField()
    resumo = models.JSONField(default=dict)
    recebido_em = models.DateTimeField(auto_now_add=True)
    recebido_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = _("Retorno CNAB")
        verbose_name_plural = _("Retornos CNAB")
        ordering = ['-recebido_em']


class ConfiguracaoFinanceiro(TenantScopedModel):
    """O que a empresa escolhe para o próprio financeiro, dentro do plano (§5.5u).

    Hoje, quantos boletos e notas um lote emite. Vazio = o máximo do plano; um
    número = freio da empresa contra o lote grande por engano. O teto continua
    sendo o do plano (`moduloerp.limites_lote`): gravar acima dele é recusado, e
    um plano que desce não deixa o número antigo valer mais que o novo teto.
    Quem muda: o administrador ou quem tem `erp.lote.configurar`.
    """
    boletos_por_lote = models.PositiveIntegerField(_("Boletos por lote"), null=True, blank=True)
    notas_por_lote = models.PositiveIntegerField(_("Notas fiscais por lote"), null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = _("Configuração do financeiro")
        verbose_name_plural = _("Configurações do financeiro")
        constraints = [
            models.UniqueConstraint(fields=['tenant'], name='configuracao_financeiro_por_tenant'),
        ]


class IntegracaoFiscal(TenantScopedModel):
    """A conta da empresa na NFE.io — **por empresa**, cadastrada pela tela.

    *Achado do dono, 10/10/2026:* "como vou cadastrar minha API?". A chave era
    uma só, do ambiente, para todos os tenants (a decisão da Fase 11.1), e não
    havia tela nenhuma: a NFS-e ficava em "Processando" até virar erro. Agora
    cada empresa cadastra a sua conta em ERP › Configurações; sem cadastro, vale
    a chave do ambiente (quem opera a plataforma para todos).

    A chave da API é guardada **cifrada** (`nucleo.cifra`) e nunca volta para a
    tela — só os últimos quatro caracteres, para a pessoa reconhecer qual é.

    **Uma por entidade** (docs/modulos/entidades.md §5): a NFS-e sai no CNPJ dono
    do título, e cada CNPJ é uma empresa diferente na NFE.io.
    """
    entidade = _entidade_fk()
    company_id = models.CharField(_("ID da empresa na NFE.io"), max_length=80, blank=True)
    api_key_cifrada = models.TextField(_("Chave da API (cifrada)"), blank=True)
    api_key_final = models.CharField(_("Final da chave"), max_length=8, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = _("Integração fiscal (NFE.io)")
        verbose_name_plural = _("Integrações fiscais (NFE.io)")
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'entidade'], name='integracao_fiscal_por_entidade'),
        ]

    def save(self, *args, **kwargs):
        if not self.entidade_id:
            from entidades.regras import matriz
            self.entidade_id = matriz(self.tenant_id).pk
        super().save(*args, **kwargs)

    @property
    def api_key(self) -> str:
        from nucleo.cifra import decifrar
        return decifrar(self.api_key_cifrada)

    def definir_api_key(self, valor: str) -> None:
        from nucleo.cifra import cifrar
        valor = (valor or "").strip()
        self.api_key_cifrada = cifrar(valor)
        self.api_key_final = valor[-4:] if valor else ""


class ParIntercompany(TenantScopedModel):
    """O par que um título gera para outra entidade do grupo (docs/modulos/entidades.md §3).

    A origem é o título comum (com fornecedor ou cliente) de quem pagou ou
    recebeu; o par são dois títulos com natureza — `credor` na entidade que tem
    a receber e `devedor` na que tem a pagar. Um par por (origem, contraparte):
    a fração do rateio e a da cota somam no mesmo par. Quem mantém o par é
    `moduloerp.intercompany.sincronizar`, nunca a API.
    """
    par_id = models.AutoField(primary_key=True)
    origem_pagar = models.ForeignKey(ContaPagar, on_delete=models.CASCADE, null=True, blank=True, related_name='pares_intercompany')
    origem_receber = models.ForeignKey(ContaReceber, on_delete=models.CASCADE, null=True, blank=True, related_name='pares_intercompany')
    entidade_origem = models.ForeignKey('entidades.Entidade', on_delete=models.PROTECT, related_name='+')
    contraparte = models.ForeignKey('entidades.Entidade', on_delete=models.PROTECT, related_name='+')
    natureza = models.CharField(max_length=20, choices=NaturezaIntercompany.choices)
    valor = models.DecimalField(max_digits=15, decimal_places=2)
    # Repasse de despesa: a receber na origem, a pagar na contraparte. Repasse de
    # receita: a pagar na origem, a receber na contraparte.
    titulo_receber = models.OneToOneField(ContaReceber, on_delete=models.PROTECT, related_name='par_intercompany')
    titulo_pagar = models.OneToOneField(ContaPagar, on_delete=models.PROTECT, related_name='par_intercompany')
    motivo = models.CharField(max_length=255, blank=True, verbose_name=_("De onde vem (rateio, cota)"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Par intercompany")
        verbose_name_plural = _("Pares intercompany")
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(origem_pagar__isnull=False, origem_receber__isnull=True)
                    | models.Q(origem_pagar__isnull=True, origem_receber__isnull=False)
                ),
                name='par_intercompany_uma_origem',
            ),
            models.UniqueConstraint(fields=['origem_pagar', 'contraparte'], name='par_unico_por_origem_pagar'),
            models.UniqueConstraint(fields=['origem_receber', 'contraparte'], name='par_unico_por_origem_receber'),
        ]

    @property
    def origem(self):
        return self.origem_pagar or self.origem_receber

    def __str__(self):
        return f"Par #{self.par_id}: {self.entidade_origem} ↔ {self.contraparte} R$ {self.valor}"
