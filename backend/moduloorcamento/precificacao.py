# backend/moduloorcamento/precificacao.py
"""ORC.2 — o que transforma quantidade em custo, e custo em preço.

Três mecanismos, na ordem em que atuam sobre uma linha da planilha:

1. **Explosão da composição** (`explodir_item`) — o serviço se abre nos insumos
   que o compõem, com coeficiente de produtividade. É o que dá memória de
   cálculo: "este m³ custa R$ 412,80 porque leva 350 kg de cimento a R$ 0,58,
   2,5 h de servente a R$ 19,42…".
2. **Encargos sociais** — incidem **só sobre mão de obra**, no regime escolhido
   (onerado × desonerado). Aplicá-los sobre material infla o orçamento; não
   aplicá-los sobre o pedreiro o torna irreal.
3. **BDI** (`calcular_bdi`) — a fórmula do Acórdão 2622/2013-TCU converte custo
   em preço de venda.

E uma quarta coisa que só um sistema integrado consegue fazer: **precificar
pelo histórico real** (`preco_real_do_item`) — o que a empresa efetivamente
pagou no SCM e o custo médio que o SIL carrega, ao lado do preço de referência.
Orçar com o próprio histórico é mais preciso que orçar pela SINAPI, e o dado já
está no sistema.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, DecimalField, F, Max, Sum
from django.db.models.functions import Coalesce

from catalogo.models import ComponenteComposicao, Item

from .models import ComposicaoBDI, ItemOrcado, ItemOrcadoInsumo, Orcamento
from .planilha import dinheiro
from .services import custo_de_referencia

CEM = Decimal("100")
UM = Decimal("1")
# Profundidade máxima da explosão. SINAPI aninha composições auxiliares em 2–3
# níveis; 12 é folga larga e ao mesmo tempo um freio para dado circular que
# escape da checagem de visitados.
PROFUNDIDADE_MAXIMA = 12


class ComposicaoInvalida(Exception):
    """Item que não é composição, ou composição sem componentes."""


# ---------------------------------------------------------------------------
# BDI — Acórdão 2622/2013-TCU
# ---------------------------------------------------------------------------


def calcular_bdi(composicao: ComposicaoBDI) -> Decimal:
    """Percentual de BDI pela fórmula do acórdão.

        BDI = [ (1+AC+S+R+G) × (1+DF) × (1+L) / (1−I) ] − 1

    Os tributos entram **dividindo**, não somando: a alíquota incide sobre o
    preço final (faturamento), não sobre o custo. Somar `I` — erro comum em
    planilha de Excel — subestima o BDI, e a diferença aparece como prejuízo só
    na hora de faturar.

    Devolve percentual com 4 casas (a precisão que editais pedem no
    detalhamento), levantando erro se os tributos chegarem a 100% — aí a
    fórmula dividiria por zero e o preço seria infinito.
    """
    tributos = composicao.tributos / CEM
    if tributos >= UM:
        raise ComposicaoInvalida(
            "A soma dos tributos precisa ser menor que 100% — a fórmula do BDI "
            "divide por (1 − I)."
        )
    parcelas = (
        composicao.administracao_central + composicao.seguro
        + composicao.risco + composicao.garantia
    ) / CEM
    despesas = composicao.despesas_financeiras / CEM
    lucro = composicao.lucro / CEM

    bruto = ((UM + parcelas) * (UM + despesas) * (UM + lucro)) / (UM - tributos) - UM
    return (bruto * CEM).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@transaction.atomic
def salvar_bdi(composicao: ComposicaoBDI) -> ComposicaoBDI:
    """Calcula, grava e — se for o padrão — propaga para o orçamento.

    O `bdi_percentual` do orçamento continua sendo o número que multiplica no
    recálculo (ORC.1); esta função é quem passa a alimentá-lo. Digitar o
    percentual direto continua possível para quem não quer detalhar, mas quando
    há composição analítica é ela que manda.
    """
    composicao.percentual_calculado = calcular_bdi(composicao)
    composicao.save()

    if composicao.padrao:
        ComposicaoBDI.objects.filter(orcamento=composicao.orcamento).exclude(
            pk=composicao.pk
        ).update(padrao=False)
        orcamento = composicao.orcamento
        orcamento.bdi_percentual = composicao.percentual_calculado.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        orcamento.save(update_fields=["bdi_percentual", "atualizado_em"])
    return composicao


# ---------------------------------------------------------------------------
# Explosão da composição + encargos
# ---------------------------------------------------------------------------


def categoria_do_item(item: Item) -> str:
    """Natureza do insumo — o que decide se leva encargo social.

    Deriva do `tipo` do catálogo, que a adoção já preencheu com a heurística de
    unidade (hora/mês → serviço = mão de obra). Não é infalível, e por isso a
    linha explodida guarda a categoria como campo editável: o orçamentista
    corrige o caso raro sem que o sistema perca a regra geral.
    """
    if item.tipo == Item.Tipo.SERVICO:
        return ItemOrcadoInsumo.Categoria.MAO_DE_OBRA
    if item.tipo in (Item.Tipo.EQUIPAMENTO, Item.Tipo.ATIVO):
        return ItemOrcadoInsumo.Categoria.EQUIPAMENTO
    if item.tipo in (Item.Tipo.MATERIAL, Item.Tipo.EPI):
        return ItemOrcadoInsumo.Categoria.MATERIAL
    return ItemOrcadoInsumo.Categoria.OUTRO


def _folhas_da_composicao(item: Item, tenant_id, *, coeficiente=UM, profundidade=0, vistos=None):
    """Achata a árvore de composição em folhas, acumulando coeficientes.

    Composição de composição é normal na SINAPI (as "composições auxiliares"),
    e o coeficiente de uma folha dentro de uma auxiliar é o **produto** dos
    coeficientes no caminho: 1 m³ de concretagem leva 1,05 m³ de concreto
    auxiliar, que leva 350 kg de cimento → 367,5 kg de cimento por m³.

    `vistos` corta ciclo (A ⊃ B ⊃ A), que na base pública acontece por dado
    sujo e aqui viraria recursão infinita.
    """
    vistos = vistos if vistos is not None else set()
    if profundidade >= PROFUNDIDADE_MAXIMA or item.item_id in vistos:
        return []
    vistos = vistos | {item.item_id}

    componentes = list(
        ComponenteComposicao.objects.filter(tenant_id=tenant_id, item_pai=item)
        .select_related("item_filho")
    )
    if not componentes:
        return [(item, coeficiente)]

    folhas = []
    for componente in componentes:
        folhas.extend(
            _folhas_da_composicao(
                componente.item_filho, tenant_id,
                coeficiente=coeficiente * componente.coeficiente,
                profundidade=profundidade + 1, vistos=vistos,
            )
        )
    return folhas


@transaction.atomic
def explodir_item(item_orcado: ItemOrcado, *, atualizar_custo: bool = True) -> list[ItemOrcadoInsumo]:
    """Gera a memória de cálculo da linha e, por padrão, refaz seu custo unitário.

    O custo unitário deixa de ser um número digitado e passa a ser a **soma dos
    insumos** — que é o que torna o orçamento auditável. Com `atualizar_custo=False`
    a memória é gerada só para consulta, sem mexer no preço (útil quando o
    orçamentista quer ver a composição mas manter uma cotação própria).

    Insumo sem preço conhecido entra com custo zero e fica **visível na memória**
    como linha zerada — em vez de sumir. Um orçamento com furo precisa mostrar
    onde é o furo.
    """
    if item_orcado.item is None:
        raise ComposicaoInvalida("A linha não aponta item do catálogo — nada a explodir.")

    orcamento = item_orcado.orcamento
    tenant_id = item_orcado.tenant_id
    folhas = _folhas_da_composicao(item_orcado.item, tenant_id)
    if not folhas or (len(folhas) == 1 and folhas[0][0].pk == item_orcado.item_id):
        raise ComposicaoInvalida(
            f"'{item_orcado.item.descricao}' não tem composição no catálogo — "
            "adote a composição da base referencial ou cadastre os componentes."
        )

    encargos = orcamento.encargos_sociais_percentual / CEM
    ItemOrcadoInsumo.objects.filter(item_orcado=item_orcado).delete()

    insumos, custo_unitario = [], Decimal("0")
    for item, coeficiente in folhas:
        categoria = categoria_do_item(item)
        preco = custo_de_referencia(item, orcamento.base_referencial) or Decimal("0")
        bruto = coeficiente * preco
        # Encargos sociais entram AQUI, sobre a parcela de mão de obra — não no
        # total da linha, senão incidiriam sobre material também.
        if categoria == ItemOrcadoInsumo.Categoria.MAO_DE_OBRA:
            bruto *= (UM + encargos)
        custo_no_item = bruto.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        custo_unitario += custo_no_item
        insumos.append(
            ItemOrcadoInsumo(
                tenant_id=tenant_id, item_orcado=item_orcado, item=item,
                descricao=item.descricao[:255], unidade=item.unidade,
                categoria=categoria, coeficiente=coeficiente,
                custo_unitario=preco, custo_no_item=custo_no_item,
            )
        )
    ItemOrcadoInsumo.objects.bulk_create(insumos)

    if atualizar_custo:
        item_orcado.custo_unitario = custo_unitario.quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        item_orcado.save(update_fields=["custo_unitario"])
    return insumos


def memoria_de_calculo(item_orcado: ItemOrcado) -> dict:
    """A composição da linha, com o peso de cada insumo e o resumo por categoria.

    O resumo material × mão de obra × equipamento é o que o orçamentista olha
    para saber se a composição faz sentido antes de fechar o preço.
    """
    insumos = list(ItemOrcadoInsumo.objects.filter(item_orcado=item_orcado).select_related("item"))
    total = sum((i.custo_no_item for i in insumos), Decimal("0"))
    por_categoria: dict[str, Decimal] = {}
    for insumo in insumos:
        por_categoria[insumo.categoria] = por_categoria.get(insumo.categoria, Decimal("0")) + insumo.custo_no_item

    return {
        "item_orcado": item_orcado.pk,
        "descricao": item_orcado.descricao,
        "unidade": item_orcado.unidade,
        "custo_unitario": str(item_orcado.custo_unitario),
        "total_composicao": str(total),
        "insumos": [
            {
                "insumo_id": i.insumo_id, "item": i.item_id, "descricao": i.descricao,
                "unidade": i.unidade, "categoria": i.categoria,
                "coeficiente": str(i.coeficiente), "custo_unitario": str(i.custo_unitario),
                "custo_no_item": str(i.custo_no_item),
                "peso_pct": str((i.custo_no_item / total * CEM).quantize(Decimal("0.01")))
                if total > 0 else "0",
            }
            for i in insumos
        ],
        "por_categoria": {
            categoria: {
                "valor": str(valor),
                "pct": str((valor / total * CEM).quantize(Decimal("0.01"))) if total > 0 else "0",
            }
            for categoria, valor in sorted(por_categoria.items())
        },
    }


# ---------------------------------------------------------------------------
# Curva ABC do orçado
# ---------------------------------------------------------------------------


def curva_abc(orcamento: Orcamento) -> dict:
    """Itens do orçamento por peso financeiro decrescente, classificados A/B/C.

    A regra prática do setor: ~20% dos itens respondem por ~80% do custo. É
    onde negociação de preço e controle de consumo valem a pena — e é a mesma
    leitura que o SIL faz do estoque, agora do lado do **planejado**.

    Mesma convenção de classe do SIL (`modulosil.views.CurvaABCView`): a classe
    é decidida pela acumulada **antes** do item, então o item de maior valor é
    sempre A, mesmo que sozinho passe de 80%.
    """
    linhas = list(
        ItemOrcado.objects.filter(
            orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO
        )
        .values("item_orcado_id", "codigo_eap", "descricao", "unidade", "quantidade", "item_id")
        .annotate(valor=Coalesce(Sum("total_custo_direto"), Decimal("0")))
        .order_by("-valor")
    )
    total = sum((linha["valor"] for linha in linhas), Decimal("0"))

    itens, acumulado = [], Decimal("0")
    for linha in linhas:
        valor = linha["valor"]
        pct_antes = (acumulado / total * CEM) if total > 0 else Decimal("0")
        classe = "A" if pct_antes < 80 else ("B" if pct_antes < 95 else "C")
        acumulado += valor
        itens.append({
            "item_orcado": linha["item_orcado_id"], "item": linha["item_id"],
            "codigo_eap": linha["codigo_eap"], "descricao": linha["descricao"],
            "unidade": linha["unidade"], "quantidade": str(linha["quantidade"]),
            "valor": str(valor),
            "pct": str((valor / total * CEM).quantize(Decimal("0.01"))) if total > 0 else "0",
            "pct_acumulado": str((acumulado / total * CEM).quantize(Decimal("0.01")))
            if total > 0 else "0",
            "classe": classe,
        })

    resumo = {c: {"itens": 0, "valor": Decimal("0")} for c in ("A", "B", "C")}
    for item in itens:
        resumo[item["classe"]]["itens"] += 1
        resumo[item["classe"]]["valor"] += Decimal(item["valor"])

    return {
        "orcamento": orcamento.pk,
        "total": str(dinheiro(total)),
        "resumo": {
            c: {
                "itens": v["itens"], "valor": str(v["valor"]),
                "pct": str((v["valor"] / total * CEM).quantize(Decimal("0.01"))) if total > 0 else "0",
            }
            for c, v in resumo.items()
        },
        "itens": itens,
    }


# ---------------------------------------------------------------------------
# Precificar pelo histórico real (SCM + SIL)
# ---------------------------------------------------------------------------


def preco_real_do_item(tenant_id, item_id) -> dict:
    """O que a empresa **de fato** pagou e carrega, ao lado do preço de tabela.

    Este é o dado que só um sistema integrado tem: o SCM sabe por quanto o item
    foi comprado (`ItemPedido` de pedidos efetivados), o SIL sabe o custo médio
    ponderado que está no estoque hoje. Orçar com o próprio histórico é mais
    preciso que orçar por mediana nacional da SINAPI — e sem sair da tela.

    Devolve `None` em cada eixo que não tem histórico, em vez de zero: "nunca
    comprei este item" e "comprei a R$ 0,00" são coisas diferentes.
    """
    from modulosil.models import SaldoEstoque
    from moduloscm.models import ItemPedido, PedidoCompra

    dec = DecimalField(max_digits=20, decimal_places=4)
    # Os apelidos não podem repetir o nome do campo agregado (`quantidade`) —
    # o ORM recusa `Sum("quantidade")` sob o apelido `quantidade`.
    compras = (
        ItemPedido.objects.filter(tenant_id=tenant_id, produto_id=item_id)
        .exclude(pedido__status=PedidoCompra.Status.RASCUNHO)
        .aggregate(
            medio=Avg("preco_unitario"),
            ultimo=Max("pedido__data_pedido"),
            quantidade_total=Coalesce(
                Sum("quantidade", output_field=dec), Decimal("0"), output_field=dec
            ),
        )
    )
    ultimo_preco = (
        ItemPedido.objects.filter(tenant_id=tenant_id, produto_id=item_id)
        .exclude(pedido__status=PedidoCompra.Status.RASCUNHO)
        .order_by("-pedido__data_pedido", "-item_pedido_id")
        .values_list("preco_unitario", flat=True)
        .first()
    )
    estoque = SaldoEstoque.objects.filter(tenant_id=tenant_id, item_id=item_id).aggregate(
        quantidade_total=Coalesce(
            Sum("quantidade", output_field=dec), Decimal("0"), output_field=dec
        ),
        valor=Coalesce(
            Sum(F("quantidade") * F("custo_medio"), output_field=dec), Decimal("0"), output_field=dec
        ),
    )
    quantidade_estoque = estoque["quantidade_total"]
    custo_medio = (
        (estoque["valor"] / quantidade_estoque) if quantidade_estoque > 0 else None
    )

    return {
        "item": item_id,
        "scm": {
            "preco_medio": str(compras["medio"]) if compras["medio"] is not None else None,
            "ultimo_preco": str(ultimo_preco) if ultimo_preco is not None else None,
            "ultima_compra": compras["ultimo"],
            "quantidade_comprada": str(compras["quantidade_total"]),
        },
        "sil": {
            "custo_medio": str(custo_medio.quantize(Decimal("0.0001"))) if custo_medio is not None else None,
            "quantidade_em_estoque": str(quantidade_estoque),
        },
    }


@transaction.atomic
def aplicar_preco_real(item_orcado: ItemOrcado, *, origem: str = "scm") -> ItemOrcado:
    """Troca o preço da linha pelo histórico real da empresa.

    `origem`: `scm` (preço médio de compra) ou `sil` (custo médio em estoque).
    Registra a troca no snapshot — a linha deixa de ter fonte de referência e
    passa a declarar que o preço é próprio, porque é exatamente isso que ele é.
    """
    if item_orcado.item_id is None:
        raise ComposicaoInvalida("A linha não aponta item do catálogo.")

    real = preco_real_do_item(item_orcado.tenant_id, item_orcado.item_id)
    bruto = real["scm"]["preco_medio"] if origem == "scm" else real["sil"]["custo_medio"]
    if bruto is None:
        raise ComposicaoInvalida(
            f"Sem histórico de {'compra' if origem == 'scm' else 'estoque'} para este item."
        )

    item_orcado.custo_unitario = Decimal(bruto).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    item_orcado.fonte_referencia = ""
    item_orcado.codigo_referencia = ""
    item_orcado.data_base_preco = None
    item_orcado.observacao = (f"Preço do histórico real ({origem.upper()})")[:255]
    item_orcado.save(update_fields=[
        "custo_unitario", "fonte_referencia", "codigo_referencia",
        "data_base_preco", "observacao",
    ])
    return item_orcado
