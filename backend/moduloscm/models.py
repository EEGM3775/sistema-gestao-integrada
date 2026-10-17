# backend/moduloscm/models.py
"""Modelos do SCM (suprimentos).

- Fatia 1: catálogo (`Produto` + `OfertaFornecedor` + `FaixaPrecoOferta`) e
  `CentroCusto`.
- Fatia 2: o pivô publicável `Demanda` (+ `ItemDemanda`) e a cotação
  `Cotacao` → `Proposta` (+ `ItemProposta`), com os seams de rede
  (`visibilidade`, `ref_externa`, `origem_tenant`).

Desenho multi-vertical, marketplace reverso e o par espelhado comprador↔vendedor
em docs/expansão/modulos/moduloscm.md. Pedido/Recebimento entram na fatia 3.
"""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel

# O centro de custo é um só, o do ERP (docs/modulos/entidades.md §2): a compra se
# atribui ao mesmo centro que o rateio usa, e ele tem a entidade dona. Era um
# modelo próprio do SCM (padrão Coupa) até 14/10/2026 — dois cadastros do mesmo
# destino, um sem a entidade. O nome continua exportado daqui para o SCM e o PDCA.
from moduloerp.models import CentroCusto  # noqa: E402,F401


class OfertaFornecedor(TenantScopedModel):
    """Oferta de um fornecedor para um `Produto` — **fonte única de preço E de
    estoque** para as DUAS vias de aquisição (cotação e compra direta). Não
    existe anúncio de venda direta separado da oferta de cotação: seriam dois
    saldos do mesmo item e vender sem lastro fere o CDC (decisão travada — ver
    docs/expansão/modulos/moduloscm.md §3). A compra direta usa `preco_direto`
    (fixo, mais restritivo); a cotação aplica desconto por volume via
    `FaixaPrecoOferta`. Publicação na rede é opt-in (`visibilidade`)."""

    class Visibilidade(models.TextChoices):
        PRIVADA = "privada", _("Privada")
        REDE = "rede", _("Publicada na rede")

    oferta_id = models.AutoField(primary_key=True)
    produto = models.ForeignKey("catalogo.Item", on_delete=models.CASCADE, related_name="ofertas", verbose_name=_("Item"))
    fornecedor = models.ForeignKey(
        "fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="ofertas_scm", verbose_name=_("Fornecedor"),
    )
    codigo_no_fornecedor = models.CharField(max_length=60, blank=True, verbose_name=_("Código no fornecedor"))
    preco_direto = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Preço de compra direta"))
    estoque_disponivel = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Estoque disponível"))
    estoque_reservado = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Estoque reservado"))
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Prazo de entrega (dias)"))
    # Publicação (marketplace) — opt-in. As duas vias leem o MESMO saldo acima.
    compra_direta = models.BooleanField(default=False, verbose_name=_("Disponível para compra direta"))
    visibilidade = models.CharField(
        max_length=10, choices=Visibilidade.choices, default=Visibilidade.PRIVADA, verbose_name=_("Visibilidade"),
    )
    regiao_entrega = models.CharField(max_length=120, blank=True, verbose_name=_("Região de entrega"))
    condicoes = models.TextField(blank=True, verbose_name=_("Condições"))
    vigencia_inicio = models.DateField(null=True, blank=True, verbose_name=_("Vigência (início)"))
    vigencia_fim = models.DateField(null=True, blank=True, verbose_name=_("Vigência (fim)"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Oferta de Fornecedor (SCM)")
        verbose_name_plural = _("Ofertas de Fornecedores (SCM)")
        ordering = ["produto", "preco_direto"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "produto", "fornecedor"], name="scm_oferta_produto_forn_por_tenant",
            ),
        ]

    @property
    def estoque_livre(self):
        """Saldo não comprometido (disponível − reservado). Fonte única para as
        duas vias — a trava anti-oversell do CDC opera sobre este número."""
        return self.estoque_disponivel - self.estoque_reservado

    def __str__(self):
        return f"{self.produto} @ {self.fornecedor}"


class FaixaPrecoOferta(TenantScopedModel):
    """Desconto por quantidade de uma oferta — usado na **cotação** (não na compra
    direta, que é preço fixo). A partir de `quantidade_min`, vale `preco_unitario`."""

    faixa_id = models.AutoField(primary_key=True)
    oferta = models.ForeignKey(OfertaFornecedor, on_delete=models.CASCADE, related_name="faixas_preco", verbose_name=_("Oferta"))
    quantidade_min = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade mínima"))
    preco_unitario = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Preço unitário"))

    class Meta:
        verbose_name = _("Faixa de Preço da Oferta (SCM)")
        verbose_name_plural = _("Faixas de Preço da Oferta (SCM)")
        ordering = ["oferta", "quantidade_min"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "oferta", "quantidade_min"], name="scm_faixa_qtdmin_por_oferta",
            ),
        ]

    def __str__(self):
        return f"{self.oferta}: ≥{self.quantidade_min} → {self.preco_unitario}"


# ---------------------------------------------------------------------------
# Fatia 2 — o pivô publicável (Demanda) e a cotação (Cotacao → Proposta).
# ---------------------------------------------------------------------------
class Demanda(TenantScopedModel):
    """Necessidade de compra — o **objeto-pivô** do SCM (marketplace reverso).
    Genérica: `tipo` material|serviço, então o mesmo motor serve compras de obra,
    condomínio e o marketplace de serviços. Nasce interna (manual ou da falta no
    estoque, `origem`) e pode ser **publicada na rede** (`visibilidade=rede`) para
    fornecedores externos responderem — por isso carrega `ref_externa` (id estável
    p/ o gêmeo espelhado). Ver docs/expansão/modulos/moduloscm.md §2–4."""

    class Tipo(models.TextChoices):
        MATERIAL = "material", _("Material")
        SERVICO = "servico", _("Serviço")

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        ABERTA = "aberta", _("Aberta")
        EM_COTACAO = "em_cotacao", _("Em cotação")
        ATENDIDA = "atendida", _("Atendida")
        CANCELADA = "cancelada", _("Cancelada")

    class Visibilidade(models.TextChoices):
        PRIVADA = "privada", _("Privada")
        REDE = "rede", _("Publicada na rede")

    class Origem(models.TextChoices):
        MANUAL = "manual", _("Manual")
        ESTOQUE = "estoque", _("Falta no estoque")
        # PDCA.5 — o seam do Last Planner. Restrição de material é a origem
        # natural de uma compra: o que trava a semana que vem tem de virar
        # demanda antes, e não depois. Marcar a origem é o que permite ao SCM
        # dizer "esta cotação está segurando a obra" em vez de tratá-la como
        # mais uma linha da fila.
        RESTRICAO = "restricao", _("Restrição de obra (PDCA)")
        # O cronograma puxa a compra: a fila "comprar até DD/MM" do plano vira
        # demanda (`modulopdca.suprimentos`). A origem diz ao comprador que a
        # data vem do plano — e que atrasar a cotação atrasa uma atividade.
        PLANO = "plano", _("Cronograma da obra (PDCA)")

    demanda_id = models.AutoField(primary_key=True)
    # Id estável do documento na rede (o gêmeo espelhado referencia por cópia, não
    # por FK cruzada). Global por natureza (UUID) — não colide entre tenants.
    ref_externa = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name=_("Referência externa"))
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.MATERIAL, verbose_name=_("Tipo"))
    centro_custo = models.ForeignKey(
        CentroCusto, on_delete=models.SET_NULL, null=True, blank=True, related_name="demandas", verbose_name=_("Centro de custo"),
    )
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("Solicitante"),
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"))
    visibilidade = models.CharField(max_length=10, choices=Visibilidade.choices, default=Visibilidade.PRIVADA, verbose_name=_("Visibilidade"))
    origem = models.CharField(max_length=10, choices=Origem.choices, default=Origem.MANUAL, verbose_name=_("Origem"))
    categoria = models.CharField(max_length=80, blank=True, verbose_name=_("Categoria"))
    regiao = models.CharField(max_length=120, blank=True, verbose_name=_("Região"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Demanda (SCM)")
        verbose_name_plural = _("Demandas (SCM)")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Demanda #{self.demanda_id} ({self.get_tipo_display()})"


class ItemDemanda(TenantScopedModel):
    """Linha de uma Demanda. `produto` é nulo para serviço/item livre (aí vale
    `descricao_servico`) — é o que permite a demanda genérica bem|serviço."""

    item_demanda_id = models.AutoField(primary_key=True)
    demanda = models.ForeignKey(Demanda, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Demanda"))
    produto = models.ForeignKey("catalogo.Item", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_demanda", verbose_name=_("Item"))
    descricao_servico = models.CharField(max_length=255, blank=True, verbose_name=_("Descrição (serviço/item livre)"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    unidade = models.CharField(max_length=20, blank=True, verbose_name=_("Unidade"))

    class Meta:
        verbose_name = _("Item de Demanda (SCM)")
        verbose_name_plural = _("Itens de Demanda (SCM)")
        ordering = ["item_demanda_id"]

    def __str__(self):
        return self.produto.descricao if self.produto else (self.descricao_servico or f"Item #{self.item_demanda_id}")


class Cotacao(TenantScopedModel):
    """RFQ (cotação) de uma Demanda — coleta `Proposta`s dos fornecedores. Pode
    ser interna (fornecedores conhecidos) ou publicada na rede."""

    class Status(models.TextChoices):
        ABERTA = "aberta", _("Aberta")
        ENCERRADA = "encerrada", _("Encerrada")
        ADJUDICADA = "adjudicada", _("Adjudicada")

    class Visibilidade(models.TextChoices):
        PRIVADA = "privada", _("Privada")
        REDE = "rede", _("Publicada na rede")

    cotacao_id = models.AutoField(primary_key=True)
    demanda = models.ForeignKey(Demanda, on_delete=models.CASCADE, related_name="cotacoes", verbose_name=_("Demanda"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ABERTA, verbose_name=_("Status"))
    visibilidade = models.CharField(max_length=10, choices=Visibilidade.choices, default=Visibilidade.PRIVADA, verbose_name=_("Visibilidade"))
    data_limite = models.DateField(null=True, blank=True, verbose_name=_("Data limite"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Cotação (SCM)")
        verbose_name_plural = _("Cotações (SCM)")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Cotação #{self.cotacao_id} (demanda {self.demanda_id})"


class Proposta(TenantScopedModel):
    """Resposta de um fornecedor a uma Cotação. Interna → `fornecedor` (FK). Da
    rede → `origem_tenant` (cópia do id do tenant vendedor, **sem FK cruzada**) +
    `fornecedor_nome` (rótulo durável). A geração do Pedido a partir da vencedora
    é da fatia 3."""

    class Status(models.TextChoices):
        RECEBIDA = "recebida", _("Recebida")
        VENCEDORA = "vencedora", _("Vencedora")
        RECUSADA = "recusada", _("Recusada")

    proposta_id = models.AutoField(primary_key=True)
    cotacao = models.ForeignKey(Cotacao, on_delete=models.CASCADE, related_name="propostas", verbose_name=_("Cotação"))
    fornecedor = models.ForeignKey(
        "fornecedores.Fornecedor", on_delete=models.SET_NULL, null=True, blank=True, related_name="propostas_scm", verbose_name=_("Fornecedor"),
    )
    # Seam de rede: proposta vinda de tenant externo é uma CÓPIA (id + rótulo),
    # nunca uma FK cruzada entre tenants (docs/expansão/modulos/moduloscm.md §4).
    origem_tenant = models.UUIDField(null=True, blank=True, verbose_name=_("Tenant de origem (rede)"))
    fornecedor_nome = models.CharField(max_length=255, blank=True, verbose_name=_("Nome do fornecedor (rótulo)"))
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Valor total"))
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Prazo de entrega (dias)"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEBIDA, verbose_name=_("Status"))
    # Quando o preço chegou — por telefone, e-mail ou planilha, o comprador digita
    # dias depois; é esta data que vai ao mapa e ao gráfico de preço do item, não
    # a do registro (dono, 16/10/2026).
    recebida_em = models.DateField(default=timezone.localdate, verbose_name=_("Recebida em"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Proposta (SCM)")
        verbose_name_plural = _("Propostas (SCM)")
        ordering = ["cotacao", "valor_total"]

    def __str__(self):
        rotulo = self.fornecedor.razao_social if self.fornecedor else (self.fornecedor_nome or "externo")
        return f"Proposta #{self.proposta_id} ({rotulo})"


class ItemProposta(TenantScopedModel):
    """Preço proposto para um item específico da demanda."""

    item_proposta_id = models.AutoField(primary_key=True)
    proposta = models.ForeignKey(Proposta, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Proposta"))
    item_demanda = models.ForeignKey(ItemDemanda, on_delete=models.PROTECT, related_name="propostas_item", verbose_name=_("Item da demanda"))
    preco_unitario = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Preço unitário"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))

    class Meta:
        verbose_name = _("Item de Proposta (SCM)")
        verbose_name_plural = _("Itens de Proposta (SCM)")
        ordering = ["item_proposta_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "proposta", "item_demanda"], name="scm_itemproposta_unico_por_proposta",
            ),
        ]

    def __str__(self):
        return f"{self.item_demanda} @ {self.preco_unitario}"


# ---------------------------------------------------------------------------
# Fatia 3 — Pedido (duas vias) → Recebimento + Avaliação de fornecedor.
# ---------------------------------------------------------------------------
class PedidoCompra(TenantScopedModel):
    """Pedido de compra — ponto de **convergência das duas vias de aquisição**
    (`origem`): compra direta (de uma `OfertaFornecedor` publicada a preço fixo)
    e cotação (da `Proposta` vencedora). `conta_pagar_ref` é o seam frouxo p/ o
    ERP (id da ContaPagar; sem FK, p/ o SCM não depender do app financeiro);
    `origem_tenant`/`ref_externa` são o seam do gêmeo Pedido de compra↔venda da
    rede (docs/expansão/modulos/moduloscm.md §4). Lado comprador apenas nesta
    fatia — o Pedido de venda do vendedor grada com a Esfera de Rede."""

    class Origem(models.TextChoices):
        COMPRA_DIRETA = "compra_direta", _("Compra direta")
        COTACAO = "cotacao", _("Cotação")
        MANUAL = "manual", _("Manual")

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        APROVADO = "aprovado", _("Aprovado")
        ENVIADO = "enviado", _("Enviado ao fornecedor")
        RECEBIDO_PARCIAL = "recebido_parcial", _("Recebido parcialmente")
        RECEBIDO_TOTAL = "recebido_total", _("Recebido totalmente")
        CANCELADO = "cancelado", _("Cancelado")

    pedido_id = models.AutoField(primary_key=True)
    ref_externa = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name=_("Referência externa"))
    origem = models.CharField(max_length=13, choices=Origem.choices, default=Origem.MANUAL, verbose_name=_("Origem"))
    # Rastros da via de origem (todos opcionais — só o da via usada é preenchido).
    demanda = models.ForeignKey(Demanda, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos", verbose_name=_("Demanda"))
    proposta_vencedora = models.ForeignKey(Proposta, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("Proposta vencedora"))
    oferta_origem = models.ForeignKey(OfertaFornecedor, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_diretos", verbose_name=_("Oferta (compra direta)"))
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="pedidos_scm", verbose_name=_("Fornecedor"))
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos", verbose_name=_("Centro de custo"))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"))
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Valor total"))
    data_pedido = models.DateField(default=timezone.localdate, verbose_name=_("Data do pedido"))
    data_entrega_prevista = models.DateField(null=True, blank=True, verbose_name=_("Entrega prevista"))
    # Seam frouxo p/ o ERP: id da ContaPagar gerada (sem FK — SCM não depende do app financeiro).
    conta_pagar_ref = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Ref. da conta a pagar (ERP)"))
    # Seam de rede: tenant vendedor quando a compra é na rede (cópia, sem FK cruzada).
    origem_tenant = models.UUIDField(null=True, blank=True, verbose_name=_("Tenant de origem (rede)"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    # Quando o pedido saiu para o fornecedor (PDF por e-mail/WhatsApp) e quantas
    # vezes foi editado depois de nascer — a revisão vai no PDF reenviado.
    enviado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Enviado ao fornecedor em"))
    revisao = models.PositiveIntegerField(default=0, verbose_name=_("Revisão"))

    class Meta:
        verbose_name = _("Pedido de Compra (SCM)")
        verbose_name_plural = _("Pedidos de Compra (SCM)")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.pedido_id} ({self.get_origem_display()})"


class ItemPedido(TenantScopedModel):
    """Linha de um Pedido de Compra."""

    item_pedido_id = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Pedido"))
    produto = models.ForeignKey("catalogo.Item", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido", verbose_name=_("Item"))
    descricao = models.CharField(max_length=255, blank=True, verbose_name=_("Descrição (serviço/item livre)"))
    unidade = models.CharField(max_length=20, blank=True, verbose_name=_("Unidade"))  # un, kg, m³… — a do produto quando é do catálogo
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    preco_unitario = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Preço unitário"))
    # O saldo que se desistiu de receber ("finalizar com saldo a menos", dono,
    # 11/10/2026). Não é recebido nem pendente: sai da conta do que falta e vai
    # ao ERP como divergência, para o título ser ajustado.
    quantidade_encerrada = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Saldo encerrado"))

    class Meta:
        verbose_name = _("Item de Pedido (SCM)")
        verbose_name_plural = _("Itens de Pedido (SCM)")
        ordering = ["item_pedido_id"]

    def __str__(self):
        return self.produto.descricao if self.produto else (self.descricao or f"Item #{self.item_pedido_id}")


class Recebimento(TenantScopedModel):
    """Entrega (parcial/total) de um Pedido — ponto de conciliação com a NF-e
    (`nota_fiscal_ref`, seam do moduloerp.nfe_client) e origem da entrada de
    estoque (`local_entrega`, resolvido pelo modulosil, que dá ENTRADA por signal)."""

    class Tipo(models.TextChoices):
        PARCIAL = "parcial", _("Parcial")
        TOTAL = "total", _("Total")

    recebimento_id = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="recebimentos", verbose_name=_("Pedido"))
    tipo = models.CharField(max_length=8, choices=Tipo.choices, default=Tipo.TOTAL, verbose_name=_("Tipo"))
    data = models.DateField(default=timezone.localdate, verbose_name=_("Data do recebimento"))
    local_entrega = models.CharField(max_length=100, blank=True, verbose_name=_("Local de entrega (ref. estoque)"))
    nota_fiscal_ref = models.CharField(max_length=60, blank=True, verbose_name=_("Ref. da NF-e (chave/número)"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    # Este recebimento finalizou o pedido deixando saldo para trás.
    encerrou_saldo = models.BooleanField(default=False, verbose_name=_("Encerrou o saldo"))
    recebido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("Recebido por"),
    )

    class Meta:
        verbose_name = _("Recebimento (SCM)")
        verbose_name_plural = _("Recebimentos (SCM)")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Recebimento #{self.recebimento_id} (pedido {self.pedido_id})"


class ItemRecebimento(TenantScopedModel):
    """Quantidade efetivamente recebida de um item do pedido."""

    item_recebimento_id = models.AutoField(primary_key=True)
    recebimento = models.ForeignKey(Recebimento, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Recebimento"))
    item_pedido = models.ForeignKey(ItemPedido, on_delete=models.PROTECT, related_name="recebimentos_item", verbose_name=_("Item do pedido"))
    quantidade_recebida = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade recebida"))

    class Meta:
        verbose_name = _("Item de Recebimento (SCM)")
        verbose_name_plural = _("Itens de Recebimento (SCM)")
        ordering = ["item_recebimento_id"]

    def __str__(self):
        return f"{self.item_pedido}: {self.quantidade_recebida}"


# ---------------------------------------------------------------------------
# D284 (11/10/2026) — a cobrança do pedido, a NF-e da compra e o histórico.
# ---------------------------------------------------------------------------
class MeioPagamentoPedido(TenantScopedModel):
    """Um meio da cobrança do pedido — o espelho, na compra, do
    `clientes.MeioPagamento` da venda.

    *Dono, 11/10/2026:* "cobrança de pagamento do pedido que pode ser boleto,
    cheque, à vista, parcelas, cartão de crédito, promissória, pix, até mais de um
    meio". É uma **lista livre**: a soma dos meios fecha no valor do pedido (nem
    um centavo a mais ou a menos — quem confere é `moduloscm.cobranca`), e cada
    meio se divide nas suas parcelas. Cada parcela vira um título no ERP.
    """

    class Tipo(models.TextChoices):
        BOLETO = "boleto", _("Boleto")
        PIX = "pix", _("Pix")
        DINHEIRO = "dinheiro", _("Dinheiro (à vista)")
        TRANSFERENCIA = "transferencia", _("Transferência / TED")
        CHEQUE = "cheque", _("Cheque")
        CARTAO_CREDITO = "cartao_credito", _("Cartão de crédito")
        CARTAO_DEBITO = "cartao_debito", _("Cartão de débito")
        PROMISSORIA = "promissoria", _("Nota promissória")
        OUTRO = "outro", _("Outro")

    meio_id = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="meios_pagamento", verbose_name=_("Pedido"))
    ordem = models.PositiveSmallIntegerField(default=1, verbose_name=_("Ordem"))
    tipo = models.CharField(max_length=16, choices=Tipo.choices, verbose_name=_("Meio de pagamento"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor (R$)"))
    parcelas = models.PositiveSmallIntegerField(default=1, verbose_name=_("Parcelas"))
    primeiro_vencimento = models.DateField(verbose_name=_("1º vencimento"))
    # "30/60/90" do comércio: dias corridos entre as parcelas, como o fornecedor fala.
    intervalo_dias = models.PositiveSmallIntegerField(default=30, verbose_name=_("Dias entre parcelas"))
    descricao = models.CharField(max_length=200, blank=True, verbose_name=_("Descrição"),
                                 help_text=_("Banco e nº dos cheques, bandeira do cartão, o que explica o meio."))

    class Meta:
        verbose_name = _("Meio de pagamento do pedido (SCM)")
        verbose_name_plural = _("Meios de pagamento do pedido (SCM)")
        ordering = ["pedido", "ordem", "meio_id"]

    def __str__(self):
        return f"{self.get_tipo_display()} — R$ {self.valor}"


class ParcelaPedido(TenantScopedModel):
    """Uma parcela de um meio — e o título do ERP que ela gerou."""

    parcela_id = models.AutoField(primary_key=True)
    meio = models.ForeignKey(MeioPagamentoPedido, on_delete=models.CASCADE, related_name="parcelas_geradas", verbose_name=_("Meio"))
    numero = models.PositiveSmallIntegerField(verbose_name=_("Parcela nº"))
    vencimento = models.DateField(verbose_name=_("Vencimento"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor"))
    # Seam frouxo p/ o ERP (sem FK), como `PedidoCompra.conta_pagar_ref`.
    conta_pagar_ref = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Título no ERP"))

    class Meta:
        verbose_name = _("Parcela do pedido (SCM)")
        verbose_name_plural = _("Parcelas do pedido (SCM)")
        ordering = ["meio", "numero"]

    def __str__(self):
        return f"{self.meio} · {self.numero}"


class NotaFiscalCompra(TenantScopedModel):
    """A NF-e de uma compra — que pode nascer **só com o número**.

    *Dono, 11/10/2026:* "caso tenha só o número vai para o ERP com o número e fica
    aguardando o documento, e quando coloca o documento compara se o número está
    certo". Por isso ela mora aqui e não no `moduloerp.NotaFiscal` (que exige o
    XML e um empreendimento): aqui a nota existe antes do documento.

    A conferência (`moduloscm.notas`) olha número, série, CNPJ do emitente e,
    com o XML, o valor. Tudo o que não bate fica em `divergencias`, com a frase
    que a tela mostra e o ERP anota.
    """

    class Situacao(models.TextChoices):
        AGUARDANDO_DOCUMENTO = "aguardando_documento", _("Aguardando documento")
        CONFERIDA = "conferida", _("Conferida")
        DIVERGENTE = "divergente", _("Divergente")

    nota_id = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="notas_fiscais", verbose_name=_("Pedido"))
    recebimento = models.ForeignKey(
        Recebimento, on_delete=models.SET_NULL, null=True, blank=True, related_name="notas_fiscais", verbose_name=_("Recebimento"),
    )
    numero = models.CharField(max_length=20, verbose_name=_("Número"))
    serie = models.CharField(max_length=3, blank=True, verbose_name=_("Série"))
    chave_acesso = models.CharField(max_length=44, blank=True, verbose_name=_("Chave de acesso"))
    data_emissao = models.DateField(null=True, blank=True, verbose_name=_("Emissão"))
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Valor da nota"))
    emitente_cnpj = models.CharField(max_length=14, blank=True, verbose_name=_("CNPJ do emitente"))
    emitente_nome = models.CharField(max_length=255, blank=True, verbose_name=_("Emitente"))
    arquivo_xml = models.FileField(upload_to="scm/nfe/xml/%Y/%m/", null=True, blank=True, verbose_name=_("XML"))
    arquivo_pdf = models.FileField(upload_to="scm/nfe/pdf/%Y/%m/", null=True, blank=True, verbose_name=_("DANFE (PDF)"))
    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.AGUARDANDO_DOCUMENTO, verbose_name=_("Situação"))
    divergencias = models.JSONField(default=list, blank=True, verbose_name=_("Divergências"))
    duplicatas = models.JSONField(default=list, blank=True, verbose_name=_("Duplicatas do XML"))
    conferida_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Conferida em"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Lançada em"))
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = _("NF-e da compra (SCM)")
        verbose_name_plural = _("NF-e das compras (SCM)")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"NF-e {self.numero} (pedido {self.pedido_id})"


class EventoPedido(TenantScopedModel):
    """O histórico do pedido — e o que dele vai ao ERP.

    Edição, divergência de recebimento, nota e cobrança ficam aqui **e** viram
    anotação nos títulos do pedido. O registro mora no SCM porque o pedido pode
    mudar antes de ter título (cobrança ainda não definida); quando os títulos
    nascem, a trilha anterior é copiada para eles (`moduloscm.financeiro`), e o
    financeiro não recebe um título sem a história.
    """

    class Tipo(models.TextChoices):
        CRIADO = "criado", _("Pedido criado")
        EDICAO = "edicao", _("Pedido editado")
        ENVIO = "envio", _("Enviado ao fornecedor")
        RECEBIMENTO = "recebimento", _("Recebimento")
        DIVERGENCIA = "divergencia", _("Divergência no recebimento")
        NFE = "nfe", _("NF-e")
        COBRANCA = "cobranca", _("Cobrança")
        CANCELAMENTO = "cancelamento", _("Cancelamento")

    evento_id = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="eventos", verbose_name=_("Pedido"))
    tipo = models.CharField(max_length=12, choices=Tipo.choices, verbose_name=_("Tipo"))
    texto = models.TextField(verbose_name=_("Texto"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Valor envolvido"))
    #: Vai ao ERP como anotação dos títulos (o que mexe no que se paga).
    vai_ao_erp = models.BooleanField(default=False, verbose_name=_("Anotado no ERP"))
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Quando"))

    class Meta:
        verbose_name = _("Evento do pedido (SCM)")
        verbose_name_plural = _("Eventos do pedido (SCM)")
        ordering = ["-criado_em", "-evento_id"]

    def __str__(self):
        return f"Pedido {self.pedido_id} · {self.get_tipo_display()}"


class AvaliacaoFornecedor(TenantScopedModel):
    """Avaliação de desempenho de um fornecedor após um pedido — privada agora;
    vira reputação portátil na rede depois (docs/expansão/modulos/moduloscm.md §5)."""

    NOTA_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]

    avaliacao_id = models.AutoField(primary_key=True)
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.CASCADE, related_name="avaliacoes_scm", verbose_name=_("Fornecedor"))
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name="avaliacoes", verbose_name=_("Pedido"))
    nota_qualidade = models.PositiveSmallIntegerField(validators=NOTA_VALIDATORS, verbose_name=_("Qualidade (1–5)"))
    nota_pontualidade = models.PositiveSmallIntegerField(validators=NOTA_VALIDATORS, verbose_name=_("Pontualidade (1–5)"))
    nota_atendimento = models.PositiveSmallIntegerField(validators=NOTA_VALIDATORS, verbose_name=_("Atendimento (1–5)"))
    comentario = models.TextField(blank=True, verbose_name=_("Comentário"))
    data = models.DateField(auto_now_add=True, verbose_name=_("Data"))

    class Meta:
        verbose_name = _("Avaliação de Fornecedor (SCM)")
        verbose_name_plural = _("Avaliações de Fornecedores (SCM)")
        ordering = ["-data"]

    def __str__(self):
        return f"Avaliação de {self.fornecedor} ({self.data})"

    @classmethod
    def agg_por_fornecedor(cls, tenant_id, fornecedor_ids):
        """Reputação agregada: `{fornecedor_id: (media, count)}` para os
        fornecedores dados. A média é a das três notas (qualidade/pontualidade/
        atendimento) sobre todas as avaliações do fornecedor no tenant. Uma
        query (não N+1) — usada para as estrelas do mapa comparativo."""
        ids = [f for f in set(fornecedor_ids) if f]
        if not ids:
            return {}
        rows = (
            cls.objects.filter(tenant_id=tenant_id, fornecedor_id__in=ids)
            .values("fornecedor_id")
            .annotate(
                mq=models.Avg("nota_qualidade"),
                mp=models.Avg("nota_pontualidade"),
                ma=models.Avg("nota_atendimento"),
                n=models.Count("avaliacao_id"),
            )
        )
        out = {}
        for r in rows:
            media = (r["mq"] + r["mp"] + r["ma"]) / 3
            out[r["fornecedor_id"]] = (round(media, 2), r["n"])
        return out
