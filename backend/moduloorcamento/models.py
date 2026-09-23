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
entitlement `orcamento`** na API, e a **escrita só acontece pela mão do dono da
plataforma**: o comando `manage.py importar_base_referencial` desde a ORC.0 e,
desde a ORC.8, o botão de carga (`is_platform_admin`), que roda o mesmo motor.
Nenhum tenant escreve aqui por endpoint algum.

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

from nucleo.tenancy import Excluivel, TenantScopedModel


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
    # ORC.8b — a companhia estadual de saneamento da Bahia. É a primeira fonte
    # setorial da lista (as outras são de obra em geral) e a única que publica
    # **só em PDF**; as duas coisas estão documentadas em `embasa.py`.
    EMBASA = "embasa", _("EMBASA (BA)")
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
        # ORC.8 — as abas `ISE`/`CSE` do arquivo nacional: preço **sem encargos
        # sociais**. Não é "onerado com percentual zero", é outra coisa: é o
        # custo puro sobre o qual se aplica um quadro de encargos próprio, que é
        # o que o ORC.7 entregou. Sem este regime, quem quisesse usar o quadro
        # analítico teria de partir de um preço que já embute encargo da Caixa —
        # e aplicar encargo sobre encargo é contar duas vezes.
        SEM_ENCARGOS = "sem", _("Sem encargos")
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
    # ORC.8b — o eixo que uma fonte pode ter **além** de UF, mês e regime, e que
    # nasceu de um fato da EMBASA: para o mesmo semestre e o mesmo regime ela
    # publica seis tabelas com os **mesmos 6.992 códigos e preços diferentes**,
    # uma por convenção coletiva (`expansao-sintracom`, `expansao-sintepav`…),
    # porque a leis sociais muda com o sindicato da região. Sem este campo na
    # chave, as seis colidiriam e a última carga sobrescreveria as cinco
    # anteriores em silêncio — o `update_or_create` faria exatamente o que lhe
    # pedissem, e o orçamento ficaria com o preço de outra região.
    #
    # Vazio em SINAPI, ORSE e nas demais: lá a publicação já é única na chave, e
    # forçá-las a inventar uma variante seria pedir que respondessem uma pergunta
    # que ninguém lhes fez.
    variante = models.CharField(
        max_length=60, blank=True, verbose_name=_("Variante"),
        help_text=_(
            "Eixo extra de identidade da fonte (EMBASA: escopo + convenção "
            "coletiva). Vazio quando a fonte publica uma tabela por UF/mês/regime."
        ),
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
    # ORC.8 — de onde este preço veio, literalmente. É o que a auditoria pede
    # quando pergunta "por que R$ 412,80?": a resposta completa é a publicação
    # **e** o artefato de onde ela foi lida. Fica vazio na importação por
    # arquivo local (o comando da ORC.0), porque ali a origem é a máquina de
    # quem rodou e inventar uma URL seria pior que não ter nenhuma.
    url_origem = models.CharField(
        max_length=500, blank=True, verbose_name=_("URL de origem"),
        help_text=_("Endereço do artefato oficial de onde a publicação foi lida."),
    )

    class Meta:
        verbose_name = _("Base referencial")
        verbose_name_plural = _("Bases referenciais")
        ordering = ["-mes_referencia", "fonte", "uf"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "uf", "mes_referencia", "regime_encargos", "variante"],
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
        # A variante entra no rótulo automático porque sem ela duas publicações
        # que **são** diferentes ficariam com o mesmo nome na tela — e escolher
        # a tabela errada de preço de saneamento numa lista de seis rótulos
        # idênticos é o erro que o campo existe para evitar.
        if self.variante:
            partes.append(f"· {self.variante}")
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
            # O `bases-resumo/` precisa, por publicação, de quantos insumos
            # vieram classificados e de quais classes a fonte usou. Sem índice,
            # a resposta custava uma varredura dos 5 milhões de insumos (~0,7 s);
            # com ele, a mesma agregação sai em ~0,37 s e cabe num índice de
            # 35 MB. **Parcial de propósito:** as duas perguntas só existem para
            # `tipo="insumo"` — incluir as composições dobraria o índice para
            # 131 MB sem responder nada a mais.
            models.Index(
                fields=["base", "grupo"],
                condition=models.Q(tipo="insumo"),
                name="orcamento_ref_classe_idx",
            ),
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
# ORC.8 — a carga da base oficial: de onde ela vem e o que já veio
# ---------------------------------------------------------------------------
#
# Continuam sendo tabelas de plataforma, sem tenant e sem RLS, pela mesma razão
# das três acima: descrevem dado público e a operação de quem o publica aqui
# dentro. O que muda é quem escreve — não mais só o comando, mas o botão do
# `is_platform_admin`. Desenho em docs/modulos/moduloorcamento.md §12.7.


class FonteOficial(models.Model):
    """**De onde** a publicação de uma fonte é baixada — e o desenho inteiro
    desta tabela existe por causa de um fato: a URL da Caixa já mudou uma vez.

    O padrão por UF morreu em 12/2024, e quem tivesse o endereço compilado no
    código teria descoberto isso com um deploy no meio do mês. Com o template
    numa caixa de texto, o conserto é de trinta segundos e é feito por quem
    percebeu o problema — que é o dono da plataforma, não quem tem acesso ao
    repositório.

    O template aceita `{ano}` (4 dígitos), `{mes}` (2 dígitos), `{ano_mes}`
    (AAAAMM), `{uf}` e `{regime}`. Os dois últimos existem para o formato antigo
    (1 ZIP por UF × regime); no nacional eles simplesmente não aparecem no
    template e a carga faz um download só.
    """

    fonte_id = models.AutoField(primary_key=True)
    fonte = models.CharField(
        max_length=10, choices=Fonte.choices, unique=True, verbose_name=_("Fonte"),
    )
    template_url = models.CharField(
        max_length=500, blank=True, verbose_name=_("Template da URL"),
        help_text=_("Aceita {ano}, {mes}, {ano_mes}, {uf} e {regime}."),
    )
    # O WAF da Caixa (Azion) recusa hit frio no arquivo: quer sessão aquecida e
    # `Referer` da página de downloads. É janela de protocolo de terceiro (§5.6
    # do planos.py) — não somos nós que escolhemos —, mas o **endereço** muda com
    # o site deles, então é dado, não constante.
    pagina_referencia = models.CharField(
        max_length=500, blank=True, verbose_name=_("Página de referência"),
        help_text=_("Página pública visitada antes do download (aquece a sessão e vira Referer)."),
    )
    ativa = models.BooleanField(
        default=True, verbose_name=_("Ativa"),
        help_text=_("Desligada, a fonte não entra na varredura mensal — o botão continua valendo."),
    )
    # Dia do mês em que a varredura tenta esta fonte. 0 desliga o agendamento e
    # deixa só o botão: o botão resolve *hoje*, o agendamento evita que "alguém
    # esqueceu" vire orçamento nascendo com preço vencido.
    dia_do_mes = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Dia do mês para tentar"),
        help_text=_("0 = não agendar (só carga manual)."),
    )
    # Quantos meses a publicação da fonte costuma atrasar em relação ao mês
    # corrente. A SINAPI publica o mês M por volta do dia 10 de M+1, então
    # tentar `hoje` no dia 5 é pedir 404 garantido.
    defasagem_meses = models.PositiveSmallIntegerField(
        default=1, verbose_name=_("Defasagem de publicação (meses)"),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    atualizada_em = models.DateTimeField(auto_now=True, verbose_name=_("Atualizada em"))

    class Meta:
        verbose_name = _("Fonte oficial")
        verbose_name_plural = _("Fontes oficiais")
        ordering = ["fonte"]

    def __str__(self):
        return f"{self.get_fonte_display()} → {self.template_url or '(sem template)'}"

    def url_para(self, competencia, uf: str = "", regime: str = "") -> str:
        """Resolve o template para uma competência. Erro de template vira texto
        vazio, não exceção: URL malformada é problema de quem a escreveu e a
        carga sabe dizer isso melhor do que um `KeyError` no log do worker."""
        if not self.template_url:
            return ""
        try:
            return self.template_url.format(
                ano=f"{competencia.year:04d}", mes=f"{competencia.month:02d}",
                ano_mes=f"{competencia.year:04d}{competencia.month:02d}",
                uf=uf.upper(), regime=regime,
            )
        except (KeyError, IndexError, ValueError):
            return ""


class CargaBase(models.Model):
    """Uma **corrida** de carga: a tentativa de trazer a publicação de um mês.

    Guardada mesmo quando falha, e principalmente quando falha. Sem esta linha o
    botão seria um botão que às vezes não faz nada e ninguém sabe por quê — a
    diferença entre "o WAF cortou", "o mês ainda não saiu" e "o layout mudou" só
    existe se alguém a escrever no momento em que ela é conhecida.

    O estado `AGUARDANDO` é o que carrega a decisão do D112 para esta porta:
    classe que não sabemos ler **para** a carga antes de gravar e devolve a
    pergunta a quem a disparou, com a lista do que não soube fazer. O caminho de
    volta é a mesma corrida com `aceitar_sem_classe`.
    """

    class Estado(models.TextChoices):
        PENDENTE = "pendente", _("Na fila")
        BAIXANDO = "baixando", _("Baixando")
        LENDO = "lendo", _("Lendo o arquivo")
        GRAVANDO = "gravando", _("Gravando")
        AGUARDANDO = "aguardando", _("Aguardando decisão")
        CONCLUIDA = "concluida", _("Concluída")
        FALHOU = "falhou", _("Falhou")

    class Origem(models.TextChoices):
        DOWNLOAD = "download", _("Download do site oficial")
        UPLOAD = "upload", _("Arquivo enviado")

    carga_id = models.AutoField(primary_key=True)
    fonte = models.CharField(max_length=10, choices=Fonte.choices, verbose_name=_("Fonte"))
    competencia = models.DateField(
        verbose_name=_("Competência"), help_text=_("Dia 1 do mês da publicação."),
    )
    origem = models.CharField(
        max_length=10, choices=Origem.choices, default=Origem.DOWNLOAD, verbose_name=_("Origem"),
    )
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDENTE, verbose_name=_("Estado"),
    )
    # O que a corrida está fazendo agora, em uma frase. É o que a tela mostra
    # enquanto o job roda: "baixando (7,2 MB)", "lendo a aba ICD", "gravando SP".
    etapa = models.CharField(max_length=200, blank=True, verbose_name=_("Etapa"))
    url_origem = models.CharField(max_length=500, blank=True, verbose_name=_("URL de origem"))
    arquivo_nome = models.CharField(max_length=255, blank=True, verbose_name=_("Arquivo"))
    # O plano B guarda o artefato enviado, e guardar é a escolha: a publicação é
    # a justificativa de preço de todo orçamento com aquela data-base, e no dia
    # em que alguém contestar um valor a pergunta será "de que arquivo veio?".
    # No caminho do download essa resposta é a `url_origem`; no upload, o
    # arquivo é a única resposta que existe.
    arquivo = models.FileField(
        upload_to="cargas_base/", blank=True, verbose_name=_("Arquivo enviado"),
    )
    bytes_lidos = models.BigIntegerField(default=0, verbose_name=_("Bytes lidos"))
    # **Resumo antes de gravar**, não conferência linha a linha: a importação é
    # idempotente e conferir 800 mil linhas seria teatro. O resumo diz quantos
    # insumos, composições e linhas analíticas entram, por publicação — e é aí
    # que se percebe o arquivo errado.
    somente_resumo = models.BooleanField(
        default=False, verbose_name=_("Só o resumo"),
        help_text=_("Lê e conta, não grava — o equivalente ao --dry-run do comando."),
    )
    aceitar_sem_classe = models.BooleanField(
        default=False, verbose_name=_("Aceitar classe sem tradução"),
    )
    resumo = models.JSONField(default=dict, blank=True, verbose_name=_("Resumo"))
    erro = models.TextField(blank=True, verbose_name=_("Erro"))
    total_publicacoes = models.PositiveIntegerField(default=0, verbose_name=_("Publicações"))
    total_insumos = models.PositiveIntegerField(default=0, verbose_name=_("Insumos"))
    total_composicoes = models.PositiveIntegerField(default=0, verbose_name=_("Composições"))
    total_analitica = models.PositiveIntegerField(default=0, verbose_name=_("Linhas analíticas"))
    solicitada_por_nome = models.CharField(
        max_length=150, blank=True, verbose_name=_("Solicitada por"),
    )
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criada em"))
    atualizada_em = models.DateTimeField(auto_now=True, verbose_name=_("Atualizada em"))
    concluida_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Concluída em"))

    class Meta:
        verbose_name = _("Carga de base oficial")
        verbose_name_plural = _("Cargas de base oficial")
        ordering = ["-criada_em"]
        indexes = [
            models.Index(fields=["fonte", "-competencia"], name="orcamento_carga_fonte_idx"),
            models.Index(fields=["estado"], name="orcamento_carga_estado_idx"),
        ]

    def __str__(self):
        return f"{self.get_fonte_display()} {self.competencia:%m/%Y} — {self.get_estado_display()}"

    @property
    def em_andamento(self) -> bool:
        return self.estado in {
            self.Estado.PENDENTE, self.Estado.BAIXANDO,
            self.Estado.LENDO, self.Estado.GRAVANDO,
        }


class AnaliticaNacional(models.Model):
    """A composição analítica guardada **uma vez por fonte + mês**, não por
    publicação — e este é o desenho que torna a carga nacional possível.

    O coeficiente da SINAPI é nacional: o que varia entre São Paulo e o Acre é o
    **preço** do insumo, não quantos quilos de cimento entram no metro cúbico de
    concreto. Amarrada a cada publicação, a analítica seria replicada 54× (27 UFs
    × 2 regimes) — cerca de 3,6 milhões de linhas por mês, ~69 milhões nos 19
    meses desde 01/2025. Guardada aqui, são ~67 mil por mês.

    Convive com `ComposicaoReferenciaItem` sem ambiguidade porque **quem lê é uma
    função só** (`services.componentes_da_composicao`): a analítica da própria
    publicação, quando existe, vence; na ausência dela, esta tabela responde. As
    publicações do formato antigo (1 ZIP por UF, com analítica própria) seguem
    exatamente como estavam.
    """

    linha_id = models.BigAutoField(primary_key=True)
    fonte = models.CharField(max_length=10, choices=Fonte.choices, verbose_name=_("Fonte"))
    competencia = models.DateField(verbose_name=_("Competência"))
    codigo_composicao = models.CharField(max_length=30, verbose_name=_("Código da composição"))
    codigo_item = models.CharField(max_length=30, verbose_name=_("Código do item"))
    coeficiente = models.DecimalField(
        max_digits=14, decimal_places=5, verbose_name=_("Coeficiente"),
    )
    # Descrição, unidade e tipo do filho viajam com a linha porque a analítica é
    # a fonte mais rica do arquivo: ela declara itens que a aba de preço pode não
    # trazer (insumo sem pesquisa naquela UF). Sem estes campos, a carga não
    # saberia criar o filho faltante e o coeficiente ficaria apontando para o
    # nada — que é o mesmo buraco que o `_gravar_analitica` do comando já fecha.
    descricao_item = models.CharField(max_length=500, blank=True, verbose_name=_("Descrição do item"))
    unidade_item = models.CharField(max_length=20, blank=True, verbose_name=_("Unidade do item"))
    tipo_item = models.CharField(
        max_length=12, choices=InsumoReferencia.Tipo.choices,
        default=InsumoReferencia.Tipo.INSUMO, verbose_name=_("Tipo do item"),
    )
    descricao_composicao = models.CharField(
        max_length=500, blank=True, verbose_name=_("Descrição da composição"),
    )
    unidade_composicao = models.CharField(
        max_length=20, blank=True, verbose_name=_("Unidade da composição"),
    )

    class Meta:
        verbose_name = _("Linha analítica nacional")
        verbose_name_plural = _("Linhas analíticas nacionais")
        ordering = ["fonte", "-competencia", "codigo_composicao", "codigo_item"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "competencia", "codigo_composicao", "codigo_item"],
                name="orcamento_analitica_nacional_unica",
            ),
        ]
        indexes = [
            models.Index(
                fields=["fonte", "competencia", "codigo_composicao"],
                name="orcamento_analitica_pai_idx",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_composicao} ⊃ {self.codigo_item} ×{self.coeficiente}"


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


class Orcamento(TenantScopedModel, Excluivel):
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
        """As naturezas em que a SINAPI separa o custo de uma composição.

        `ENCARGOS_COMPLEMENTARES` (EPI, exame, alimentação, transporte) é classe
        própria e não "material": ela acompanha a hora de mão de obra, mas **não
        recebe encargo social por cima** — é complemento do custo do
        trabalhador, não salário. Somá-la ao material escondia isso.
        """

        MATERIAL = "material", _("Material")
        MAO_DE_OBRA = "mao_de_obra", _("Mão de obra")
        EQUIPAMENTO = "equipamento", _("Equipamento")
        ENCARGOS_COMPLEMENTARES = "encargos_complementares", _("Encargos complementares")
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
        max_length=24, choices=Categoria.choices, default=Categoria.MATERIAL, verbose_name=_("Categoria"),
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


# ---------------------------------------------------------------------------
# ORC.5b — bancos de preço do tenant, importação e reprecificação
# ---------------------------------------------------------------------------
#
# A base referencial do topo deste arquivo é pública e global (§11.1). Daqui para
# baixo é o espelho **da empresa**: mesmo formato (publicação → itens →
# componentes), só que `TenantScopedModel` com RLS fail-closed padrão.
#
# São tabelas separadas em vez de uma só com `tenant` nulável, de propósito. Um
# `tenant IS NULL OR tenant = :meu` na política RLS transformaria a trava
# fail-closed — a defesa que impede vazamento entre empresas — numa política com
# exceção, e exceção em política de isolamento é o tipo de detalhe que passa
# despercebido na revisão seguinte. O custo é duplicar busca e adoção; o ganho é
# que a regra do projeto continua valendo sem asterisco.
#
# Desenho e decisões de rumo em docs/modulos/moduloorcamento.md §12.2.


class BancoPreco(TenantScopedModel):
    """Base de preço **da empresa**: a tabela da prefeitura, o banco histórico.

    É da empresa **com obra opcional**, não da obra. A tabela de uma prefeitura
    serve todas as obras daquela cidade, e amarrá-la a uma obra obrigaria a
    reimportar a mesma planilha por obra — multiplicando linhas idênticas e
    criando divergência silenciosa quando uma cópia é corrigida e a outra não.

    `travado` é a trava contra edição por engano. Banco conferido é régua: quem
    orça confia no número, e uma correção acidental num coeficiente contamina
    todo orçamento montado a partir dele. Destravar é explícito e fica registrado.
    """

    class Origem(models.TextChoices):
        IMPORTADA = "importada", _("Importada de arquivo/API")
        PROPRIA = "propria", _("Montada na empresa")

    banco_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    descricao = models.TextField(blank=True, verbose_name=_("Descrição"))
    fonte = models.CharField(
        max_length=10, choices=Fonte.choices, default=Fonte.PROPRIA, verbose_name=_("Fonte"),
    )
    uf = models.CharField(max_length=2, blank=True, verbose_name=_("UF"))
    mes_referencia = models.DateField(
        null=True, blank=True, verbose_name=_("Mês de referência (data-base)"),
        help_text=_("Data-base dos preços deste banco. Vazio = sem data-base declarada."),
    )
    regime_encargos = models.CharField(
        max_length=10, choices=BaseReferencial.Regime.choices,
        default=BaseReferencial.Regime.NAO_SE_APLICA, verbose_name=_("Regime de encargos"),
    )
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bancos_preco", verbose_name=_("Obra (opcional)"),
        help_text=_("Marque só quando o banco existir por causa de uma obra específica."),
    )
    origem = models.CharField(
        max_length=10, choices=Origem.choices, default=Origem.PROPRIA, verbose_name=_("Origem"),
    )
    travado = models.BooleanField(
        default=False, verbose_name=_("Travado"),
        help_text=_("Travado = somente leitura. Protege o banco conferido de edição acidental."),
    )
    travado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Travado em"))
    travado_por_nome = models.CharField(max_length=150, blank=True, verbose_name=_("Travado por"))
    total_itens = models.PositiveIntegerField(default=0, verbose_name=_("Total de itens"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("Banco de preço da empresa")
        verbose_name_plural = _("Bancos de preço da empresa")
        ordering = ["-mes_referencia", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="orcamento_banco_nome_unico"),
        ]
        indexes = [
            models.Index(fields=["tenant", "ativo"], name="orcamento_banco_ativo_idx"),
        ]

    def __str__(self):
        return self.rotulo_automatico()

    def rotulo_automatico(self) -> str:
        partes = [self.nome]
        if self.uf:
            partes.append(self.uf)
        if self.mes_referencia:
            partes.append(self.mes_referencia.strftime("%m/%Y"))
        return " ".join(partes)

    @property
    def editavel(self) -> bool:
        return not self.travado


class PastaComposicao(TenantScopedModel):
    """Agrupamento nomeado dentro de um banco — "Estrutura", "Obra Alfa", "Padrão".

    Organização, não hierarquia de custo: pasta não soma nada. Existe porque um
    banco com mil composições sem agrupamento é impossível de navegar.
    """

    pasta_id = models.AutoField(primary_key=True)
    banco = models.ForeignKey(
        BancoPreco, on_delete=models.CASCADE, related_name="pastas", verbose_name=_("Banco"),
    )
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pastas_composicao", verbose_name=_("Obra (opcional)"),
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))

    class Meta:
        verbose_name = _("Pasta de composições")
        verbose_name_plural = _("Pastas de composições")
        ordering = ["banco", "ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["banco", "nome"], name="orcamento_pasta_nome_unica"),
        ]

    def __str__(self):
        return self.nome


class ItemBancoPreco(TenantScopedModel):
    """Linha de um banco da empresa — mesmo contrato do `InsumoReferencia`."""

    item_banco_id = models.AutoField(primary_key=True)
    banco = models.ForeignKey(
        BancoPreco, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Banco"),
    )
    pasta = models.ForeignKey(
        PastaComposicao, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="itens", verbose_name=_("Pasta"),
    )
    codigo = models.CharField(max_length=30, verbose_name=_("Código"))
    descricao = models.CharField(max_length=500, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, verbose_name=_("Unidade"))
    tipo = models.CharField(
        max_length=12, choices=InsumoReferencia.Tipo.choices,
        default=InsumoReferencia.Tipo.INSUMO, verbose_name=_("Tipo"),
    )
    custo_unitario = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))], verbose_name=_("Custo unitário"),
    )
    grupo = models.CharField(max_length=150, blank=True, verbose_name=_("Grupo/classe"))
    observacao = models.CharField(max_length=255, blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Item de banco da empresa")
        verbose_name_plural = _("Itens de banco da empresa")
        ordering = ["banco", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["banco", "tipo", "codigo"], name="orcamento_item_banco_codigo_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["banco", "tipo"], name="orcamento_itbanco_tipo_idx"),
            models.Index(fields=["tenant", "codigo"], name="orcamento_itbanco_cod_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.descricao[:60]}"


class ComponenteBancoPreco(TenantScopedModel):
    """Linha analítica de uma composição do banco da empresa."""

    componente_id = models.AutoField(primary_key=True)
    composicao = models.ForeignKey(
        ItemBancoPreco, on_delete=models.CASCADE, related_name="componentes",
        verbose_name=_("Composição"),
    )
    filho = models.ForeignKey(
        ItemBancoPreco, on_delete=models.CASCADE, related_name="usado_em",
        verbose_name=_("Insumo/composição filha"),
    )
    coeficiente = models.DecimalField(
        max_digits=14, decimal_places=5, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))], verbose_name=_("Coeficiente"),
    )

    class Meta:
        verbose_name = _("Componente de composição da empresa")
        verbose_name_plural = _("Componentes de composição da empresa")
        ordering = ["composicao", "componente_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["composicao", "filho"], name="orcamento_comp_banco_unico",
            ),
        ]

    def __str__(self):
        return f"{self.composicao_id} ⊃ {self.filho_id} ×{self.coeficiente}"


# `ImportacaoPreco` e `LinhaImportacao` viviam aqui até o **IE.1**. Foram
# promovidos a `funcoesimpexp.Importacao`/`LinhaImportacao`, onde o que era campo
# de preço (`codigo`, `custo_unitario`, `grupo`) virou um `valores` JSON governado
# pelas colunas que o recurso declara — a mesma máquina servindo qualquer módulo.
# A declaração do Orçamento está em `impexp.py`.


class Reprecificacao(TenantScopedModel):
    """Um **lote** de troca de data-base, com o preço anterior de cada linha.

    Reprecificar não é versionar. Versão, neste módulo, significa aditivo
    contratual — mudou o escopo da obra, e a revisão exige motivo. Atualizar a
    tabela de preço é o mesmo escopo com preço de outro mês; se as duas coisas
    virassem "versão", o histórico passaria a contar duas histórias misturadas.

    Por isso o lote guarda `custo_antes` linha a linha: é o que torna o
    **desfazer** possível sem inventar versão. Em orçamento **aprovado** não há
    lote — a régua está congelada (`planilha.exigir_editavel`) e o caminho é
    revisar, porque medições já feitas contra ela não podem mudar de base em
    silêncio.

    O destino é **qualquer publicação**, para frente ou para trás: em licitação
    a data-base é a do edital, e ela costuma ser passada.
    """

    class Status(models.TextChoices):
        PREVIA = "previa", _("Prévia (não aplicada)")
        APLICADA = "aplicada", _("Aplicada")
        DESFEITA = "desfeita", _("Desfeita")

    reprecificacao_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="reprecificacoes",
        verbose_name=_("Orçamento"),
    )
    base_destino = models.ForeignKey(
        BaseReferencial, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reprecificacoes", verbose_name=_("Publicação de destino"),
    )
    banco_destino = models.ForeignKey(
        BancoPreco, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reprecificacoes", verbose_name=_("Banco de destino"),
    )
    data_base_destino = models.DateField(
        null=True, blank=True, verbose_name=_("Data-base de destino"),
    )
    somente_ate = models.DateField(
        null=True, blank=True, verbose_name=_("Só linhas com preço até"),
        help_text=_("Data de corte: linha com preço mais novo que isto não é tocada."),
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PREVIA, verbose_name=_("Status"),
    )
    total_antes = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Total antes"),
    )
    total_depois = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name=_("Total depois"),
    )
    linhas_afetadas = models.PositiveIntegerField(default=0, verbose_name=_("Linhas afetadas"))
    linhas_descontinuadas = models.PositiveIntegerField(
        default=0, verbose_name=_("Linhas descontinuadas"),
        help_text=_(
            "Linhas cujo código sumiu da publicação de destino. Contadas à parte "
            "porque não são preço trocado — são preço que a fonte deixou de publicar."
        ),
    )
    motivo = models.CharField(max_length=255, blank=True, verbose_name=_("Motivo"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    aplicada_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Aplicada em"))
    desfeita_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Desfeita em"))
    criado_por_nome = models.CharField(max_length=150, blank=True, verbose_name=_("Feita por"))

    class Meta:
        verbose_name = _("Reprecificação")
        verbose_name_plural = _("Reprecificações")
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["orcamento", "status"], name="orcamento_repre_status_idx"),
        ]

    def __str__(self):
        return f"Reprecificação #{self.reprecificacao_id} ({self.get_status_display()})"

    @property
    def delta(self) -> Decimal:
        return (self.total_depois or Decimal("0")) - (self.total_antes or Decimal("0"))


class LinhaReprecificacao(TenantScopedModel):
    """O antes e o depois de uma linha da planilha dentro de um lote.

    Guarda também `fonte_antes`/`codigo_antes`/`data_base_antes` porque desfazer
    tem de restaurar a **procedência**, não só o número: uma linha que voltou ao
    preço velho mas continua dizendo que veio da publicação nova é um rastro
    falso, e é justamente o rastro que a auditoria de licitação confere.
    """

    linha_id = models.AutoField(primary_key=True)
    reprecificacao = models.ForeignKey(
        Reprecificacao, on_delete=models.CASCADE, related_name="linhas",
        verbose_name=_("Lote"),
    )
    item_orcado = models.ForeignKey(
        ItemOrcado, on_delete=models.CASCADE, related_name="reprecificacoes",
        verbose_name=_("Linha orçada"),
    )
    custo_antes = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"), verbose_name=_("Custo antes"),
    )
    custo_depois = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"), verbose_name=_("Custo depois"),
    )
    fonte_antes = models.CharField(max_length=10, blank=True, verbose_name=_("Fonte antes"))
    codigo_antes = models.CharField(max_length=30, blank=True, verbose_name=_("Código antes"))
    data_base_antes = models.DateField(null=True, blank=True, verbose_name=_("Data-base antes"))
    fonte_depois = models.CharField(max_length=10, blank=True, verbose_name=_("Fonte depois"))
    codigo_depois = models.CharField(max_length=30, blank=True, verbose_name=_("Código depois"))
    data_base_depois = models.DateField(null=True, blank=True, verbose_name=_("Data-base depois"))
    selecionada = models.BooleanField(default=True, verbose_name=_("Selecionada"))
    aplicada = models.BooleanField(default=False, verbose_name=_("Aplicada"))
    descontinuado = models.BooleanField(
        default=False, verbose_name=_("Descontinuado na fonte"),
        help_text=_(
            "O código não existe na publicação de destino. A linha entra no lote "
            "para **aparecer**, nunca para ser aplicada: não há preço novo para pôr "
            "nela. Antes disto ela era silenciosamente pulada, e a planilha passava "
            "a se chamar pela data-base nova carregando preço da antiga."
        ),
    )
    motivo = models.CharField(max_length=255, blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Linha de reprecificação")
        verbose_name_plural = _("Linhas de reprecificação")
        ordering = ["reprecificacao", "linha_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["reprecificacao", "item_orcado"], name="orcamento_repre_linha_unica",
            ),
        ]

    def __str__(self):
        return f"{self.item_orcado_id}: {self.custo_antes} → {self.custo_depois}"

    @property
    def delta_unitario(self) -> Decimal:
        return (self.custo_depois or Decimal("0")) - (self.custo_antes or Decimal("0"))


# ---------------------------------------------------------------------------
# ORC.7 — encargos analíticos, memória do quantitativo e reajuste por índice
# ---------------------------------------------------------------------------
#
# As três assimetrias que sobravam depois do ORC.6, e o que cada uma custava:
#
#   1. **Encargos eram um percentual digitado no cabeçalho.** Passava no
#      cálculo e reprovava em análise de edital, que pede o *quadro* — grupos
#      A/B/C/D, horista × mensalista, onerado × desonerado.
#   2. **A quantidade não tinha memória.** O preço tinha (`ItemOrcadoInsumo`
#      abre a composição); a quantidade era um Decimal digitado, e ninguém
#      conferia "por que 19,60 m²?".
#   3. **Reprecificar ≠ reajustar.** Trocar a data-base de uma publicação e
#      reajustar um contrato por fórmula paramétrica são operações diferentes,
#      e só a primeira existia.


class ComposicaoEncargos(TenantScopedModel):
    """O **quadro de encargos sociais** — analítico, como edital exige.

    Substitui, sem apagar, o `encargos_sociais_percentual` do cabeçalho do
    orçamento: aquele campo continua sendo o número que a explosão multiplica,
    mas quando existe um quadro marcado `padrao` é ele quem o alimenta — a mesma
    relação que `ComposicaoBDI` tem com `bdi_percentual`.

    **Por que grupos, e não um percentual.** A metodologia SINAPI (e o TCU, ao
    auditar) separa em quatro:

    - **A** — obrigações sociais sobre a folha (INSS/CPP, SESI, SENAI, INCRA,
      SEBRAE, salário-educação, RAT, FGTS). No regime **desonerado** a CPP de
      20% sai e entra a CPRB sobre a receita, que vive no BDI, não aqui.
    - **B** — encargos que **recebem** as incidências do grupo A (repouso
      semanal, feriados, 13º, férias gozadas, auxílio-enfermidade…).
    - **C** — encargos que **não recebem** as incidências de A, porque são
      indenizatórios (aviso prévio indenizado, férias indenizadas, multa do
      FGTS na rescisão).
    - **D** — as **reincidências**: A sobre B, e FGTS sobre aviso prévio. É o
      grupo que ninguém digita à mão sem errar, e por isso aqui ele é
      **derivado** (ver `RubricaEncargos.base_calculo`).

    **Horista × mensalista não é preferência, é aritmética.** O mensalista já
    recebe repouso semanal e feriados embutidos no salário, então o grupo B dele
    é menor — usar o percentual do horista sobre um encargo mensal paga duas
    vezes o mesmo descanso. Por isso o tipo é chave de unicidade junto com o
    regime: um orçamento carrega os dois quadros e a explosão escolhe pela
    unidade do insumo (`H` → horista, `MES` → mensalista).
    """

    class TipoMaoDeObra(models.TextChoices):
        HORISTA = "horista", _("Horista")
        MENSALISTA = "mensalista", _("Mensalista")

    class Regime(models.TextChoices):
        ONERADO = "onerado", _("Onerado")
        DESONERADO = "desonerado", _("Desonerado")

    encargos_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="composicoes_encargos",
        verbose_name=_("Orçamento"),
    )
    nome = models.CharField(max_length=120, default="Encargos sociais", verbose_name=_("Nome"))
    tipo_mao_de_obra = models.CharField(
        max_length=12, choices=TipoMaoDeObra.choices, default=TipoMaoDeObra.HORISTA,
        verbose_name=_("Tipo de mão de obra"),
    )
    regime = models.CharField(
        max_length=12, choices=Regime.choices, default=Regime.ONERADO, verbose_name=_("Regime"),
    )
    padrao = models.BooleanField(
        default=True, verbose_name=_("Quadro padrão do orçamento"),
        help_text=_(
            "O padrão alimenta o percentual do cabeçalho e vale quando não há "
            "quadro do tipo do insumo."
        ),
    )
    fonte = models.CharField(
        max_length=10, choices=Fonte.choices, blank=True, verbose_name=_("Fonte do quadro"),
        help_text=_("De qual publicação as alíquotas vieram, quando não foram digitadas."),
    )
    data_base = models.DateField(null=True, blank=True, verbose_name=_("Data-base das alíquotas"))
    # --- Derivados (encargos.salvar_encargos) ---
    total_grupo_a = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("Grupo A (%)"),
    )
    total_grupo_b = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("Grupo B (%)"),
    )
    total_grupo_c = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("Grupo C (%)"),
    )
    total_grupo_d = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("Grupo D (%)"),
    )
    percentual_calculado = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"),
        verbose_name=_("Encargos resultantes (%)"),
        help_text=_("A + B + C + D. Derivado, nunca digitado."),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Composição de encargos sociais")
        verbose_name_plural = _("Composições de encargos sociais")
        ordering = ["orcamento", "-padrao", "tipo_mao_de_obra"]
        constraints = [
            models.UniqueConstraint(
                fields=["orcamento", "tipo_mao_de_obra", "regime"],
                name="orcamento_encargos_unico_por_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_mao_de_obra_display()}) — {self.percentual_calculado}%"


class RubricaEncargos(TenantScopedModel):
    """Uma linha do quadro de encargos: código, descrição e alíquota.

    Linha e não coluna porque as publicações **mudam de rubrica**: a SINAPI já
    renomeou itens do grupo B e o SECONCI só existe em alguns estados. Um model
    com quarenta campos fixos exigiria migration a cada publicação; uma tabela
    de rubricas absorve a diferença e ainda deixa a empresa acrescentar a sua.

    `base_calculo` é o que torna o **grupo D** auditável em vez de digitado:

    - `direta` — a alíquota vem do campo `percentual` (grupos A, B e C).
    - `a_sobre_b` — reincidência do grupo A sobre o grupo B: ``A × B / 100``.
    - `fgts_sobre_aviso` — reincidência do FGTS sobre o aviso prévio, o outro
      termo clássico de D: ``FGTS × (rubricas de aviso prévio) / 100``.

    Nas duas derivadas o `percentual` vira **resultado**, não entrada — quem o
    escreve é `encargos.calcular_encargos`, e a tela o mostra bloqueado com a
    conta ao lado. É a diferença entre um quadro que confere e um que só parece
    conferir.
    """

    class Grupo(models.TextChoices):
        A = "A", _("A — Obrigações sociais sobre a folha")
        B = "B", _("B — Encargos que recebem incidência do grupo A")
        C = "C", _("C — Encargos que não recebem incidência do grupo A")
        D = "D", _("D — Reincidências")

    class BaseCalculo(models.TextChoices):
        DIRETA = "direta", _("Alíquota digitada")
        A_SOBRE_B = "a_sobre_b", _("Reincidência de A sobre B")
        FGTS_SOBRE_AVISO = "fgts_sobre_aviso", _("Reincidência do FGTS sobre o aviso prévio")

    rubrica_id = models.AutoField(primary_key=True)
    composicao = models.ForeignKey(
        ComposicaoEncargos, on_delete=models.CASCADE, related_name="rubricas",
        verbose_name=_("Quadro de encargos"),
    )
    grupo = models.CharField(max_length=1, choices=Grupo.choices, verbose_name=_("Grupo"))
    codigo = models.CharField(
        max_length=10, blank=True, verbose_name=_("Código"),
        help_text=_("A1, B3, D2… o código da publicação, quando existe."),
    )
    descricao = models.CharField(max_length=180, verbose_name=_("Descrição"))
    percentual = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name=_("Alíquota (%)"),
    )
    base_calculo = models.CharField(
        max_length=20, choices=BaseCalculo.choices, default=BaseCalculo.DIRETA,
        verbose_name=_("Base de cálculo"),
    )
    e_fgts = models.BooleanField(
        default=False, verbose_name=_("É a rubrica do FGTS"),
        help_text=_("Marca quem entra como multiplicando na reincidência do grupo D."),
    )
    e_aviso_previo = models.BooleanField(
        default=False, verbose_name=_("É aviso prévio"),
        help_text=_("Marca a base da reincidência do FGTS no grupo D."),
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem no grupo"))

    class Meta:
        verbose_name = _("Rubrica de encargos")
        verbose_name_plural = _("Rubricas de encargos")
        ordering = ["composicao", "grupo", "ordem", "rubrica_id"]
        indexes = [
            models.Index(fields=["composicao", "grupo"], name="orcamento_rubrica_grupo_idx"),
        ]

    def __str__(self):
        return f"{self.grupo}{self.codigo} {self.descricao}: {self.percentual}%"


class LinhaMedicao(TenantScopedModel):
    """A **memória de cálculo do quantitativo** — o que faltava do outro lado.

    O preço da linha já era auditável (`ItemOrcadoInsumo` abre a composição); a
    quantidade não era. `ItemOrcado.quantidade` era um Decimal digitado, e
    "19,60 m²" não respondia a "de onde?". Aqui ela vira soma de parciais, no
    formato que o setor usa desde a prancheta e que Arquimedes e ORSE mantêm::

        descrição       n      a       b      c      total
        Parede eixo B   2  ×  3,50 ×  2,80        =  19,60
        (−) Vão porta   1  ×  0,80 ×  2,10        =  −1,68
                                            total    17,92

    **Dimensão ausente não vira zero, vira ausência.** `a`, `b` e `c` são
    anuláveis e a conta só multiplica o que foi informado — senão uma linha de
    contagem pura (`n = 12 unidades`) daria zero, que é o erro silencioso mais
    caro possível numa planilha.

    `formula` é a saída para o que não cabe em três dimensões (uma área de
    seção, um arco). Quando preenchida, manda; a avaliação é por AST restrita em
    `quantitativos.py` — aritmética e parênteses, nada de nome nem chamada.

    A linha-pai passa a ter a quantidade **derivada** quando tem medição: a
    grade mostra o campo bloqueado com o total da soma. Só assim as duas pontas
    não divergem.
    """

    class Sinal(models.IntegerChoices):
        SOMA = 1, _("Soma (+)")
        SUBTRACAO = -1, _("Subtração (−)")

    medicao_id = models.AutoField(primary_key=True)
    item_orcado = models.ForeignKey(
        ItemOrcado, on_delete=models.CASCADE, related_name="linhas_medicao",
        verbose_name=_("Linha orçada"),
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    descricao = models.CharField(
        max_length=180, blank=True, verbose_name=_("Descrição da parcial"),
        help_text=_("Onde é: 'Parede eixo B', 'Pavimento tipo', 'vãos'."),
    )
    sinal = models.SmallIntegerField(
        choices=Sinal.choices, default=Sinal.SOMA, verbose_name=_("Sinal"),
    )
    repeticoes = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("1"), verbose_name=_("Repetições (n)"),
    )
    comprimento = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name=_("Comprimento (a)"),
    )
    largura = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name=_("Largura (b)"),
    )
    altura = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, verbose_name=_("Altura (c)"),
    )
    formula = models.CharField(
        max_length=180, blank=True, verbose_name=_("Fórmula"),
        help_text=_("Aritmética livre. Quando preenchida, substitui n × a × b × c."),
    )
    total = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0"), verbose_name=_("Total da parcial"),
        help_text=_("Derivado. Já com o sinal aplicado."),
    )
    referencia_projeto = models.CharField(
        max_length=120, blank=True, verbose_name=_("Referência de projeto"),
        help_text=_("Prancha, folha ou elemento de onde a medida saiu — o rastro da conferência."),
    )

    class Meta:
        verbose_name = _("Linha de medição")
        verbose_name_plural = _("Linhas de medição")
        ordering = ["item_orcado", "ordem", "medicao_id"]
        indexes = [
            models.Index(fields=["item_orcado"], name="orcamento_medicao_linha_idx"),
        ]

    def __str__(self):
        return f"{self.descricao or 'parcial'} = {self.total}"


class IndiceEconomico(models.Model):
    """Um índice de reajuste — INCC-M, IPCA, IGP-M, CUB.

    **Global, sem tenant**, pela mesma razão da `BaseReferencial` (§11.1): o
    INCC-M de julho/2026 é o mesmo número para todo mundo, é publicado por
    terceiro (FGV, IBGE, Sinduscon) e replicá-lo por empresa seria copiar dado
    público. Escrita por comando/job; a API é read-only e gateada pelo
    entitlement `orcamento`.
    """

    indice_id = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True, verbose_name=_("Código"))
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    fonte = models.CharField(
        max_length=80, blank=True, verbose_name=_("Fonte"),
        help_text=_("FGV, IBGE, Sinduscon/UF — quem publica."),
    )
    uf = models.CharField(
        max_length=2, blank=True, verbose_name=_("UF"),
        help_text=_("Só para índices regionais, como o CUB."),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Índice econômico")
        verbose_name_plural = _("Índices econômicos")
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.nome}"


class ValorIndice(models.Model):
    """O número do índice numa competência.

    Guarda o **número-índice** (a série encadeada), não só a variação: reajuste
    contratual é razão entre dois pontos da série (``I_t / I_0``), e reconstituir
    isso somando variações mês a mês acumula erro de arredondamento que aparece
    como centavo de diferença num contrato de milhões. A variação fica junto
    porque é o que a imprensa publica e o que o usuário confere.
    """

    valor_id = models.AutoField(primary_key=True)
    indice = models.ForeignKey(
        IndiceEconomico, on_delete=models.CASCADE, related_name="valores", verbose_name=_("Índice"),
    )
    competencia = models.DateField(
        verbose_name=_("Competência"), help_text=_("Sempre o dia 1º do mês de referência."),
    )
    numero_indice = models.DecimalField(
        max_digits=16, decimal_places=6, verbose_name=_("Número-índice"),
    )
    variacao_percentual = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True, verbose_name=_("Variação no mês (%)"),
    )

    class Meta:
        verbose_name = _("Valor de índice")
        verbose_name_plural = _("Valores de índice")
        ordering = ["indice", "-competencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["indice", "competencia"], name="orcamento_indice_competencia_unica",
            ),
        ]

    def __str__(self):
        return f"{self.indice.codigo} {self.competencia:%m/%Y} = {self.numero_indice}"


class FormulaReajuste(TenantScopedModel):
    """A **fórmula paramétrica de reajuste** do contrato, como o edital a define::

        R = V × [ a + Σ pᵢ × (Iᵢ,t / Iᵢ,0) ]

    onde `a` é a parcela **não reajustável** e cada `pᵢ` é o peso de um índice
    setorial. Contratos de obra pública quase sempre usam uma cesta (mão de
    obra, materiais, equipamentos) em vez de um índice único, e é por isso que a
    fórmula é uma tabela de parcelas e não um campo.

    **Reajustar não é reprecificar.** A reprecificação (`Reprecificacao`) troca o
    preço unitário pela cotação de outra publicação, item a item — muda a
    *composição* do custo. O reajuste multiplica tudo por um fator contratual,
    sem tocar em composição, e é ato de contrato: em orçamento aprovado ele
    exige revisão, que é onde o histórico mora.
    """

    formula_id = models.AutoField(primary_key=True)
    orcamento = models.ForeignKey(
        Orcamento, on_delete=models.CASCADE, related_name="formulas_reajuste",
        verbose_name=_("Orçamento"),
    )
    nome = models.CharField(max_length=120, default="Reajuste contratual", verbose_name=_("Nome"))
    data_base = models.DateField(
        verbose_name=_("Data-base (I₀)"),
        help_text=_("A competência do denominador — normalmente a data-base do orçamento."),
    )
    parcela_fixa = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0"),
        verbose_name=_("Parcela não reajustável (a)"),
        help_text=_("Fração de 0 a 1. A soma de 'a' com os pesos precisa fechar em 1."),
        validators=[MinValueValidator(Decimal("0"))],
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Fórmula de reajuste")
        verbose_name_plural = _("Fórmulas de reajuste")
        ordering = ["orcamento", "nome"]

    def __str__(self):
        return f"{self.nome} (base {self.data_base:%m/%Y})"


class ParcelaFormulaReajuste(TenantScopedModel):
    """Uma parcela da cesta: índice × peso."""

    parcela_id = models.AutoField(primary_key=True)
    formula = models.ForeignKey(
        FormulaReajuste, on_delete=models.CASCADE, related_name="parcelas", verbose_name=_("Fórmula"),
    )
    indice = models.ForeignKey(
        IndiceEconomico, on_delete=models.PROTECT, related_name="+", verbose_name=_("Índice"),
    )
    peso = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0"), verbose_name=_("Peso (p)"),
        help_text=_("Fração de 0 a 1."),
        validators=[MinValueValidator(Decimal("0"))],
    )
    rotulo = models.CharField(
        max_length=80, blank=True, verbose_name=_("Rótulo"),
        help_text=_("'Mão de obra', 'Materiais' — como o edital nomeia a parcela."),
    )

    class Meta:
        verbose_name = _("Parcela da fórmula de reajuste")
        verbose_name_plural = _("Parcelas da fórmula de reajuste")
        ordering = ["formula", "parcela_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["formula", "indice"], name="orcamento_formula_indice_unico",
            ),
        ]

    def __str__(self):
        return f"{self.rotulo or self.indice.codigo}: {self.peso}"
