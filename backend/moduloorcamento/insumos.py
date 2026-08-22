# backend/moduloorcamento/insumos.py
"""O orçamento visto **por insumo**, não por serviço (ORC.7).

Até o ORC.6 o módulo enxergava a planilha só na dimensão em que ela é digitada:
etapa → serviço → linha. Isso responde "quanto custa o contrapiso?" e não
responde as duas perguntas que quem compra e quem audita fazem primeiro:

- **"quanto cimento esta obra consome no total?"** — a relação de insumos, que
  é a lista de compra da obra inteira e a ponte natural com a `Demanda` do SCM;
- **"quais insumos concentram o custo?"** — a curva ABC **de insumos**, que é a
  peça que edital pede e que não é a mesma coisa que a curva ABC de serviços já
  existente em `precificacao.curva_abc`.

A diferença entre as duas ABC é o ponto: a de serviços diz onde negociar
*escopo* (o contrapiso pesa 12% da obra), a de insumos diz onde negociar
*preço* (o aço aparece em nove serviços diferentes e, somado, pesa 18%). Um
orçamento sem a segunda mostra o cimento diluído em vinte linhas e nunca revela
que ele é o item A da obra.

**Toda resposta daqui declara cobertura.** O insumo só existe depois que a
composição foi explodida (`precificacao.explodir_item`), então uma planilha com
metade das linhas abertas produziria uma relação convincente e pela metade. A
`cobertura_pct` — ponderada por valor, não por contagem — é o que impede o
relatório de mentir por omissão.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

from .models import ItemOrcado, ItemOrcadoInsumo, Orcamento

CEM = Decimal("100")
DUAS = Decimal("0.01")

# Expressões reusadas: o insumo tem coeficiente **por unidade do serviço**, e o
# que interessa no orçamento é sempre coeficiente × quantidade da linha-pai.
_QUANTIDADE_NO_ORCAMENTO = ExpressionWrapper(
    F("coeficiente") * F("item_orcado__quantidade"),
    output_field=DecimalField(max_digits=24, decimal_places=6),
)
_VALOR_NO_ORCAMENTO = ExpressionWrapper(
    F("custo_no_item") * F("item_orcado__quantidade"),
    output_field=DecimalField(max_digits=24, decimal_places=4),
)


def _cobertura(orcamento: Orcamento) -> dict:
    """Quanto do custo direto está explodido — em valor, e em linhas."""
    analiticas = ItemOrcado.objects.filter(
        orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
    )
    total = analiticas.aggregate(soma=Sum("total_custo_direto"))["soma"] or Decimal("0")
    explodidas = analiticas.filter(insumos__isnull=False).distinct()
    coberto = explodidas.aggregate(soma=Sum("total_custo_direto"))["soma"] or Decimal("0")

    return {
        "custo_direto_total": str(total),
        "custo_direto_explodido": str(coberto),
        "cobertura_pct": str(
            (coberto / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP)
        ) if total > 0 else "0",
        "linhas_analiticas": analiticas.count(),
        "linhas_explodidas": explodidas.count(),
        "linhas_sem_composicao": analiticas.count() - explodidas.count(),
    }


def _consolidar(orcamento: Orcamento, *, categoria: str | None = None) -> list[dict]:
    """Agrupa os insumos de todas as linhas do orçamento.

    A chave do agrupamento é o `catalogo.Item`, e o `descricao`/`unidade` só
    entram como rótulo — insumo adotado de base referencial tem item, e é por
    ele que a relação casa com o que o SCM compra e o SIL estoca. Insumo sem
    item (composição própria digitada solta) cai num grupo por descrição, que é
    o melhor que existe sem inventar identidade.

    `custo_unitario` é o **médio ponderado** entre as ocorrências: o mesmo aço
    pode entrar em duas linhas com preços de datas-base diferentes depois de uma
    reprecificação parcial, e mostrar só o primeiro esconderia a divergência.
    """
    consulta = ItemOrcadoInsumo.objects.filter(item_orcado__orcamento=orcamento)
    if categoria:
        consulta = consulta.filter(categoria=categoria)

    linhas = (
        consulta
        .values("item_id", "descricao", "unidade", "categoria")
        .annotate(
            quantidade=Coalesce(Sum(_QUANTIDADE_NO_ORCAMENTO), Decimal("0")),
            valor=Coalesce(Sum(_VALOR_NO_ORCAMENTO), Decimal("0")),
            servicos=Count("item_orcado", distinct=True),
        )
        .order_by("-valor")
    )

    # Agrupa por item quando há item; por (descrição, unidade) quando não há. O
    # `values` acima já separa por descrição, então o passo extra só junta o que
    # é o mesmo `item_id` com descrições que divergiram entre snapshots.
    por_chave: dict[tuple, dict] = {}
    for linha in linhas:
        chave = (
            ("item", linha["item_id"]) if linha["item_id"]
            else ("texto", linha["descricao"], linha["unidade"])
        )
        acumulado = por_chave.setdefault(chave, {
            "item": linha["item_id"],
            "descricao": linha["descricao"],
            "unidade": linha["unidade"],
            "categoria": linha["categoria"],
            "quantidade": Decimal("0"),
            "valor": Decimal("0"),
            "servicos": 0,
        })
        acumulado["quantidade"] += linha["quantidade"]
        acumulado["valor"] += linha["valor"]
        acumulado["servicos"] += linha["servicos"]

    consolidados = sorted(por_chave.values(), key=lambda d: d["valor"], reverse=True)
    for registro in consolidados:
        quantidade = registro["quantidade"]
        registro["custo_unitario_medio"] = (
            (registro["valor"] / quantidade).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if quantidade else Decimal("0")
        )
    return consolidados


def _codigos_dos_itens(consolidados: list[dict]) -> dict[int, tuple[str, str]]:
    """Código e fonte de referência dos insumos, num SELECT só.

    A relação é uma lista de compra e uma peça de edital: sem o código SINAPI ao
    lado, nem o comprador acha o item no fornecedor nem o analista confere o
    preço na tabela.
    """
    from catalogo.models import Item

    ids = [r["item"] for r in consolidados if r["item"]]
    if not ids:
        return {}
    return {
        item_id: (codigo or "", fonte or "")
        for item_id, codigo, fonte in Item.objects.filter(item_id__in=ids).values_list(
            "item_id", "codigo_referencia", "fonte_referencia"
        )
    }


def relacao_de_insumos(orcamento: Orcamento, *, categoria: str | None = None) -> dict:
    """A **lista de compra da obra**: cada insumo uma vez, com quantidade total.

    É o relatório que faltava para o orçamento virar entrada do suprimento — e o
    motivo de ele nascer aqui e não no SCM: quem sabe explodir composição é este
    módulo. O SCM consome esta saída (`moduloscm` gera a `Demanda`), e nenhuma
    regra de compra vaza para cá.
    """
    consolidados = _consolidar(orcamento, categoria=categoria)
    codigos = _codigos_dos_itens(consolidados)
    total = sum((r["valor"] for r in consolidados), Decimal("0"))

    itens = []
    for registro in consolidados:
        codigo, fonte = codigos.get(registro["item"], ("", ""))
        itens.append({
            "item": registro["item"],
            "codigo_referencia": codigo,
            "fonte_referencia": fonte,
            "descricao": registro["descricao"],
            "unidade": registro["unidade"],
            "categoria": registro["categoria"],
            "rotulo_categoria": dict(ItemOrcadoInsumo.Categoria.choices).get(
                registro["categoria"], registro["categoria"]
            ),
            "quantidade": str(registro["quantidade"].quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "custo_unitario_medio": str(registro["custo_unitario_medio"]),
            "valor": str(registro["valor"].quantize(DUAS, rounding=ROUND_HALF_UP)),
            "pct": str((registro["valor"] / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP))
            if total > 0 else "0",
            "servicos": registro["servicos"],
        })

    return {
        "orcamento": orcamento.pk,
        "filtro_categoria": categoria or "",
        "total": str(total.quantize(DUAS, rounding=ROUND_HALF_UP)),
        "itens": itens,
        **_cobertura(orcamento),
    }


def curva_abc_insumos(orcamento: Orcamento) -> dict:
    """Curva ABC **de insumos** — a peça que faltava ao lado da de serviços.

    Mesma convenção de classe da curva ABC de serviços e da do consumo no SIL: a
    classe é decidida pela acumulada **antes** do item, então o insumo de maior
    valor é sempre A mesmo que sozinho ultrapasse 80%. Manter a convenção é o que
    permite pôr as três curvas lado a lado sem nota de rodapé.
    """
    consolidados = _consolidar(orcamento)
    codigos = _codigos_dos_itens(consolidados)
    total = sum((r["valor"] for r in consolidados), Decimal("0"))

    itens, acumulado = [], Decimal("0")
    for registro in consolidados:
        valor = registro["valor"]
        pct_antes = (acumulado / total * CEM) if total > 0 else Decimal("0")
        classe = "A" if pct_antes < 80 else ("B" if pct_antes < 95 else "C")
        acumulado += valor
        codigo, fonte = codigos.get(registro["item"], ("", ""))
        itens.append({
            "item": registro["item"],
            "codigo_referencia": codigo,
            "fonte_referencia": fonte,
            "descricao": registro["descricao"],
            "unidade": registro["unidade"],
            "categoria": registro["categoria"],
            "quantidade": str(registro["quantidade"].quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "custo_unitario_medio": str(registro["custo_unitario_medio"]),
            "valor": str(valor.quantize(DUAS, rounding=ROUND_HALF_UP)),
            "pct": str((valor / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP)) if total > 0 else "0",
            "pct_acumulado": str((acumulado / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP))
            if total > 0 else "0",
            "classe": classe,
            "servicos": registro["servicos"],
        })

    resumo = {c: {"itens": 0, "valor": Decimal("0")} for c in ("A", "B", "C")}
    for item in itens:
        resumo[item["classe"]]["itens"] += 1
        resumo[item["classe"]]["valor"] += Decimal(item["valor"])

    return {
        "orcamento": orcamento.pk,
        "total": str(total.quantize(DUAS, rounding=ROUND_HALF_UP)),
        "resumo": {
            c: {
                "itens": v["itens"],
                "valor": str(v["valor"]),
                "pct": str((v["valor"] / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP))
                if total > 0 else "0",
            }
            for c, v in resumo.items()
        },
        "itens": itens,
        **_cobertura(orcamento),
    }


# ---------------------------------------------------------------------------
# A separação por natureza — material × mão de obra × equipamento
# ---------------------------------------------------------------------------
#
# É como ORSE e Arquimedes imprimem a composição, e não é preferência estética:
# as três naturezas têm regimes diferentes. Encargo social incide só sobre mão
# de obra; material entra na relação de compra e no estoque; equipamento tem
# custo horário produtivo × improdutivo e admite BDI diferenciado pelo TCU.
# Somá-los numa coluna só apaga exatamente a informação que decide a ação.


def composicao_por_natureza(item_orcado: ItemOrcado) -> dict:
    """A composição de **uma linha**, agrupada nas três naturezas.

    Cada grupo traz seu subtotal e seu peso na linha, que é a leitura de sanidade
    do orçamentista: um serviço de alvenaria com 90% de material e 10% de mão de
    obra tem coeficiente de produtividade errado, e isso salta aos olhos aqui e
    em nenhum outro lugar.
    """
    insumos = list(
        ItemOrcadoInsumo.objects.filter(item_orcado=item_orcado).order_by("categoria", "descricao")
    )
    total = sum((i.custo_no_item for i in insumos), Decimal("0"))

    grupos: dict[str, dict] = {}
    for insumo in insumos:
        bloco = grupos.setdefault(insumo.categoria, {
            "categoria": insumo.categoria,
            "rotulo": dict(ItemOrcadoInsumo.Categoria.choices).get(insumo.categoria, insumo.categoria),
            "subtotal": Decimal("0"),
            "insumos": [],
        })
        bloco["subtotal"] += insumo.custo_no_item
        bloco["insumos"].append({
            "insumo": insumo.pk,
            "item": insumo.item_id,
            "descricao": insumo.descricao,
            "unidade": insumo.unidade,
            "coeficiente": str(insumo.coeficiente),
            "custo_unitario": str(insumo.custo_unitario),
            "custo_no_item": str(insumo.custo_no_item),
            "pct": str((insumo.custo_no_item / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP))
            if total > 0 else "0",
        })

    # A ordem é a da analítica impressa (ORSE, Arquimedes): material, gente,
    # máquina, o complemento do trabalhador e o resto.
    ordem = [
        ItemOrcadoInsumo.Categoria.MATERIAL,
        ItemOrcadoInsumo.Categoria.MAO_DE_OBRA,
        ItemOrcadoInsumo.Categoria.EQUIPAMENTO,
        ItemOrcadoInsumo.Categoria.ENCARGOS_COMPLEMENTARES,
        ItemOrcadoInsumo.Categoria.OUTRO,
    ]
    blocos = []
    for categoria in ordem:
        if categoria not in grupos:
            continue
        bloco = grupos[categoria]
        bloco["pct"] = str((bloco["subtotal"] / total * CEM).quantize(DUAS, rounding=ROUND_HALF_UP)) \
            if total > 0 else "0"
        bloco["subtotal"] = str(bloco["subtotal"].quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        blocos.append(bloco)

    return {
        "item_orcado": item_orcado.pk,
        "codigo_eap": item_orcado.codigo_eap,
        "descricao": item_orcado.descricao,
        "unidade": item_orcado.unidade,
        "quantidade": str(item_orcado.quantidade),
        "custo_unitario": str(item_orcado.custo_unitario),
        "total_composicao": str(total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "confere_com_a_linha": total.quantize(Decimal("0.0001")) == item_orcado.custo_unitario,
        "grupos": blocos,
    }


def resumo_por_natureza(orcamento: Orcamento, *, por_etapa: bool = False) -> dict:
    """Material × mão de obra × equipamento no orçamento — e, se pedido, por etapa.

    O corte por etapa é o que transforma o gráfico em decisão: uma obra 60%
    material no total pode ser 90% mão de obra na etapa de acabamento, e é essa
    etapa que precisa de efetivo contratado com antecedência.
    """
    consulta = ItemOrcadoInsumo.objects.filter(item_orcado__orcamento=orcamento)
    campos = ["categoria"]
    if por_etapa:
        campos = ["item_orcado__etapa", "item_orcado__etapa__nome_etapa", "categoria"]

    linhas = (
        consulta.values(*campos)
        .annotate(valor=Coalesce(Sum(_VALOR_NO_ORCAMENTO), Decimal("0")))
        .order_by("-valor")
    )
    rotulos = dict(ItemOrcadoInsumo.Categoria.choices)
    total = sum((linha["valor"] for linha in linhas), Decimal("0"))

    def bloco(valor: Decimal, categoria: str, base: Decimal) -> dict:
        return {
            "categoria": categoria,
            "rotulo": rotulos.get(categoria, categoria),
            "valor": str(valor.quantize(DUAS, rounding=ROUND_HALF_UP)),
            "pct": str((valor / base * CEM).quantize(DUAS, rounding=ROUND_HALF_UP)) if base > 0 else "0",
        }

    resposta = {
        "orcamento": orcamento.pk,
        "total": str(total.quantize(DUAS, rounding=ROUND_HALF_UP)),
        **_cobertura(orcamento),
    }

    if not por_etapa:
        resposta["categorias"] = [bloco(l["valor"], l["categoria"], total) for l in linhas]
        return resposta

    por_etapa_mapa: dict = {}
    for linha in linhas:
        chave = linha["item_orcado__etapa"]
        etapa = por_etapa_mapa.setdefault(chave, {
            "etapa": chave,
            "nome": linha["item_orcado__etapa__nome_etapa"] or "Sem etapa",
            "total": Decimal("0"),
            "_linhas": [],
        })
        etapa["total"] += linha["valor"]
        etapa["_linhas"].append(linha)

    etapas = []
    for etapa in sorted(por_etapa_mapa.values(), key=lambda e: e["total"], reverse=True):
        base = etapa["total"]
        etapas.append({
            "etapa": etapa["etapa"],
            "nome": etapa["nome"],
            "total": str(base.quantize(DUAS, rounding=ROUND_HALF_UP)),
            "categorias": [bloco(l["valor"], l["categoria"], base) for l in etapa["_linhas"]],
        })
    resposta["etapas"] = etapas
    return resposta
