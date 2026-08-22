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
        """Natureza do item — **a classificação da SINAPI**, que é a mesma régua
        que o resto do mercado usa.

        Até 20/08/2026 não havia `MAO_DE_OBRA`: pedreiro e servente entravam
        como `SERVICO`, e a precificação lia todo `SERVICO` como mão de obra
        para aplicar encargo social. O efeito era duplo e silencioso — serviço
        **terceirizado** (que já vem com encargo embutido no preço do
        subcontratado) levava encargo de novo, e a leitura "material × mão de
        obra × equipamento" do orçamento saía torta. Os dois passam a ser
        coisas distintas: `MAO_DE_OBRA` é gente da empresa (leva encargo),
        `SERVICO` é serviço contratado de terceiro (não leva).

        `ENCARGOS_COMPLEMENTARES` é a classe que a SINAPI publica para EPI,
        exames, alimentação e transporte do trabalhador: entra na composição
        rateado por hora de mão de obra e **não** recebe encargo social por
        cima — é complemento do custo do trabalhador, não salário.
        """

        MATERIAL = "material", _("Material")
        MAO_DE_OBRA = "mao_de_obra", _("Mão de obra")
        EQUIPAMENTO = "equipamento", _("Equipamento / Ferramenta")
        ENCARGOS_COMPLEMENTARES = "encargos_complementares", _("Encargos complementares")
        SERVICO = "servico", _("Serviço de terceiro")
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
    # `max_length` acompanha o maior valor da lista ("encargos_complementares",
    # 23) — largura de coluna, não teto de produto (planos.py §5.6).
    tipo = models.CharField(max_length=24, choices=Tipo.choices, default=Tipo.MATERIAL, verbose_name=_("Tipo"))
    # O rótulo da empresa por cima da natureza. Fica ao lado do `tipo`, e não no
    # lugar dele, porque todo cálculo do sistema (encargo, compra, estoque) lê o
    # `tipo`: um tipo próprio sem natureza declarada seria um item que ninguém
    # sabe precificar. O `save()` mantém os dois de acordo.
    tipo_proprio = models.ForeignKey(
        "catalogo.TipoItemProprio", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="itens", verbose_name=_("Tipo próprio da empresa"),
    )
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
    # De qual **edição** o item foi adotado ("SINAPI BA 10/2024 desonerada", ou
    # o nome do banco próprio). Rótulo durável e não FK, pelo mesmo motivo do
    # `importada_por_nome` da base: o catálogo é do tenant e a publicação é
    # global, e apagar uma publicação não pode apagar a procedência do item.
    # Sem este campo, o par (fonte, código) era toda a procedência guardada — e
    # não há como saber de qual edição veio a descrição que está gravada (D110).
    publicacao_referencia = models.CharField(
        max_length=120, blank=True, verbose_name=_("Publicação de origem"),
        help_text=_("Edição da base (ou banco) de onde o item foi adotado."),
    )
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

    def save(self, *args, **kwargs):
        """Tipo próprio escolhido → o `tipo` vem dele, sempre.

        É a guarda que impede a configuração incoerente: sem isto, um item
        marcado com o tipo próprio "Andaime locado" (natureza equipamento)
        poderia continuar com `tipo=material` no banco e o orçamento aplicaria a
        regra errada — divergência que ninguém vê na tela e aparece no preço.
        """
        if self.tipo_proprio_id:
            self.tipo = self.tipo_proprio.natureza
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_interno} — {self.descricao}"


class TipoItemProprio(TenantScopedModel):
    """O tipo de item **que a empresa cria**, por cima das naturezas da SINAPI.

    A lista de naturezas é fechada de propósito: não é gosto, é o que decide
    conta (encargo social incide sobre mão de obra e não sobre material; o que é
    comprável entra na relação de compra; o que é estocável tem saldo). O que a
    empresa cria é o **nome que ela usa** — "Andaime locado", "Verba de
    mobilização", "Locação de betoneira" — dizendo de qual natureza aquilo é e
    como as flags de domínio se comportam.

    Os padrões vêm da natureza escolhida (`padroes_da_natureza`), então quem
    cria um tipo sem entender de flag ainda assim cria um tipo coerente; quem
    entende ajusta. A incoerência clássica — "leva encargo social" ligado num
    tipo de natureza material — é bloqueada no `clean()`, e não só avisada:
    ela sairia como preço errado numa planilha de licitação.

    Quem cria isto é o mesmo papel que cuida do banco de preço da empresa
    (`cadastro.tipo_item.edit`) — não o orçamentista de plantão.
    """

    tipo_item_id = models.AutoField(primary_key=True)
    codigo = models.SlugField(max_length=30, verbose_name=_("Código"))
    nome = models.CharField(max_length=60, verbose_name=_("Nome"))
    descricao = models.CharField(max_length=200, blank=True, verbose_name=_("Descrição"))
    natureza = models.CharField(
        max_length=24, choices=Item.Tipo.choices, default=Item.Tipo.MATERIAL,
        verbose_name=_("Natureza (como o sistema calcula)"),
        help_text=_("A classificação da SINAPI de que este tipo herda o comportamento."),
    )
    leva_encargo_social = models.BooleanField(
        default=False, verbose_name=_("Leva encargo social"),
        help_text=_("Só faz sentido em mão de obra: o encargo incide sobre salário."),
    )
    compravel = models.BooleanField(default=True, verbose_name=_("Comprável (SCM)"))
    estocavel = models.BooleanField(default=True, verbose_name=_("Estocável (SIL)"))
    vendavel = models.BooleanField(default=False, verbose_name=_("Vendável (comercial)"))
    consumivel = models.BooleanField(default=True, verbose_name=_("Consumível (baixa por obra)"))
    rastreavel = models.BooleanField(default=False, verbose_name=_("Rastreável (lote/validade)"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Tipo próprio de item")
        verbose_name_plural = _("Tipos próprios de item")
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo"], name="catalogo_tipoitem_codigo_unico",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_natureza_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.leva_encargo_social and self.natureza != Item.Tipo.MAO_DE_OBRA:
            raise ValidationError({
                "leva_encargo_social": _(
                    "Encargo social incide sobre salário: só tipo de natureza "
                    "'Mão de obra' pode levá-lo. Se este custo já vem com encargo "
                    "embutido (serviço de terceiro), deixe desmarcado."
                ),
            })
        if self.natureza == Item.Tipo.COMPOSICAO and (self.compravel or self.estocavel):
            raise ValidationError({
                "compravel": _(
                    "Composição não se compra nem se estoca — quem se compra são "
                    "os insumos dela."
                ),
            })

    @staticmethod
    def padroes_da_natureza(natureza: str) -> dict:
        """As flags que a natureza escolhida implica — o ponto de partida do
        formulário, para ninguém precisar adivinhar cinco caixas de seleção."""
        base = {
            "leva_encargo_social": False, "compravel": True, "estocavel": True,
            "vendavel": False, "consumivel": True, "rastreavel": False,
        }
        if natureza == Item.Tipo.MAO_DE_OBRA:
            return {**base, "leva_encargo_social": True, "compravel": False,
                    "estocavel": False, "consumivel": False}
        if natureza in (Item.Tipo.SERVICO, Item.Tipo.COMPOSICAO):
            return {**base, "compravel": natureza == Item.Tipo.SERVICO,
                    "estocavel": False, "consumivel": False}
        if natureza in (Item.Tipo.EQUIPAMENTO, Item.Tipo.ATIVO):
            return {**base, "estocavel": natureza == Item.Tipo.EQUIPAMENTO, "consumivel": False}
        if natureza == Item.Tipo.ENCARGOS_COMPLEMENTARES:
            # EPI, exame, alimentação, transporte: compra-se, mas o consumo é do
            # trabalhador e não da obra — não baixa contra a etapa.
            return {**base, "consumivel": False}
        return base


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
