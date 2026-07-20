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


class CentroCusto(TenantScopedModel):
    """Destino/unidade de negócio a que uma compra se atribui — **próprio do SCM**
    (padrão Coupa: o procurement tem sua dimensão de alocação e a mapeia p/ o
    rateio do ERP ao virar ContaPagar). Vertical-agnóstico: obra é só UM `tipo`
    (caso construtora); loja usa filial/almoxarifado. O vínculo é opcional e
    polimórfico — só um dos campos preenchido conforme o `tipo`; `local_estoque_ref`
    é o seam leve para o modulosil (que ainda não existe)."""

    class Tipo(models.TextChoices):
        OBRA = "obra", _("Obra")
        EMPREENDIMENTO = "empreendimento", _("Empreendimento")
        ALMOXARIFADO = "almoxarifado", _("Almoxarifado / Central")
        FILIAL = "filial", _("Filial")
        ADMINISTRATIVO = "administrativo", _("Administrativo")
        OUTRO = "outro", _("Outro")

    centro_custo_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    codigo = models.CharField(max_length=30, blank=True, verbose_name=_("Código"))
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.OUTRO, verbose_name=_("Tipo"))
    empreendimento = models.ForeignKey(
        "empreendimentos.Empreendimento", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+", verbose_name=_("Empreendimento"),
    )
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+", verbose_name=_("Obra"),
    )
    local_estoque_ref = models.CharField(
        max_length=100, blank=True, verbose_name=_("Local de estoque (referência)"),
        help_text=_("Seam p/ o modulosil: identifica o local de estoque até o módulo existir."),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Centro de Custo (SCM)")
        verbose_name_plural = _("Centros de Custo (SCM)")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.codigo} — {self.nome}" if self.codigo else self.nome


class Produto(TenantScopedModel):
    """Item mestre do catálogo do SCM, **supplier-agnostic** (padrão Amazon ASIN /
    Nimbi Private: identidade do produto separada da oferta do fornecedor). A
    oferta de preço por fornecedor é `OfertaFornecedor`. `gtin`/`item_rede_id`
    são o seam para o catálogo global da rede (cotações comparáveis entre
    tenants) — ver docs/expansão/modulos/moduloscm.md §5."""

    class TipoItem(models.TextChoices):
        MATERIAL = "material", _("Material")
        SERVICO = "servico", _("Serviço")

    produto_id = models.AutoField(primary_key=True)
    codigo_interno = models.CharField(max_length=40, verbose_name=_("Código interno (SKU)"))
    descricao = models.CharField(max_length=255, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, verbose_name=_("Unidade"))  # un, kg, m³, m...
    categoria = models.CharField(max_length=80, blank=True, verbose_name=_("Categoria"))
    tipo_item = models.CharField(
        max_length=10, choices=TipoItem.choices, default=TipoItem.MATERIAL, verbose_name=_("Tipo"),
    )
    gtin = models.CharField(max_length=14, blank=True, verbose_name=_("GTIN/EAN"))
    item_rede_id = models.CharField(
        max_length=64, blank=True, verbose_name=_("ID no catálogo da rede"),
        help_text=_("Seam do catálogo global compartilhado (marketplace)."),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Produto (SCM)")
        verbose_name_plural = _("Produtos (SCM)")
        ordering = ["descricao"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo_interno"], name="scm_produto_codigo_por_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_interno} — {self.descricao}"


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
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="ofertas", verbose_name=_("Produto"))
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
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_demanda", verbose_name=_("Produto"))
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
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido", verbose_name=_("Produto"))
    descricao = models.CharField(max_length=255, blank=True, verbose_name=_("Descrição (serviço/item livre)"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    preco_unitario = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Preço unitário"))

    class Meta:
        verbose_name = _("Item de Pedido (SCM)")
        verbose_name_plural = _("Itens de Pedido (SCM)")
        ordering = ["item_pedido_id"]

    def __str__(self):
        return self.produto.descricao if self.produto else (self.descricao or f"Item #{self.item_pedido_id}")


class Recebimento(TenantScopedModel):
    """Entrega (parcial/total) de um Pedido — ponto de conciliação com a NF-e
    (`nota_fiscal_ref`, seam do moduloerp.nfe_client) e origem da entrada de
    estoque (`local_entrega`, seam do modulosil, que ainda não existe)."""

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
