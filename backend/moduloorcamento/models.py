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
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


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


# ---------------------------------------------------------------------------
# ORC.1 — a planilha orçamentária (daqui para baixo, tudo é do tenant)
# ---------------------------------------------------------------------------
#
# A partir daqui os modelos são `TenantScopedModel` com RLS fail-closed: é o
# orçamento **da empresa**, não mais dado público. A fronteira entre as duas
# metades deste arquivo é a **adoção** (services.py): a base pública vira item
# do catálogo do tenant, e é esse item que a planilha orça.
#
# Estrutura espelhando o que Sienge, Orçafascio e OrçaFácil fazem — e o que os
# editais de obra pública exigem:
#
#   Orçamento (obra, data-base, BDI, encargos)
#     └── ItemOrcado — árvore EAP, código "1.2.3"
#           ├── SINTÉTICO  → agrupa, não custa: total = Σ filhos
#           └── ANALÍTICO  → custa: quantidade × custo unitário
#
# A distinção sintético × analítico não é decoração: é o que separa "1.2
# Estrutura" (um título) de "1.2.1 Concretagem de pilares fck 25, 120 m³ ×
# R$ 412,80" (uma linha de custo). Somar as duas contaria o custo duas vezes.


class Orcamento(TenantScopedModel):
    """Planilha orçamentária de uma obra, **versionada**.

    Três decisões de desenho que vêm do domínio, não da conveniência:

    1. **Versão, não edição.** Orçamento aprovado é a régua contra a qual o
       custo real é medido; revisar não sobrescreve — cria a versão seguinte e
       marca a anterior como `SUPERADO` (`RevisaoOrcamento` guarda o porquê).
       É como Sienge trata reprogramação e como o TCU exige em obra pública:
       aditivo precisa de rastro.
    2. **Data-base é do orçamento, não da base.** `data_base` é copiada da
       publicação escolhida e fica aqui mesmo que a `BaseReferencial` seja
       desativada depois. Comparar orçado com realizado sem saber de que mês é
       o preço é comparar coisas diferentes.
    3. **BDI e encargos moram no cabeçalho.** O custo direto vive nas linhas; o
       que transforma custo em **preço** é do orçamento inteiro. ORC.2 detalha a
       composição do BDI (`ComposicaoBDI`); aqui fica o percentual resultante,
       que é o que multiplica.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        APROVADO = "aprovado", _("Aprovado")
        SUPERADO = "superado", _("Superado por revisão")
        CANCELADO = "cancelado", _("Cancelado")

    orcamento_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.PROTECT, related_name="orcamentos", verbose_name=_("Obra"),
    )
    descricao = models.CharField(max_length=200, verbose_name=_("Descrição"))
    versao = models.PositiveIntegerField(default=1, verbose_name=_("Versão"))
    orcamento_origem = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="revisoes_geradas",
        verbose_name=_("Versão que esta revisa"),
    )
    base_referencial = models.ForeignKey(
        BaseReferencial, on_delete=models.SET_NULL, null=True, blank=True, related_name="orcamentos",
        verbose_name=_("Base referencial de preço"),
    )
    data_base = models.DateField(
        null=True, blank=True, verbose_name=_("Data-base"),
        help_text=_("Mês de referência dos preços. Copiada da base; sobrevive a ela."),
    )
    regime_encargos = models.CharField(
        max_length=10, choices=BaseReferencial.Regime.choices, default=BaseReferencial.Regime.ONERADO,
        verbose_name=_("Regime de encargos"),
    )
    encargos_sociais_percentual = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Encargos sociais (%)"),
        help_text=_("Incide só sobre mão de obra. Detalhe em ORC.2."),
    )
    bdi_percentual = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("BDI (%)"),
        help_text=_("Percentual resultante. A composição analítica fica em ComposicaoBDI."),
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"),
    )
    # Totais desnormalizados: recalculados por `services.recalcular_orcamento`.
    # Guardados porque a lista de orçamentos e o cockpit precisam do total sem
    # explodir a árvore de itens a cada leitura.
    custo_direto_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Custo direto total"),
    )
    valor_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Valor total (com BDI)"),
    )
    aprovado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Aprovado em"))
    aprovado_por_nome = models.CharField(
        max_length=150, blank=True, verbose_name=_("Aprovado por"),
        help_text=_("Rótulo durável de quem aprovou (não é FK — o registro sobrevive ao usuário)."),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("Orçamento")
        verbose_name_plural = _("Orçamentos")
        ordering = ["obra", "-versao"]
        constraints = [
            # `obra` já é tenant-scoped, então a FK-pai amarra o tenant (mesma
            # convenção dos `unique_together` mantidos na Fase 8.3).
            models.UniqueConstraint(fields=["obra", "versao"], name="orcamento_versao_unica_por_obra"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="orcamento_tenant_status_idx"),
        ]

    def __str__(self):
        return f"{self.descricao} (v{self.versao})"

    @property
    def editavel(self) -> bool:
        """Só rascunho aceita escrita. Aprovado é régua congelada; superado e
        cancelado são história. A API traduz isso em 409, não em 403 — não falta
        permissão, o documento é que não está mais aberto."""
        return self.status == self.Status.RASCUNHO


class ItemOrcado(TenantScopedModel):
    """Linha da planilha — nó da árvore EAP.

    **O snapshot é o ponto.** `descricao`, `unidade`, `custo_unitario`,
    `codigo_referencia` e `data_base_preco` são copiados do
    `catalogo.Item`/base no momento em que a linha é criada e **não seguem** o
    item depois. Um orçamento aprovado em julho não pode mudar de valor porque
    a SINAPI de agosto saiu ou porque alguém corrigiu a descrição no catálogo.
    A FK `item` continua ali para navegar (e para o SCM/SIL casarem o que foi
    comprado com o que foi orçado), mas quem manda no número é o snapshot.

    `etapa` é o que faz o orçado casar com o **aplicado** do SIL, que apropria
    movimentação por `obras.EtapaObra` — mesma dimensão, comparação direta.
    """

    class TipoLinha(models.TextChoices):
        SINTETICO = "sintetico", _("Sintético (agrupador)")
        ANALITICO = "analitico", _("Analítico (custa)")

    item_orcado_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Orçamento"),
    )
    pai = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="filhos",
        verbose_name=_("Linha-pai"),
    )
    codigo_eap = models.CharField(
        max_length=40, blank=True, verbose_name=_("Código EAP"),
        help_text=_("Hierárquico: 1, 1.1, 1.1.2. Recalculado a partir da árvore."),
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem entre irmãos"))
    tipo_linha = models.CharField(
        max_length=10, choices=TipoLinha.choices, default=TipoLinha.ANALITICO,
        verbose_name=_("Tipo de linha"),
    )
    etapa = models.ForeignKey(
        "obras.EtapaObra", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_orcados",
        verbose_name=_("Etapa da obra"),
    )
    item = models.ForeignKey(
        "catalogo.Item", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_orcados",
        verbose_name=_("Item do catálogo"),
    )
    # --- Snapshot (a régua histórica) ---
    descricao = models.CharField(max_length=255, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, blank=True, verbose_name=_("Unidade"))
    quantidade = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"), verbose_name=_("Quantidade"),
    )
    custo_unitario = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"),
        verbose_name=_("Custo unitário direto"),
        help_text=_("Sem BDI. Congelado na data-base do orçamento."),
    )
    fonte_referencia = models.CharField(
        max_length=10, choices=Fonte.choices, blank=True, verbose_name=_("Fonte do preço"),
    )
    codigo_referencia = models.CharField(max_length=30, blank=True, verbose_name=_("Código na fonte"))
    data_base_preco = models.DateField(null=True, blank=True, verbose_name=_("Data-base do preço"))
    # BDI diferenciado (ORC.2): nulo = usa o BDI padrão do orçamento. O TCU
    # admite BDI próprio para fornecimento de equipamentos, onde não cabem a
    # mesma administração central e o mesmo risco de um serviço executado.
    bdi = models.ForeignKey(
        "ComposicaoBDI", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens",
        verbose_name=_("BDI diferenciado"),
    )
    # --- Derivados (services.recalcular_orcamento) ---
    total_custo_direto = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Total (custo direto)"),
    )
    total_com_bdi = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Total (com BDI)"),
    )
    observacao = models.CharField(max_length=255, blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Item orçado")
        verbose_name_plural = _("Itens orçados")
        ordering = ["orcamento", "codigo_eap", "ordem", "item_orcado_id"]
        indexes = [
            models.Index(fields=["orcamento", "pai"], name="orcamento_item_arvore_idx"),
            models.Index(fields=["orcamento", "etapa"], name="orcamento_item_etapa_idx"),
        ]

    def __str__(self):
        return f"{self.codigo_eap} {self.descricao}".strip()

    @property
    def custa(self) -> bool:
        """Linha que entra na soma direta. Sintético tem total, mas é o total
        dos filhos — somá-lo junto com eles contaria duas vezes."""
        return self.tipo_linha == self.TipoLinha.ANALITICO


class RevisaoOrcamento(TenantScopedModel):
    """Por que a régua mudou — aditivo, supressão ou reequilíbrio.

    Não é log genérico: é o documento que justifica a diferença entre duas
    versões aprovadas, que em obra pública precisa de motivo declarado e em obra
    privada é o que responde "por que estourou". Um registro por revisão,
    apontando as duas pontas.
    """

    class Tipo(models.TextChoices):
        ADITIVO = "aditivo", _("Aditivo (acréscimo de escopo)")
        SUPRESSAO = "supressao", _("Supressão (redução de escopo)")
        REEQUILIBRIO = "reequilibrio", _("Reequilíbrio econômico-financeiro")
        ATUALIZACAO = "atualizacao", _("Atualização de preços (nova data-base)")
        CORRECAO = "correcao", _("Correção de erro de orçamento")

    revisao_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="revisoes", verbose_name=_("Nova versão"),
    )
    orcamento_anterior = models.ForeignKey(
        Orcamento, on_delete=models.SET_NULL, null=True, blank=True, related_name="revisoes_originadas",
        verbose_name=_("Versão anterior"),
    )
    numero = models.PositiveIntegerField(default=1, verbose_name=_("Número da revisão"))
    tipo = models.CharField(max_length=13, choices=Tipo.choices, verbose_name=_("Tipo"))
    motivo = models.TextField(verbose_name=_("Motivo"))
    valor_anterior = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Valor anterior"),
    )
    valor_novo = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Valor novo"),
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    criado_por_nome = models.CharField(max_length=150, blank=True, verbose_name=_("Revisado por"))

    class Meta:
        verbose_name = _("Revisão de orçamento")
        verbose_name_plural = _("Revisões de orçamento")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Revisão {self.numero} ({self.get_tipo_display()})"

    @property
    def delta(self) -> Decimal:
        return self.valor_novo - self.valor_anterior


# ---------------------------------------------------------------------------
# ORC.2 — composição analítica, encargos e BDI
# ---------------------------------------------------------------------------
#
# O que separa um orçamento **analítico** de uma lista de preços: cada serviço
# se abre em insumos com coeficiente de produtividade, e o custo unitário passa
# a ter **memória de cálculo** — dá para responder "por que este m³ custa
# R$ 412,80?". É o que a SINAPI publica, o que edital exige e o que o TCU
# audita.
#
# Duas camadas por cima do custo direto, nesta ordem:
#   1. **Encargos sociais** — só sobre mão de obra (onerado × desonerado).
#   2. **BDI** — sobre o custo direto total, transformando custo em preço.


class ComposicaoBDI(TenantScopedModel):
    """BDI analítico pela fórmula do **Acórdão 2622/2013-TCU**.

        BDI = [ (1+AC+S+R+G) × (1+DF) × (1+L) / (1−I) ] − 1

    Guardar as parcelas em vez de só o percentual final é o que permite emitir a
    *composição analítica do BDI* — peça obrigatória em licitação, e a primeira
    coisa que um auditor pede. O percentual resultante é derivado, nunca digitado.

    **IRPJ e CSLL ficam de fora** por vedação expressa do TCU (Acórdãos 325/2007
    e 2622/2013): são tributos sobre o lucro da empresa, não sobre o faturamento
    da obra, e embuti-los no preço faz o contratante pagar o imposto de renda do
    contratado. Por isso não existe campo para eles — a ausência é a regra.

    Um orçamento pode ter mais de um BDI (o TCU admite **BDI diferenciado** para
    fornecimento de equipamentos, onde não cabe a mesma administração central e
    o mesmo risco de um serviço executado). O marcado como `padrao` vale para as
    linhas que não apontam BDI próprio.
    """

    bdi_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="composicoes_bdi",
        verbose_name=_("Orçamento"),
    )
    nome = models.CharField(max_length=120, default="BDI padrão", verbose_name=_("Nome"))
    padrao = models.BooleanField(
        default=True, verbose_name=_("BDI padrão do orçamento"),
        help_text=_("Vale para as linhas que não apontam um BDI próprio."),
    )
    # Parcelas (%) — nomes da fórmula do acórdão.
    administracao_central = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("Administração central (AC) %"),
    )
    seguro = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("Seguro (S) %"),
    )
    risco = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("Risco (R) %"),
    )
    garantia = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("Garantia (G) %"),
    )
    despesas_financeiras = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("Despesas financeiras (DF) %"),
    )
    lucro = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("Lucro (L) %"),
    )
    # Tributos (I) — sobre o faturamento. Separados porque a alíquota de ISS é
    # municipal e a CPRB depende da desoneração da folha; juntá-los num campo só
    # impediria a composição analítica de mostrar de onde veio cada ponto.
    pis = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("PIS %"))
    cofins = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("COFINS %"))
    iss = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("ISS %"))
    cprb = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), verbose_name=_("CPRB %"),
        help_text=_("Contribuição previdenciária sobre receita bruta (regime desonerado)."),
    )
    percentual_calculado = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("BDI resultante (%)"),
        help_text=_("Derivado da fórmula. Não editável."),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Composição de BDI")
        verbose_name_plural = _("Composições de BDI")
        ordering = ["orcamento", "-padrao", "nome"]

    def __str__(self):
        return f"{self.nome} — {self.percentual_calculado}%"

    @property
    def tributos(self) -> Decimal:
        """I da fórmula — a soma das alíquotas sobre faturamento."""
        return self.pis + self.cofins + self.iss + self.cprb


class ItemOrcadoInsumo(TenantScopedModel):
    """Uma linha da **memória de cálculo**: o insumo dentro do serviço orçado.

    Resultado da explosão da composição do `catalogo.Item`, achatada em folhas
    com o coeficiente acumulado. Também é **snapshot** — pelo mesmo motivo da
    linha-pai (`ItemOrcado`): mexer na composição do catálogo depois não pode
    mudar o custo de um orçamento já montado.

    `categoria` existe porque **encargos sociais só incidem sobre mão de obra**.
    Sem distinguir a natureza do insumo, ou se aplica encargo sobre cimento (e o
    orçamento incha), ou não se aplica sobre o pedreiro (e o orçamento fica
    irreal).
    """

    class Categoria(models.TextChoices):
        MATERIAL = "material", _("Material")
        MAO_DE_OBRA = "mao_de_obra", _("Mão de obra")
        EQUIPAMENTO = "equipamento", _("Equipamento")
        OUTRO = "outro", _("Outro")

    insumo_id = models.AutoField(primary_key=True)
    item_orcado = models.ForeignKey(
        ItemOrcado, on_delete=models.CASCADE, related_name="insumos", verbose_name=_("Linha orçada"),
    )
    item = models.ForeignKey(
        "catalogo.Item", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name=_("Insumo do catálogo"),
    )
    descricao = models.CharField(max_length=255, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, blank=True, verbose_name=_("Unidade"))
    categoria = models.CharField(
        max_length=12, choices=Categoria.choices, default=Categoria.MATERIAL, verbose_name=_("Categoria"),
    )
    coeficiente = models.DecimalField(
        max_digits=16, decimal_places=6, default=Decimal("0"), verbose_name=_("Coeficiente"),
        help_text=_("Consumo por unidade do serviço, já acumulado pela explosão."),
    )
    custo_unitario = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"), verbose_name=_("Custo unitário do insumo"),
    )
    custo_no_item = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"),
        verbose_name=_("Custo no serviço"),
        help_text=_("coeficiente × custo unitário, com encargos quando é mão de obra."),
    )

    class Meta:
        verbose_name = _("Insumo do item orçado")
        verbose_name_plural = _("Insumos dos itens orçados")
        ordering = ["item_orcado", "categoria", "insumo_id"]
        indexes = [
            models.Index(fields=["item_orcado"], name="orcamento_insumo_linha_idx"),
        ]

    def __str__(self):
        return f"{self.descricao} ×{self.coeficiente}"


# ---------------------------------------------------------------------------
# ORC.3 — cronograma físico-financeiro (a curva S)
# ---------------------------------------------------------------------------


class ParcelaEtapa(TenantScopedModel):
    """Quanto de uma etapa cai em cada mês — a célula do cronograma.

    O cronograma físico-financeiro é uma grade: linhas são etapas, colunas são
    meses, células são percentuais. A **curva S** é o acumulado dessa grade no
    tempo, e o nome vem do formato — obra começa devagar, acelera no miolo e
    desacelera no acabamento.

    Guardamos **percentual e valor**: o percentual é o que o planejador digita
    e o que sobrevive a uma mudança de preço; o valor é derivado
    (`controle.recalcular_parcelas`) e existe para a leitura não precisar
    recalcular a grade inteira a cada abertura de tela.

    `etapa` nula significa "o orçamento inteiro" — útil para obra pequena, que
    não vale quebrar em etapas só para ter cronograma.
    """

    parcela_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="parcelas", verbose_name=_("Orçamento"),
    )
    etapa = models.ForeignKey(
        "obras.EtapaObra", on_delete=models.CASCADE, null=True, blank=True,
        related_name="parcelas_orcamento", verbose_name=_("Etapa"),
    )
    competencia = models.DateField(
        verbose_name=_("Competência"), help_text=_("Dia 1 do mês da parcela."),
    )
    percentual = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("Percentual do mês"),
    )
    valor_previsto = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Valor previsto"),
    )
    observacao = models.CharField(max_length=255, blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Parcela do cronograma")
        verbose_name_plural = _("Parcelas do cronograma")
        ordering = ["orcamento", "etapa", "competencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["orcamento", "etapa", "competencia"],
                name="orcamento_parcela_unica_por_mes",
            ),
            # A de cima não cobre `etapa IS NULL`: no Postgres NULL ≠ NULL, então
            # duas parcelas "do orçamento inteiro" no mesmo mês passariam. Esta
            # constraint parcial fecha o caso, sem depender do `nulls_distinct`
            # (que exige PG 15+).
            models.UniqueConstraint(
                fields=["orcamento", "competencia"],
                condition=models.Q(etapa__isnull=True),
                name="orcamento_parcela_unica_sem_etapa",
            ),
        ]
        indexes = [
            models.Index(fields=["orcamento", "competencia"], name="orcamento_parcela_mes_idx"),
        ]

    def __str__(self):
        return f"{self.competencia:%m/%Y} — {self.percentual}%"


# ---------------------------------------------------------------------------
# ORC.4 — orçamento paramétrico (CUB) e os quadros da NBR 12721
# ---------------------------------------------------------------------------
#
# Duas coisas diferentes que compartilham o mesmo vocabulário de áreas:
#
# 1. **Paramétrico** — estimativa por m², feita na *viabilidade*, antes de
#    existir planilha analítica. É o que responde "esse terreno comporta um
#    prédio que se paga?" com a informação que existe nessa hora: área e padrão.
# 2. **NBR 12721** — os oito quadros que instruem o **registro de incorporação**
#    em cartório. Não é relatório gerencial: é condição legal para vender
#    unidade na planta (Lei 4.591/64), e todo o resto da documentação da
#    incorporação deriva desses números.
#
# O elo entre eles é a **área equivalente de construção**: área real convertida
# para "m² de custo padrão" por coeficientes (garagem e área descoberta custam
# menos que apartamento). É sobre a equivalente que o CUB multiplica e é por ela
# que o custo global se rateia entre as unidades.


class ProjetoPadrao(models.TextChoices):
    """Projetos-padrão da NBR 12721 — a chave do CUB.

    O CUB é publicado mensalmente pelos SINDUSCON estaduais **por
    projeto-padrão**: um R-1 (residência unifamiliar) e um R-16 (prédio de 16
    andares) têm custos por m² bem diferentes. Aplicar CUB de padrão normal num
    empreendimento de padrão alto subestima o custo global e distorce o rateio
    entre as unidades — por isso o padrão é campo obrigatório, não observação.
    """

    R1_BAIXO = "r1_b", _("R-1 Baixo")
    R1_NORMAL = "r1_n", _("R-1 Normal")
    R1_ALTO = "r1_a", _("R-1 Alto")
    PP4_BAIXO = "pp4_b", _("PP-4 Baixo")
    PP4_NORMAL = "pp4_n", _("PP-4 Normal")
    R8_BAIXO = "r8_b", _("R-8 Baixo")
    R8_NORMAL = "r8_n", _("R-8 Normal")
    R8_ALTO = "r8_a", _("R-8 Alto")
    R16_NORMAL = "r16_n", _("R-16 Normal")
    R16_ALTO = "r16_a", _("R-16 Alto")
    PIS = "pis", _("PIS — Projeto de Interesse Social")
    RP1Q = "rp1q", _("RP-1Q — Residência Popular")
    CAL8_NORMAL = "cal8_n", _("CAL-8 Normal — Comercial Andares Livres")
    CAL8_ALTO = "cal8_a", _("CAL-8 Alto — Comercial Andares Livres")
    CSL8_NORMAL = "csl8_n", _("CSL-8 Normal — Comercial Salas e Lojas")
    CSL8_ALTO = "csl8_a", _("CSL-8 Alto — Comercial Salas e Lojas")
    CSL16_NORMAL = "csl16_n", _("CSL-16 Normal")
    CSL16_ALTO = "csl16_a", _("CSL-16 Alto")
    GI = "gi", _("GI — Galpão Industrial")


class ParametroObra(TenantScopedModel):
    """Orçamento **paramétrico**: área equivalente × CUB + adicionais.

    Vive pendurado na **obra**, não no `Orcamento`, porque acontece antes dele:
    na viabilidade ainda não há planilha para pendurar nada. Quando o analítico
    fica pronto, os dois convivem — e a diferença entre eles é uma informação
    valiosa (o paramétrico errou para mais ou para menos?), não um conflito.

    **O CUB não cobre tudo.** A própria NBR lista o que fica de fora: fundações
    especiais, elevadores, instalações especiais, projetos, licenças, terreno,
    lucro do incorporador. Por isso os adicionais são campo explícito — um
    paramétrico só com CUB × área subestima sistematicamente, e é assim que
    incorporação entra em obra sem caixa.
    """

    parametro_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="parametros_orcamento",
        verbose_name=_("Obra"),
    )
    descricao = models.CharField(max_length=200, verbose_name=_("Descrição"))
    projeto_padrao = models.CharField(
        max_length=8, choices=ProjetoPadrao.choices, verbose_name=_("Projeto-padrão"),
    )
    cub_m2 = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), verbose_name=_("CUB (R$/m²)"),
        help_text=_("Publicado pelo SINDUSCON do estado, para este projeto-padrão."),
    )
    cub_uf = models.CharField(max_length=2, blank=True, verbose_name=_("UF do CUB"))
    cub_mes = models.DateField(
        null=True, blank=True, verbose_name=_("Mês do CUB"),
        help_text=_("Data-base da publicação — o CUB é mensal."),
    )
    area_real = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), verbose_name=_("Área real (m²)"),
    )
    area_equivalente = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área equivalente (m²)"),
        help_text=_("É sobre ela que o CUB multiplica, não sobre a área real."),
    )
    percentual_adicionais = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Adicionais (%)"),
        help_text=_("Fundação especial, elevador, projetos — o que o CUB não cobre."),
    )
    valor_adicionais = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Adicionais (R$)"), help_text=_("Adicionais conhecidos em valor fechado."),
    )
    custo_estimado = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Custo estimado"), help_text=_("Derivado — não editável."),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Orçamento paramétrico")
        verbose_name_plural = _("Orçamentos paramétricos")
        ordering = ["obra", "-criado_em"]

    def __str__(self):
        return f"{self.descricao} ({self.get_projeto_padrao_display()})"


class PavimentoObra(TenantScopedModel):
    """Um pavimento e suas áreas — insumo do **Quadro I** da NBR 12721.

    As áreas se separam em três naturezas porque custam diferente, e a norma
    converte cada uma em área equivalente por um coeficiente próprio:
    o pavimento-tipo é o padrão (coeficiente 1), garagem/área de padrão
    diferente custa menos, área descoberta custa menos ainda.
    """

    pavimento_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="pavimentos", verbose_name=_("Obra"),
    )
    nome = models.CharField(max_length=120, verbose_name=_("Pavimento"))
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    area_coberta_padrao = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área coberta padrão (m²)"),
    )
    area_coberta_diferente = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área coberta de padrão diferente (m²)"),
    )
    coeficiente_coberta_diferente = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.5000"),
        verbose_name=_("Coeficiente da área de padrão diferente"),
    )
    area_descoberta = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área descoberta (m²)"),
    )
    coeficiente_descoberta = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.3000"),
        verbose_name=_("Coeficiente da área descoberta"),
    )

    class Meta:
        verbose_name = _("Pavimento (NBR 12721)")
        verbose_name_plural = _("Pavimentos (NBR 12721)")
        ordering = ["obra", "ordem", "pavimento_id"]
        constraints = [
            models.UniqueConstraint(fields=["obra", "nome"], name="orcamento_pavimento_unico"),
        ]

    def __str__(self):
        return self.nome

    @property
    def area_real(self) -> Decimal:
        return self.area_coberta_padrao + self.area_coberta_diferente + self.area_descoberta

    @property
    def area_equivalente(self) -> Decimal:
        return (
            self.area_coberta_padrao
            + self.area_coberta_diferente * self.coeficiente_coberta_diferente
            + self.area_descoberta * self.coeficiente_descoberta
        )


class UnidadeAutonoma(TenantScopedModel):
    """Uma unidade autônoma (apartamento, loja, vaga) — **Quadros II e IV**.

    Guarda dois números que **não são a mesma coisa**, e confundi-los é erro
    clássico de incorporação:

    - **`coeficiente_proporcionalidade`** — o rateio do **custo** da obra entre
      as unidades, derivado da área equivalente. É o termo que a NBR usa nos
      quadros I a VIII, e é o que responde "quanto desta obra é desta unidade".
    - **`fracao_ideal`** — a quota **do terreno e das coisas de uso comum** que
      cabe à unidade. É conceito do direito civil, entra na matrícula e pode ser
      definida por outro critério que não a área equivalente.

    Frequentemente têm o mesmo valor, e é exatamente por isso que um campo só
    passaria despercebido até o dia em que não têm — quando o registro sai
    errado e a incorporação trava no cartório.
    """

    unidade_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="unidades_autonomas",
        verbose_name=_("Obra"),
    )
    pavimento = models.ForeignKey(
        PavimentoObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="unidades", verbose_name=_("Pavimento"),
    )
    designacao = models.CharField(max_length=60, verbose_name=_("Designação"))  # "Apto 101"
    tipo = models.CharField(max_length=60, blank=True, verbose_name=_("Tipo"))  # "2 dormitórios"
    area_privativa_padrao = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área privativa padrão (m²)"),
    )
    area_privativa_diferente = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área privativa de padrão diferente (m²)"),
    )
    coeficiente_privativa_diferente = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.5000"),
        verbose_name=_("Coeficiente da área privativa diferente"),
    )
    area_uso_comum = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Área de uso comum (m²)"),
    )
    coeficiente_proporcionalidade = models.DecimalField(
        max_digits=12, decimal_places=8, default=Decimal("0"),
        verbose_name=_("Coeficiente de proporcionalidade"),
        help_text=_("Rateio do custo. Derivado da área equivalente."),
    )
    fracao_ideal = models.DecimalField(
        max_digits=12, decimal_places=8, default=Decimal("0"),
        verbose_name=_("Fração ideal do terreno"),
        help_text=_("Quota legal do terreno — NÃO é o coeficiente de proporcionalidade."),
    )
    custo_estimado = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"),
        verbose_name=_("Custo da unidade"), help_text=_("Quadro IV-A. Derivado."),
    )

    class Meta:
        verbose_name = _("Unidade autônoma (NBR 12721)")
        verbose_name_plural = _("Unidades autônomas (NBR 12721)")
        ordering = ["obra", "pavimento", "designacao"]
        constraints = [
            models.UniqueConstraint(fields=["obra", "designacao"], name="orcamento_unidade_unica"),
        ]

    def __str__(self):
        return self.designacao

    @property
    def area_real_privativa(self) -> Decimal:
        return self.area_privativa_padrao + self.area_privativa_diferente

    @property
    def area_equivalente_privativa(self) -> Decimal:
        return (
            self.area_privativa_padrao
            + self.area_privativa_diferente * self.coeficiente_privativa_diferente
        )

    @property
    def area_real_total(self) -> Decimal:
        return self.area_real_privativa + self.area_uso_comum


class MemorialNBR(TenantScopedModel):
    """Linha de um dos **quadros descritivos** — V, VI, VII e VIII.

    Estes quatro quadros não são cálculo: são **memoriais descritivos**
    preenchidos pelo projetista (informações gerais do empreendimento,
    equipamentos, acabamentos das áreas privativas e das comuns). Modelá-los
    como linhas de texto é o que eles são — inventar fórmula aqui produziria
    documento errado num processo de cartório.
    """

    class Quadro(models.TextChoices):
        V = "v", _("Quadro V — Informações gerais")
        VI = "vi", _("Quadro VI — Memorial dos equipamentos")
        VII = "vii", _("Quadro VII — Acabamentos das dependências de uso privado")
        VIII = "viii", _("Quadro VIII — Acabamentos das dependências de uso comum")

    memorial_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="memoriais_nbr", verbose_name=_("Obra"),
    )
    quadro = models.CharField(max_length=4, choices=Quadro.choices, verbose_name=_("Quadro"))
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    dependencia = models.CharField(
        max_length=120, blank=True, verbose_name=_("Dependência / item"),
    )
    descricao = models.TextField(verbose_name=_("Descrição"))

    class Meta:
        verbose_name = _("Memorial da NBR 12721")
        verbose_name_plural = _("Memoriais da NBR 12721")
        ordering = ["obra", "quadro", "ordem", "memorial_id"]

    def __str__(self):
        return f"{self.get_quadro_display()} — {self.dependencia or self.descricao[:40]}"
