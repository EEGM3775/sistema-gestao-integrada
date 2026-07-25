# backend/moduloorcamento/models.py
"""Orçamento de obra — ORC.0: a **base referencial de plataforma**.

Estas três tabelas são a exceção consciente à regra "todo model de negócio é
`TenantScopedModel`": elas guardam **dado público de terceiro** (SINAPI é
publicada pela Caixa/IBGE, ORSE pelo governo de Sergipe, ambas gratuitas e
mensais), não dado de cliente. Duas razões para não serem tenant-scoped:

1. **Volume.** SINAPI tem ~87 mil composições *por estado* e é republicada todo
   mês. Replicar isso por tenant multiplicaria dezenas de milhares de linhas por
   empresa, de conteúdo idêntico.
2. **Natureza.** Não há nada a isolar: o preço mediano do cimento em SP em
   07/2026 é o mesmo para todo mundo. RLS existe para proteger dado de cliente;
   aqui ela só custaria complexidade sem proteger nada.

Por isso não há política RLS nestas tabelas — a **leitura segue gateada pelo
entitlement `orcamento`** na API, e a **escrita só acontece por comando de
importação** (`manage.py importar_base_referencial`), nunca por endpoint.

O que é do tenant é a **adoção**: usar um item da base cria/atualiza o
`catalogo.Item` daquela empresa com `codigo_referencia`/`fonte_referencia`
preenchidos (o seam que o catálogo já traz), então entra no catálogo só o que a
empresa usa — e o item orçado é o mesmo que o SCM compra e o SIL estoca.

Desenho em docs/modulos/moduloorcamento.md §11.1.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class Fonte(models.TextChoices):
    """Bases de referência de custo do mercado brasileiro.

    Espelha (e amplia) `catalogo.Item.Fonte` — as duas listas precisam continuar
    compatíveis, porque a adoção copia `fonte` para `Item.fonte_referencia`.
    """

    SINAPI = "sinapi", _("SINAPI (Caixa/IBGE)")
    ORSE = "orse", _("ORSE (SE)")
    SICRO = "sicro", _("SICRO (DNIT)")
    SEINFRA = "seinfra", _("SEINFRA (CE)")
    SEDOP = "sedop", _("SEDOP (PA)")
    TCPO = "tcpo", _("TCPO (PINI)")
    PROPRIA = "propria", _("Própria")


class BaseReferencial(models.Model):
    """Uma **publicação** de base referencial: fonte × UF × mês × regime de encargos.

    A granularidade não é "a base SINAPI", é "SINAPI-SP de 07/2026 desonerada" —
    porque orçamento tem **data-base**, e comparar orçado com realizado sem saber
    de que publicação veio o preço é comparar coisas diferentes. Encargos onerado
    × desonerado mudam o custo de toda composição com mão de obra, então também
    são eixo de identidade, não atributo.
    """

    class Regime(models.TextChoices):
        ONERADO = "onerado", _("Onerado")
        DESONERADO = "desonerado", _("Desonerado")
        NAO_SE_APLICA = "na", _("Não se aplica")

    base_id = models.AutoField(primary_key=True)
    fonte = models.CharField(max_length=10, choices=Fonte.choices, verbose_name=_("Fonte"))
    uf = models.CharField(
        max_length=2, blank=True, verbose_name=_("UF"),
        help_text=_("Vazio para base nacional (TCPO, SICRO)."),
    )
    mes_referencia = models.DateField(
        verbose_name=_("Mês de referência (data-base)"),
        help_text=_("Dia 1 do mês da publicação — é a data-base do orçamento."),
    )
    regime_encargos = models.CharField(
        max_length=10, choices=Regime.choices, default=Regime.ONERADO,
        verbose_name=_("Regime de encargos"),
    )
    rotulo = models.CharField(max_length=120, blank=True, verbose_name=_("Rótulo"))
    total_insumos = models.PositiveIntegerField(default=0, verbose_name=_("Total de insumos"))
    total_composicoes = models.PositiveIntegerField(default=0, verbose_name=_("Total de composições"))
    ativa = models.BooleanField(default=True, verbose_name=_("Ativa"))
    importada_em = models.DateTimeField(auto_now=True, verbose_name=_("Importada em"))
    importada_por_nome = models.CharField(
        max_length=150, blank=True, verbose_name=_("Importada por"),
        help_text=_("Rótulo durável de quem rodou a importação (não é FK)."),
    )

    class Meta:
        verbose_name = _("Base referencial")
        verbose_name_plural = _("Bases referenciais")
        ordering = ["-mes_referencia", "fonte", "uf"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "uf", "mes_referencia", "regime_encargos"],
                name="orcamento_base_publicacao_unica",
            ),
        ]

    def __str__(self):
        return self.rotulo or self.rotulo_automatico()

    def rotulo_automatico(self) -> str:
        partes = [self.get_fonte_display().split(" (")[0]]
        if self.uf:
            partes.append(self.uf)
        partes.append(self.mes_referencia.strftime("%m/%Y"))
        if self.regime_encargos != self.Regime.NAO_SE_APLICA:
            partes.append(self.get_regime_encargos_display().lower())
        return " ".join(partes)


class InsumoReferencia(models.Model):
    """Uma linha da base: **insumo** (material, mão de obra, equipamento) ou
    **composição** (serviço formado por insumos). O discriminador é `tipo`, como
    na própria SINAPI, que publica os dois no mesmo catálogo com códigos
    distintos."""

    class Tipo(models.TextChoices):
        INSUMO = "insumo", _("Insumo")
        COMPOSICAO = "composicao", _("Composição")

    referencia_id = models.AutoField(primary_key=True)
    base = models.ForeignKey(
        BaseReferencial, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Base"),
    )
    codigo = models.CharField(max_length=30, verbose_name=_("Código na fonte"))
    descricao = models.CharField(max_length=500, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, verbose_name=_("Unidade"))
    tipo = models.CharField(
        max_length=12, choices=Tipo.choices, default=Tipo.INSUMO, verbose_name=_("Tipo"),
    )
    custo_unitario = models.DecimalField(
        max_digits=14, decimal_places=4, default=0, verbose_name=_("Custo unitário"),
        help_text=_("Preço mediano do insumo ou custo total da composição, na data-base."),
    )
    grupo = models.CharField(max_length=150, blank=True, verbose_name=_("Grupo/classe na fonte"))

    class Meta:
        verbose_name = _("Item de base referencial")
        verbose_name_plural = _("Itens de base referencial")
        ordering = ["base", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["base", "tipo", "codigo"], name="orcamento_referencia_codigo_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["base", "tipo"], name="orcamento_ref_base_tipo_idx"),
            models.Index(fields=["codigo"], name="orcamento_ref_codigo_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.descricao[:60]}"


class ComposicaoReferenciaItem(models.Model):
    """Linha **analítica** de uma composição: composição-pai → filho + coeficiente.

    É o que dá memória de cálculo ao preço (o diferencial da composição analítica
    sobre a sintética) e o que a adoção recursiva traduz em
    `catalogo.ComponenteComposicao`. O filho pode ser outro item do tipo
    composição — SINAPI tem composições auxiliares aninhadas.
    """

    componente_id = models.AutoField(primary_key=True)
    composicao = models.ForeignKey(
        InsumoReferencia, on_delete=models.CASCADE, related_name="componentes",
        verbose_name=_("Composição"),
    )
    filho = models.ForeignKey(
        InsumoReferencia, on_delete=models.CASCADE, related_name="usado_em",
        verbose_name=_("Insumo/composição filha"),
    )
    coeficiente = models.DecimalField(
        max_digits=14, decimal_places=5, verbose_name=_("Coeficiente"),
        help_text=_("Consumo do filho por unidade da composição (produtividade)."),
    )

    class Meta:
        verbose_name = _("Componente de composição referencial")
        verbose_name_plural = _("Componentes de composição referencial")
        ordering = ["composicao", "componente_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["composicao", "filho"], name="orcamento_ref_componente_unico",
            ),
        ]

    def __str__(self):
        return f"{self.composicao_id} ⊃ {self.filho_id} ×{self.coeficiente}"
