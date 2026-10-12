# backend/moduloorcamento/services.py
"""Adoção: a base referencial **pública** vira item do catálogo **da empresa**.

Este é o ponto de costura do módulo com a fundação. A base (SINAPI/ORSE) é
global e read-only; o `catalogo.Item` é do tenant. Adotar significa: "esta
empresa passa a ter no catálogo dela este insumo/serviço da base, com o código
da fonte registrado". Consequência de desenho — o item adotado é **o mesmo**
que o SCM compra e o SIL estoca, então o orçado casa com o comprado e o
aplicado sem tradução (docs/modulos/moduloorcamento.md §11.1).

Três propriedades que o chamador pode assumir:

- **Idempotente.** Adotar duas vezes não duplica: a chave de reconhecimento é
  (tenant, fonte_referencia, codigo_referencia) e, na falta dela, o
  `codigo_interno` derivado. Re-adotar atualiza preço/descrição da publicação
  mais nova sem quebrar as FKs de quem já usa o item.
- **Recursiva por padrão.** Composição adotada traz os componentes (e os
  componentes dos componentes), porque composição sem insumo não tem memória de
  cálculo — é só um preço solto.
- **Sob RLS.** Escreve `catalogo.Item`, que é tenant-scoped e fail-closed; roda
  no contexto já armado pela autenticação (ou sob `tenant_context` em job).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from catalogo.models import ComponenteComposicao, Item, TipoItemProprio
from funcoesimpexp.formatos.leitura import normalizar

from . import identidade
from .models import ComposicaoReferenciaItem, InsumoReferencia

# Unidades de mão de obra na SINAPI/ORSE (hora e mês de profissional). Item com
# esta unidade não é material: não se estoca nem se compra em pedido de material,
# então nasce no catálogo como serviço.
UNIDADES_MAO_DE_OBRA = {"H", "HORA", "MES", "MÊS", "H/M", "MÊS/H"}

# Prefixo do código interno gerado na adoção. Mantém o item da base distinguível
# do cadastro próprio da empresa na lista do catálogo, e evita colisão com SKU
# interno (que raramente começa por "SINAPI-").
#
# **Largura, e não teto** — a distinção importa desde que todo limite passou a
# morar em `payment/planos.py` (08/08/2026). Este 40 é o `max_length` da coluna
# `catalogo.Item.codigo_interno`, e existe para o código gerado **caber**; não diz
# nada sobre até onde o cliente vai, e mudá-lo sozinho só produz um valor que o
# banco recusa. Chamava-se `LARGURA_CODIGO_INTERNO` e por isso aparecia em toda
# varredura de teto como falso positivo — o nome é que estava errado.
LARGURA_CODIGO_INTERNO = 40


class AdocaoInvalida(Exception):
    """Referência inconsistente para adoção (sem código, sem unidade)."""


class IdentidadeDivergente(Exception):
    """D110 — o item achado pelo código **não é** o item que a publicação descreve.

    Não é dado inválido: os dois lados estão bem formados, e é justamente por
    isso que o caso passava batido. A adoção para aqui em vez de sobrescrever,
    porque reescrever descrição e unidade de um item que já é componente de
    composição e já está em linha orçada troca o insumo **por baixo** de quem o
    referencia — sem erro na tela, e visível só num total que não fecha.

    Carrega o item e a divergência para quem chama poder mostrar os dois lados e
    oferecer a decisão (`forcar=True` é a resposta humana "sim, é o mesmo item").
    """

    def __init__(self, item: Item, divergencia: identidade.Divergencia, codigo: str = ""):
        self.item = item
        self.divergencia = divergencia
        self.codigo = codigo
        super().__init__(f"{codigo or item.codigo_referencia}: {divergencia}")

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo or self.item.codigo_referencia,
            "item_id": self.item.pk,
            "codigo_interno": self.item.codigo_interno,
            **self.divergencia.como_dict(),
        }


@dataclass
class ResultadoAdocao:
    """O que uma adoção em lote produziu — o que entrou **e o que ficou de fora**.

    Duas listas em vez de só a dos adotados porque o que ficou de fora é a
    informação nova: silenciar a divergência devolveria exatamente o
    comportamento que o D110 fechou.
    """

    adotados: list = field(default_factory=list)
    divergentes: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.adotados)

    def __iter__(self):
        return iter(self.adotados)


def codigo_interno_para(referencia: InsumoReferencia) -> str:
    """`SINAPI-88489`. Truncado ao limite do campo do catálogo."""
    fonte = referencia.base.fonte.upper()
    return f"{fonte}-{referencia.codigo}"[:LARGURA_CODIGO_INTERNO]


# Prefixos de classe → natureza. É um de-para **escrito por gente**, não uma
# inferência: cada linha existe porque a grafia apareceu numa publicação real.
# A ordem importa — o primeiro prefixo que casar vence, então "mao de obra" vem
# antes de qualquer coisa que comece por "ma".
PREFIXOS_DE_CLASSE: tuple[tuple[str, str], ...] = (
    ("mao de obra", Item.Tipo.MAO_DE_OBRA),
    ("mao-de-obra", Item.Tipo.MAO_DE_OBRA),
    ("maos de obra", Item.Tipo.MAO_DE_OBRA),
    ("encargo", Item.Tipo.ENCARGOS_COMPLEMENTARES),
    ("equipamento", Item.Tipo.EQUIPAMENTO),
    # A prefeitura escreve a locação do avesso ("LOCAÇÃO DE EQUIPAMENTO"); a
    # SINAPI escreve "EQUIPAMENTO (LOCAÇÃO)". É o mesmo insumo, e sem esta linha
    # a de prefeitura caía no plano B — em `H`, virando mão de obra e levando
    # encargo social, que é o defeito do D109 renascido em outra fonte.
    ("locacao de equipamento", Item.Tipo.EQUIPAMENTO),
    ("material", Item.Tipo.MATERIAL),
    # Plural que ORSE e SICRO usam. "materiais" NÃO começa por "material" (troca
    # o `l` pelo `i`), então precisa de linha própria — foi assim que a classe
    # mais comum de duas bases inteiras passava por não classificada.
    ("materiais", Item.Tipo.MATERIAL),
    ("servico", Item.Tipo.SERVICO),
)

# Classes que a fonte publica e que **por desenho** não dizem natureza. Estão
# aqui para não entrarem no relatório de "classe não reconhecida": elas foram
# reconhecidas — a resposta delas é "não classifico".
CLASSES_SEM_NATUREZA = frozenset({"especiais", "especial", "taxas", "taxa"})

# Onde moram os dicionários de classe que o **superuser** declara por fonte.
# Arquivo em vez de tabela porque quem decide isto é a mesma pessoa que importa
# a base-mãe, uma vez por fonte e não por tenant: a base é global e read-only, e
# a decisão dela também é. Em arquivo ela entra no diff, é revisável e viaja com
# a imagem — em tabela, ninguém veria quem mudou a natureza de uma classe
# inteira, que é uma alavanca de preço para **todos** os tenants de uma vez.
PASTA_DE_CLASSES = Path(__file__).resolve().parent / "dados" / "classes"

_cache_de_classes: dict[str, dict[str, str]] = {}


def classes_declaradas(fonte: str | None) -> dict[str, str]:
    """`{classe normalizada: natureza}` que o superuser declarou para a fonte.

    Lê `dados/classes/<fonte>.csv` (`classe;natureza`, `#` comenta). É o que faz
    a importação parar de perguntar a mesma coisa todo mês: a resposta dada uma
    vez vale para as publicações seguintes daquela fonte.

    Casamento **exato** sobre a forma normalizada, e não por prefixo como o
    `PREFIXOS_DE_CLASSE`: aqui alguém digitou a classe olhando para a
    publicação, então não há por que abrir a mão em cima disso — prefixo faria
    "MATERIAL DE CONSUMO" casar com uma linha escrita para "MATERIAL".

    Linha que não aponta para uma natureza do catálogo é **ignorada** e não
    derruba a leitura: este arquivo é lido dentro de `bases-resumo/`, que é
    tela, e uma vírgula errada aqui não pode derrubar a listagem de publicações.
    Quem cobra o arquivo com rigor é o comando de importação, que o valida antes
    de gravar qualquer coisa.
    """
    chave = (fonte or "").strip().lower()
    if chave in _cache_de_classes:
        return _cache_de_classes[chave]

    declarado: dict[str, str] = {}
    arquivo = PASTA_DE_CLASSES / f"{chave}.csv"
    if chave and arquivo.is_file():
        naturezas = {t for t, _ in Item.Tipo.choices}
        for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or ";" not in linha:
                continue
            classe, _, natureza = linha.partition(";")
            natureza = natureza.split(";")[0].strip().lower().replace(" ", "_").replace("-", "_")
            if normalizar(classe) and natureza in naturezas:
                declarado[normalizar(classe)] = natureza
    _cache_de_classes[chave] = declarado
    return declarado


def esquecer_classes_declaradas() -> None:
    """Zera o cache — para o teste que escreve o arquivo e relê."""
    _cache_de_classes.clear()


def natureza_da_classificacao(texto: str | None, fonte: str | None = None) -> str | None:
    """A **classificação publicada pela fonte** → natureza do catálogo.

    A SINAPI publica, desde 01/2025, a coluna `Classificação` com MATERIAL ·
    MÃO DE OBRA · EQUIPAMENTO (AQUISIÇÃO/LOCAÇÃO) · ENCARGOS COMPLEMENTARES ·
    SERVIÇOS · ESPECIAIS. Ela é a resposta da própria fonte à pergunta que a
    adoção fazia por adivinhação — e é gravada em `InsumoReferencia.grupo`.

    Com `fonte`, o dicionário que o superuser declarou para ela vem **antes** do
    de-para embutido: quem importou a base olhou a publicação, e o embutido foi
    escrito para o vocabulário da SINAPI.

    Devolve `None` em três situações que são diferentes entre si, e é
    `classificacao_desconhecida` quem as separa: campo vazio (a fonte não
    classifica — D111), classe que declara não ser natureza ("ESPECIAIS",
    "TAXAS"), e **vocabulário que ninguém declarou** — que é o caso a reportar,
    porque nele a fonte respondeu e nós é que não entendemos.
    """
    if not texto:
        return None
    chave = normalizar(texto)
    declarado = classes_declaradas(fonte).get(chave) if fonte else None
    if declarado is not None:
        return declarado
    for prefixo, natureza in PREFIXOS_DE_CLASSE:
        if chave.startswith(prefixo):
            return natureza
    return None


def classificacao_desconhecida(texto: str | None, fonte: str | None = None) -> bool:
    """A fonte disse alguma coisa e o sistema não soube ler.

    Existe porque as três causas de `natureza_da_classificacao` devolver `None`
    pedem respostas diferentes, e tratá-las como uma só é o que fazia toda base
    de vocabulário próprio (ORSE, SICRO, tabela de prefeitura) cair no plano B
    da unidade **em silêncio** — com o indicador de "publicação classifica
    insumo" aceso, porque a coluna estava preenchida.

    Vazio devolve `False`: a fonte não respondeu, e isso já é contado à parte.
    Célula com só espaço é vazia — o `normalizar` é quem decide isso, e não um
    `if not texto`, que deixaria `"   "` passar por resposta.
    """
    if natureza_da_classificacao(texto, fonte) is not None:
        return False
    chave = normalizar(texto)
    return bool(chave) and chave not in CLASSES_SEM_NATUREZA


def flags_da_natureza(natureza: str) -> dict:
    """As flags de domínio que a natureza implica, no vocabulário do `Item`.

    Vem de `TipoItemProprio.padroes_da_natureza` de propósito: é o **mesmo**
    de-para que o formulário de tipo próprio oferece ao usuário. Duas tabelas
    diriam coisas diferentes sobre o mesmo insumo — uma na adoção automática,
    outra no cadastro à mão.
    """
    padroes = dict(TipoItemProprio.padroes_da_natureza(natureza))
    padroes.pop("leva_encargo_social", None)  # é do orçamento, não do item
    return padroes


def _tipo_e_flags(referencia: InsumoReferencia) -> tuple[str, dict]:
    """Traduz o item da base para o vocabulário do catálogo-mestre.

    Ordem de decisão, da mais confiável para a menos:

    1. **composição** → `Tipo.COMPOSICAO`: quem se compra e se estoca são os
       insumos dela; a composição é construto de orçamento.
    2. **classificação da fonte** (`grupo`) → a natureza que a própria SINAPI
       declarou.
    3. **unidade de hora/mês** → `Tipo.MAO_DE_OBRA`. Até 20/08/2026 este degrau
       devolvia `Tipo.SERVICO`, e como a precificação lia todo serviço como mão
       de obra, serviço de terceiro levava encargo social em cima de preço que
       já vinha com encargo dentro.
    4. **demais** → `Tipo.MATERIAL`.

    O usuário pode corrigir o item depois no catálogo — os degraus 3 e 4 são o
    default menos arriscado, não a verdade final.
    """
    if referencia.tipo == InsumoReferencia.Tipo.COMPOSICAO:
        return Item.Tipo.COMPOSICAO, flags_da_natureza(Item.Tipo.COMPOSICAO)
    natureza = natureza_da_classificacao(referencia.grupo, referencia.base.fonte)
    if natureza is None:
        natureza = (
            Item.Tipo.MAO_DE_OBRA
            if referencia.unidade.strip().upper() in UNIDADES_MAO_DE_OBRA
            else Item.Tipo.MATERIAL
        )
    return natureza, flags_da_natureza(natureza)


def _localizar_item(tenant_id, referencia: InsumoReferencia) -> Item | None:
    """Item já adotado, pelo par (fonte, código da fonte) ou pelo código interno."""
    por_referencia = Item.objects.filter(
        tenant_id=tenant_id,
        fonte_referencia=referencia.base.fonte,
        codigo_referencia=referencia.codigo,
    ).first()
    if por_referencia is not None:
        return por_referencia
    return Item.objects.filter(
        tenant_id=tenant_id, codigo_interno=codigo_interno_para(referencia)
    ).first()


@transaction.atomic
def adotar_no_catalogo(
    referencia: InsumoReferencia, tenant_id, *, recursivo: bool = True, forcar: bool = False,
) -> Item:
    """Cria (ou atualiza) o `catalogo.Item` do tenant a partir da referência.

    Devolve o item adotado. Com `recursivo`, adota também os componentes da
    composição e grava os `ComponenteComposicao` correspondentes.

    **A re-adoção confere a identidade antes de sobrescrever** (D110). Achar o
    item pelo par `(fonte, código)` diz onde escrever, não *o quê*: quando a
    descrição e a unidade do catálogo não batem com as da publicação, o par
    aponta para outro insumo — a fonte reaproveitou o número — e sobrescrever
    trocaria o item por baixo das composições e das linhas orçadas que já o
    referenciam. Nesse caso levanta `IdentidadeDivergente` e **não grava nada**.
    `forcar=True` é a decisão de quem olhou os dois lados e disse que é o mesmo.
    """
    if not referencia.codigo or not referencia.unidade:
        raise AdocaoInvalida(
            f"Referência {referencia.pk} sem código ou unidade — base importada incompleta."
        )

    tipo, flags = _tipo_e_flags(referencia)
    item = _localizar_item(tenant_id, referencia)
    if item is None:
        item = Item(
            tenant_id=tenant_id, codigo_interno=codigo_interno_para(referencia),
            origem=Item.Origem.BASE, origem_detalhe=str(referencia.base)[:120],
        )
        # Flags só são definidas na CRIAÇÃO: se a empresa marcou o item como não
        # estocável, uma re-adoção não pode desfazer essa decisão dela.
        for campo, valor in flags.items():
            setattr(item, campo, valor)
        item.tipo = tipo
    elif not forcar:
        divergencia = identidade.conferir(
            descricao_catalogo=item.descricao,
            unidade_catalogo=item.unidade,
            descricao_publicacao=referencia.descricao,
            unidade_publicacao=referencia.unidade,
        )
        if divergencia is not None:
            raise IdentidadeDivergente(item, divergencia, codigo=referencia.codigo)
    item.descricao = referencia.descricao[:255]
    item.unidade = referencia.unidade[:20]
    item.codigo_referencia = referencia.codigo[:30]
    item.fonte_referencia = referencia.base.fonte
    # De qual **edição** veio o que está no catálogo. Sem isto, o par
    # (fonte, código) é toda a procedência que o item guarda, e ele não responde
    # "de onde saiu esta descrição" — pergunta que a conferência de identidade
    # faz o tempo todo e que o D110 registrou como lacuna.
    item.publicacao_referencia = str(referencia.base)[:120]
    if referencia.grupo and not item.categoria:
        item.categoria = referencia.grupo[:80]
    item.save()

    if recursivo and referencia.tipo == InsumoReferencia.Tipo.COMPOSICAO:
        _adotar_componentes(referencia, item, tenant_id, forcar=forcar)
    return item


def componentes_da_composicao(referencia: InsumoReferencia) -> list:
    """A analítica de uma composição — **a única função que sabe onde ela mora**.

    Desde a ORC.8 há dois armazenamentos, e é deliberado (a conta está no
    docstring de `AnaliticaNacional`): a analítica da publicação, quando existe,
    e a nacional guardada uma vez por fonte + mês. Ter dois *lugares* é o preço
    de não replicar 3,6 milhões de linhas por mês; ter duas *leituras* seria o
    bug — por isso todo consumidor (adoção, cópia para banco de preço, endpoint
    de composição) passa por aqui.

    **A própria publicação vence.** Ela é mais específica: quem importou aquele
    arquivo pelo comando declarou aquela analítica para aquela base, e uma
    republicação nacional não deve mudar o que já foi conferido linha a linha.

    O que volta são `ComposicaoReferenciaItem` — os do banco quando existem,
    instâncias **não salvas** quando vêm da nacional. O `componente_id` negativo
    delas não é um id: é o que impede a lista de sair com chaves repetidas na
    tela, e diz de qual linha nacional cada componente veio.

    Componente cujo filho não tem preço naquela UF fica de fora, e isso é a
    regra 1 do §4.1 valendo até o fim: sem pesquisa não é zero, e uma composição
    exibida com um insumo a R$ 0,00 mentiria sobre o custo dela.
    """
    proprios = list(
        ComposicaoReferenciaItem.objects.filter(composicao=referencia)
        .select_related("filho", "filho__base")
        .order_by("componente_id")
    )
    if proprios or referencia.tipo != InsumoReferencia.Tipo.COMPOSICAO:
        return proprios

    from .models import AnaliticaNacional

    base = referencia.base
    linhas = list(
        AnaliticaNacional.objects.filter(
            fonte=base.fonte,
            competencia=base.mes_referencia,
            codigo_composicao=referencia.codigo,
        ).order_by("linha_id")
    )
    if not linhas:
        return []
    filhos = {
        item.codigo: item
        for item in InsumoReferencia.objects.filter(
            base=base, codigo__in=[linha.codigo_item for linha in linhas]
        ).select_related("base")
    }
    virtuais = []
    for linha in linhas:
        filho = filhos.get(linha.codigo_item)
        if filho is None:
            continue
        virtuais.append(ComposicaoReferenciaItem(
            componente_id=-linha.linha_id,
            composicao=referencia, filho=filho, coeficiente=linha.coeficiente,
        ))
    return virtuais


def _adotar_componentes(
    referencia: InsumoReferencia, item_pai: Item, tenant_id, *, forcar: bool = False,
) -> None:
    """Explode a composição no catálogo do tenant, um nível por chamada recursiva.

    Divergência num componente **derruba a composição inteira** — a exceção sobe
    e o `atomic` desfaz tudo. É o desfecho certo: composição cujo insumo não é o
    que ela pensa que é não tem memória de cálculo válida, e adotá-la pela
    metade deixaria um pai apontando para filho errado, que é o dano do D110 com
    outro nome.
    """
    for componente in componentes_da_composicao(referencia):
        item_filho = adotar_no_catalogo(
            componente.filho, tenant_id, recursivo=True, forcar=forcar
        )
        if item_filho.pk == item_pai.pk:
            # Autorreferência na base (dado sujo) — ignorada: um item composto de
            # si mesmo explodiria em laço na precificação.
            continue
        ComponenteComposicao.objects.update_or_create(
            tenant_id=tenant_id, item_pai=item_pai, item_filho=item_filho,
            defaults={"coeficiente": componente.coeficiente},
        )


def adotar_muitos(
    referencias, tenant_id, *, recursivo: bool = True, forcar: bool = False,
) -> ResultadoAdocao:
    """Adoção em lote (a tela adota a seleção da busca de uma vez).

    Uma divergência de identidade **não derruba o lote**: o item divergente fica
    de fora e vai para `divergentes`, os outros entram. Cada `adotar_no_catalogo`
    é um `atomic` aninhado (savepoint), então o que foi recusado não deixa
    escrita pela metade.
    """
    resultado = ResultadoAdocao()
    for referencia in referencias:
        try:
            resultado.adotados.append(
                adotar_no_catalogo(referencia, tenant_id, recursivo=recursivo, forcar=forcar)
            )
        except IdentidadeDivergente as exc:
            resultado.divergentes.append(exc.como_dict())
    return resultado


# ---------------------------------------------------------------------------
# ORC.1 — a outra travessia: catálogo do tenant → linha da planilha
# ---------------------------------------------------------------------------


def custo_de_referencia(item: Item, base) -> Decimal | None:
    """Preço do item na publicação escolhida pelo orçamento, se houver.

    Só encontra quando o item **veio** daquela fonte (foi adotado dela): a
    chave é o par (fonte, código na fonte) que a adoção gravou. Item próprio da
    empresa não tem preço na SINAPI, e devolver `None` aqui é o comportamento
    certo — quem informa o preço é o orçamentista.
    """
    if base is None or not item.codigo_referencia or item.fonte_referencia != base.fonte:
        return None
    referencia = InsumoReferencia.objects.filter(
        base=base, codigo=item.codigo_referencia
    ).only("custo_unitario").first()
    return referencia.custo_unitario if referencia else None


def linha_a_partir_do_item(
    *, orcamento, item: Item, quantidade, custo_unitario=None,
    pai_id=None, etapa_id=None, ordem=0, base=None,
):
    """Cria o `ItemOrcado` **tirando o snapshot** do item do catálogo.

    O que é copiado (descrição, unidade, fonte, código) para de acompanhar o
    catálogo a partir daqui — ver `models.ItemOrcado`. A FK `item` fica, e é ela
    que depois deixa o SCM/SIL casarem comprado e aplicado com o orçado.

    **O preço viaja com a linha (ORC.10a).** `base` é a publicação de onde o
    item foi efetivamente pescado — a que estava aberta no seletor na hora de
    inserir. Antes o preço saía sempre da publicação do *cabeçalho*, e isso
    produzia dois zeros silenciosos: o orçamento sem base vinculada inseria tudo
    a custo zero, e o item de outra fonte (um ORSE numa planilha SINAPI) também,
    porque `custo_de_referencia` exige que a fonte do item e a da publicação
    batam. É o modelo do Arquimedes: a partida arrastada traz o preço do banco
    de onde veio, e a data-base do cabeçalho é o **rótulo do documento**, não um
    filtro sobre o preço.

    Sem `base` vale a regra antiga — a publicação do cabeçalho —, que é o que
    mantém o seed, a precificação e os demais chamadores internos funcionando
    sem saber de nada disto.

    Precedência do preço: o informado pelo cliente ganha do de referência. Quem
    está montando a planilha pode ter cotação melhor que a SINAPI, e o sistema
    não tem por que discordar — mas registra de onde veio o número.
    """
    from .models import ItemOrcado  # import tardio: evita ciclo com models

    publicacao = base if base is not None else orcamento.base_referencial
    preco = custo_unitario
    if preco in (None, ""):
        preco = custo_de_referencia(item, publicacao)
    veio_da_base = custo_unitario in (None, "") and preco is not None

    return ItemOrcado.objects.create(
        tenant_id=orcamento.tenant_id,
        orcamento=orcamento,
        pai_id=pai_id or None,
        etapa_id=etapa_id or None,
        item=item,
        tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
        ordem=ordem or 0,
        descricao=item.descricao,
        unidade=item.unidade,
        quantidade=Decimal(str(quantidade or 0)),
        custo_unitario=Decimal(str(preco or 0)),
        fonte_referencia=item.fonte_referencia or "",
        codigo_referencia=item.codigo_referencia or "",
        # A data-base é a **da publicação que deu o preço**, não a do
        # cabeçalho: com linhas de fontes diferentes na mesma planilha, é ela
        # que faz a coluna Data-base da grade dizer a verdade (e a marca
        # vermelha da ORC.7b aparecer onde deve). Quando a base é a do próprio
        # orçamento dá no mesmo: `data_base` já é copiada dela.
        data_base_preco=publicacao.mes_referencia if veio_da_base else None,
    )
