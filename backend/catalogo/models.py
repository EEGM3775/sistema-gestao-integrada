# backend/catalogo/models.py
"""Catálogo-mestre de plataforma (MDM/PIM).

Item mestre **único** (bem | serviço | equipamento | EPI | ativo | composição)
compartilhado por SCM (compra), SIL (estoque) e futuros (comercial/orçamento).
App de **fundação** — sem entitlement, como fornecedores/clientes. Nasce da
promoção do antigo `moduloscm.Produto` (migração 0002). Padrão dos grandes
players: SAP Material/Product Master; Oracle Item Master com taxonomia + flags
por aplicação. Desenho em docs/modulos/catalogo.md.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


class Item(TenantScopedModel):
    """Item mestre supplier-agnostic. O `tipo` é o discriminador (SAP-like); as
    flags por domínio (Oracle-like) dizem como cada módulo trata o item — um só
    cadastro, comportamento por flag, sem tipos redundantes."""

    class Tipo(models.TextChoices):
        MATERIAL = "material", _("Material")
        SERVICO = "servico", _("Serviço")
        EQUIPAMENTO = "equipamento", _("Equipamento / Ferramenta")
        EPI = "epi", _("EPI")
        ATIVO = "ativo", _("Ativo / Patrimônio")
        COMPOSICAO = "composicao", _("Composição")

    class Fonte(models.TextChoices):
        """Bases de referência de custo. Espelha `moduloorcamento.models.Fonte`
        (a adoção de um item da base copia a fonte para cá) — as duas listas
        precisam continuar compatíveis."""

        SINAPI = "sinapi", _("SINAPI")
        ORSE = "orse", _("ORSE")
        SICRO = "sicro", _("SICRO")
        SEINFRA = "seinfra", _("SEINFRA")
        SEDOP = "sedop", _("SEDOP")
        TCPO = "tcpo", _("TCPO")
        PROPRIA = "propria", _("Própria")

    item_id = models.AutoField(primary_key=True)
    codigo_interno = models.CharField(max_length=40, verbose_name=_("Código interno (SKU)"))
    descricao = models.CharField(max_length=255, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, verbose_name=_("Unidade"))  # un, kg, m³, m, vb...
    categoria = models.CharField(max_length=80, blank=True, verbose_name=_("Categoria"))
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.MATERIAL, verbose_name=_("Tipo"))
    # Flags por domínio (padrão Oracle stockable/inventory-item).
    compravel = models.BooleanField(default=True, verbose_name=_("Comprável (SCM)"))
    estocavel = models.BooleanField(default=True, verbose_name=_("Estocável (SIL)"))
    vendavel = models.BooleanField(default=False, verbose_name=_("Vendável (comercial)"))
    consumivel = models.BooleanField(default=True, verbose_name=_("Consumível (baixa por obra)"))
    rastreavel = models.BooleanField(default=False, verbose_name=_("Rastreável (lote/validade)"))
    ncm = models.CharField(max_length=10, blank=True, verbose_name=_("NCM"))
    gtin = models.CharField(max_length=14, blank=True, verbose_name=_("GTIN/EAN"))
    # Seam p/ bases de composição (SINAPI/TCPO) → módulo Orçamento (futuro).
    codigo_referencia = models.CharField(max_length=30, blank=True, verbose_name=_("Código de referência"))
    fonte_referencia = models.CharField(max_length=10, choices=Fonte.choices, blank=True, verbose_name=_("Fonte da referência"))
    # Seam do catálogo global compartilhado (marketplace/rede).
    item_rede_id = models.CharField(
        max_length=64, blank=True, verbose_name=_("ID no catálogo da rede"),
        help_text=_("Seam do catálogo global compartilhado (marketplace)."),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Item (catálogo)")
        verbose_name_plural = _("Itens (catálogo)")
        ordering = ["descricao"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "codigo_interno"], name="catalogo_item_codigo_por_tenant"),
        ]

    def __str__(self):
        return f"{self.codigo_interno} — {self.descricao}"


class ComponenteComposicao(TenantScopedModel):
    """BOM de um Item do tipo composição: insumos (`item_filho`) + `coeficiente`.
    Base para explosão de insumos / curva ABC do módulo Orçamento (futuro)."""

    componente_id = models.AutoField(primary_key=True)
    item_pai = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="componentes", verbose_name=_("Item composto"))
    item_filho = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="usado_em", verbose_name=_("Insumo"))
    coeficiente = models.DecimalField(max_digits=14, decimal_places=5, verbose_name=_("Coeficiente"))

    class Meta:
        verbose_name = _("Componente de Composição")
        verbose_name_plural = _("Componentes de Composição")
        ordering = ["item_pai", "componente_id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "item_pai", "item_filho"], name="catalogo_componente_unico"),
        ]

    def __str__(self):
        return f"{self.item_pai_id} ⊃ {self.item_filho_id} ×{self.coeficiente}"
