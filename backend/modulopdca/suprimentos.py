# backend/modulopdca/suprimentos.py
"""O cronograma **puxa a compra** — a necessidade de material no tempo.

*(Decisão do dono, 09/10/2026: "quero que o PDCA, o orçamento, os pedidos e o
estoque se conversem".)* Cada módulo já sabia a sua parte e ninguém juntava:

- o **orçamento** sabe quanto de cada insumo um serviço consome (a composição
  explodida, `ItemOrcadoInsumo`: coeficiente × quantidade da linha);
- o **plano** sabe quando cada serviço começa (o CPM) e quanto já andou;
- o **estoque** sabe o que tem na obra; o **Suprimentos**, o que já foi pedido.

Aqui as quatro coisas viram uma lista: *este insumo, esta quantidade, chegar até
este dia — e quanto disso ainda falta comprar*.

**De onde vem a quantidade** (decisão "os dois"): pela **atividade** quando ela
está ligada a um item orçado — a linha inteira dividida entre as atividades que
a usam, pela duração —, e pela **etapa** quando não está: os itens do orçamento
vigente daquela etapa que nenhuma atividade cita caem na atividade da etapa que
começa primeiro. O que já foi executado sai da conta (`1 − avanço`): material
de serviço pronto já foi consumido, e pedir de novo seria comprar duas vezes.

**Quando** (decisão "o planejador define, com padrão e exceção por item"): o
material chega `antecedência` dias antes do início — a da atividade, senão a do
insumo, senão o padrão da obra, senão zero. *Pedir até* desconta ainda o prazo
de entrega do fornecedor, quando alguma oferta o informa.

**Quanto falta comprar**: por insumo, na ordem das datas, o que está no estoque
da obra cobre primeiro, depois o que já está pedido, depois o que já está em
demanda. Só o resto é "a comprar" — e é por isso que gerar a demanda duas vezes
não compra duas vezes: a segunda leitura já vê a primeira.

Importa orçamento, Suprimentos e estoque **tarde**, pelo mesmo motivo do título
no ERP: o planejamento continua carregando numa instalação sem eles.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import AntecedenciaDeCompra, Atividade, Cronograma

#: As naturezas de insumo que se compram, e o tipo de demanda que cada uma
#: abre. Mão de obra é contratação (vira contrato e medição, não compra).
_TIPO_DA_CATEGORIA = {"material": "material", "equipamento": "servico"}

ZERO = Decimal("0")
_Q3 = Decimal("0.001")
#: Campos em reais (duas casas); o resto é quantidade (três).
_CHAVES_DE_DINHEIRO = frozenset({
    "custo_unitario", "orcado", "comprometido", "recebido", "aplicado", "medido",
})


def _chave(item_id, descricao: str, unidade: str) -> str:
    """O insumo como chave: pelo item do catálogo, ou pelo texto quando não há.
    É a mesma regra da relação de insumos do orçamento."""
    return f"i{item_id}" if item_id else f"t:{descricao.strip().lower()}|{unidade.strip().lower()}"


def antecedencias_da_obra(obra_id: int, *, tenant_id) -> tuple[int | None, dict[int, int]]:
    """`(padrão da obra, {item: dias})` — uma consulta."""
    padrao = None
    por_item: dict[int, int] = {}
    for item_id, dias in AntecedenciaDeCompra.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
    ).values_list("item_id", "dias"):
        if item_id is None:
            padrao = dias
        else:
            por_item[item_id] = dias
    return padrao, por_item


def _prazos_de_entrega(itens: set[int]) -> dict[int, int]:
    """O menor prazo de entrega informado nas ofertas ativas de cada item."""
    if not itens:
        return {}
    try:
        from moduloscm.models import OfertaFornecedor
    except ImportError:  # pragma: no cover — instalação sem Suprimentos
        return {}
    prazos: dict[int, int] = {}
    for item_id, prazo in OfertaFornecedor.objects.filter(
        produto_id__in=itens, ativo=True, prazo_entrega_dias__isnull=False,
    ).values_list("produto_id", "prazo_entrega_dias"):
        prazos[item_id] = min(prazo, prazos.get(item_id, prazo))
    return prazos


def disponivel_na_obra(obra_id: int, itens: set[int], *, tenant_id) -> dict[int, dict]:
    """Por item: `{estoque, em_pedido, em_demanda}` desta obra.

    - **estoque**: saldo livre (quantidade − reservado) nos locais de estoque da
      obra (o canteiro);
    - **em pedido**: o que os pedidos em aberto do centro de custo da obra ainda
      não entregaram;
    - **em demanda**: o que as demandas ainda sem pedido já pediram.
    """
    saida = {i: {"estoque": ZERO, "em_pedido": ZERO, "em_demanda": ZERO} for i in itens}
    if not itens:
        return saida
    try:
        from modulosil.models import SaldoEstoque

        for item_id, qtd, reservado in SaldoEstoque.objects.filter(
            tenant_id=tenant_id, local__obra_id=obra_id, local__ativo=True, item_id__in=itens,
        ).values_list("item_id", "quantidade", "reservado"):
            saida[item_id]["estoque"] += max(ZERO, (qtd or ZERO) - (reservado or ZERO))
    except ImportError:  # pragma: no cover
        pass
    try:
        from moduloscm.models import Demanda, ItemDemanda, ItemPedido, PedidoCompra

        abertos = (PedidoCompra.Status.RASCUNHO, PedidoCompra.Status.APROVADO,
                   PedidoCompra.Status.ENVIADO, PedidoCompra.Status.RECEBIDO_PARCIAL)
        for linha in (ItemPedido.objects
                      .filter(tenant_id=tenant_id, produto_id__in=itens,
                              pedido__centro_custo__obra_id=obra_id, pedido__status__in=abertos)
                      .annotate(recebido=Sum("recebimentos_item__quantidade_recebida"))
                      .values("produto_id", "quantidade", "recebido")):
            falta = (linha["quantidade"] or ZERO) - (linha["recebido"] or ZERO)
            if falta > 0:
                saida[linha["produto_id"]]["em_pedido"] += falta
        sem_pedido = (Demanda.Status.RASCUNHO, Demanda.Status.ABERTA, Demanda.Status.EM_COTACAO)
        for item_id, qtd in ItemDemanda.objects.filter(
            tenant_id=tenant_id, produto_id__in=itens,
            demanda__centro_custo__obra_id=obra_id, demanda__status__in=sem_pedido,
        ).values_list("produto_id", "quantidade"):
            saida[item_id]["em_demanda"] += qtd or ZERO
    except ImportError:  # pragma: no cover
        pass
    return saida


def disponivel_fora_da_obra(itens: set[int], *, tenant_id, obra_id) -> dict[int, Decimal]:
    """Saldo livre de cada item nos almoxarifados **que não são da obra** —
    o central e o canteiro de outras obras (a sobra que voltou ou que ficou).

    Não abate a necessidade (várias obras disputariam o mesmo saldo); é o aviso
    "transfira antes de comprar", que é como a sobra de uma obra vira o
    material da próxima *(decisão do dono: sobra e devolução abatem a próxima
    necessidade)*.
    """
    saida: dict[int, Decimal] = defaultdict(lambda: ZERO)
    if not itens:
        return saida
    try:
        from modulosil.models import SaldoEstoque
    except ImportError:  # pragma: no cover
        return saida
    for item_id, qtd, reservado in (SaldoEstoque.objects
                                    .filter(tenant_id=tenant_id, item_id__in=itens, local__ativo=True)
                                    .exclude(local__obra_id=obra_id)
                                    .exclude(local__tipo="fornecedor")
                                    .values_list("item_id", "quantidade", "reservado")):
        saida[item_id] += max(ZERO, (qtd or ZERO) - (reservado or ZERO))
    return saida


def _atividades_e_avanco(cronograma: Cronograma) -> tuple[list[Atividade], dict[int, Decimal]]:
    """As atividades do plano e o avanço (0–100) de cada uma."""
    from .services import avanco_do_cronograma

    atividades = list(cronograma.atividades.select_related("item_orcado").all())
    avanco = {
        aid: Decimal(str(v["avanco"])) if v.get("avanco") is not None else ZERO
        for aid, v in avanco_do_cronograma(cronograma)["por_atividade"].items()
    }
    return atividades, avanco


def consumo_do_plano(cronograma: Cronograma, atividades: list[Atividade]) -> dict:
    """**Quem consome quanto de cada insumo** — a regra única da quantidade.

    Usada pela necessidade de compra (o que falta) e pelo consumo teórico do
    apontamento (o que já devia ter saído do estoque). Devolve o par
    `(atividade, item orçado, fração, origem)` de cada consumo, a quantidade de
    cada linha orçada e os insumos compráveis de cada uma.

    - **Pela atividade** ligada a item orçado: a linha dividida entre as
      atividades que a citam, pela duração.
    - **Pela etapa**: os itens do orçamento vigente daquela etapa que nenhuma
      atividade cita caem na atividade da etapa que começa primeiro.
    - **Revisão do orçamento** (aditivo): atividade ligada a um item de versão
      **anterior** do orçamento é lida pelo item de mesmo código EAP na versão
      vigente — a quantidade revisada passa a valer no plano e no que falta
      comprar sem religar atividade por atividade. `remapeadas` conta quantas.
    """
    from moduloorcamento.models import ItemOrcado, ItemOrcadoInsumo
    from moduloorcamento.planilha import orcamento_vigente

    tenant_id = cronograma.tenant_id
    obra_id = cronograma.obra_id
    com_filhos = {a.pai_id for a in atividades if a.pai_id}
    folhas = [a for a in atividades if a.atividade_id not in com_filhos and not a.eh_marco]
    orcamento = orcamento_vigente(tenant_id, obra_id) if obra_id else None

    # A versão vigente pelo código EAP: o item de revisão anterior vira o atual.
    no_vigente: dict[str, int] = {}
    if orcamento is not None:
        no_vigente = dict(
            ItemOrcado.objects.filter(orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO)
            .exclude(codigo_eap="").values_list("codigo_eap", "item_orcado_id")
        )
    ligados = {a.item_orcado_id for a in folhas if a.item_orcado_id}
    origem_do_item = dict(
        ItemOrcado.objects.filter(item_orcado_id__in=ligados).values_list("item_orcado_id", "orcamento_id")
    )
    codigo_do_item = dict(
        ItemOrcado.objects.filter(item_orcado_id__in=ligados).values_list("item_orcado_id", "codigo_eap")
    )
    remapeadas = 0

    por_item_orcado: dict[int, list[Atividade]] = defaultdict(list)
    for a in folhas:
        if not a.item_orcado_id:
            continue
        efetivo = a.item_orcado_id
        if (orcamento is not None and origem_do_item.get(efetivo) != orcamento.pk
                and codigo_do_item.get(efetivo) in no_vigente):
            efetivo = no_vigente[codigo_do_item[efetivo]]
            remapeadas += 1
        por_item_orcado[efetivo].append(a)
    consumo: list[tuple[Atividade, int, Decimal, str]] = []
    for item_id, quem in por_item_orcado.items():
        pesos = [Decimal(max(1, a.duracao_dias or 1)) for a in quem]
        total = sum(pesos)
        for a, p in zip(quem, pesos):
            consumo.append((a, item_id, p / total, "atividade"))

    etapas_sem_orcamento = 0
    if orcamento is not None:
        primeira_da_etapa: dict[int, Atividade] = {}
        for a in sorted(
            (x for x in atividades if x.etapa_id and x.inicio_cedo),
            key=lambda x: (x.inicio_cedo, x.profundidade),
        ):
            primeira_da_etapa.setdefault(a.etapa_id, a)
        soltos = (ItemOrcado.objects
                  .filter(orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
                          etapa_id__in=list(primeira_da_etapa))
                  .exclude(item_orcado_id__in=list(por_item_orcado))
                  .values_list("item_orcado_id", "etapa_id"))
        for item_id, etapa_id in soltos:
            consumo.append((primeira_da_etapa[etapa_id], item_id, Decimal(1), "etapa"))
        etapas_plano = {a.etapa_id for a in atividades if a.etapa_id}
        etapas_sem_orcamento = len(etapas_plano - set(primeira_da_etapa))

    itens_orcados = {item_id for _, item_id, _, _ in consumo}
    quantidade_da_linha = dict(
        ItemOrcado.objects.filter(item_orcado_id__in=itens_orcados).values_list("item_orcado_id", "quantidade")
    )
    insumos_por_linha: dict[int, list] = defaultdict(list)
    for ins in ItemOrcadoInsumo.objects.filter(
        item_orcado_id__in=itens_orcados, categoria__in=list(_TIPO_DA_CATEGORIA),
    ).values("item_orcado_id", "item_id", "descricao", "unidade", "categoria", "coeficiente", "custo_unitario"):
        insumos_por_linha[ins["item_orcado_id"]].append(ins)

    return {
        "folhas": folhas, "consumo": consumo, "orcamento": orcamento,
        "quantidade_da_linha": quantidade_da_linha, "insumos_por_linha": insumos_por_linha,
        "etapas_sem_orcamento": etapas_sem_orcamento, "remapeadas": remapeadas,
    }


def necessidade_de_material(cronograma: Cronograma, *, hoje: date | None = None) -> dict:
    """A lista "este insumo, esta quantidade, chegar até este dia — e quanto falta".

    Ver a docstring do módulo para as quatro regras (quantidade, data, execução e
    abatimento). Devolve as **linhas** (uma por atividade × insumo, na ordem de
    "pedir até"), o **resumo por insumo** e a **cobertura** — quantas atividades
    ficaram de fora por não terem item orçado nem etapa com orçamento, para a
    tela dizer em vez de mostrar uma lista convincente e pela metade.
    """
    hoje = hoje or timezone.localdate()
    tenant_id = cronograma.tenant_id
    obra_id = cronograma.obra_id
    atividades, avancos = _atividades_e_avanco(cronograma)
    plano = consumo_do_plano(cronograma, atividades)
    folhas = plano["folhas"]
    consumo = plano["consumo"]
    orcamento = plano["orcamento"]
    quantidade_da_linha = plano["quantidade_da_linha"]
    insumos_por_linha = plano["insumos_por_linha"]

    # 3. A data: antecedência da atividade > do insumo > padrão da obra > zero.
    padrao, por_item = antecedencias_da_obra(obra_id, tenant_id=tenant_id) if obra_id else (None, {})
    catalogo = {ins["item_id"] for lista in insumos_por_linha.values() for ins in lista if ins["item_id"]}
    prazos = _prazos_de_entrega(catalogo)

    linhas = []
    for a, item_orcado_id, fracao, origem in consumo:
        if not a.inicio_cedo:
            continue
        feito = min(Decimal(100), avancos.get(a.atividade_id, ZERO)) / Decimal(100)
        qtd_linha = quantidade_da_linha.get(item_orcado_id) or ZERO
        for ins in insumos_por_linha.get(item_orcado_id, []):
            total = (ins["coeficiente"] or ZERO) * qtd_linha * fracao
            restante = total * (1 - feito)
            if restante <= 0:
                continue
            if a.antecedencia_compra_dias is not None:
                dias, de_onde = a.antecedencia_compra_dias, "atividade"
            elif ins["item_id"] in por_item:
                dias, de_onde = por_item[ins["item_id"]], "insumo"
            elif padrao is not None:
                dias, de_onde = padrao, "obra"
            else:
                dias, de_onde = 0, "nenhuma"
            chegar = a.inicio_cedo - timedelta(days=dias)
            prazo = prazos.get(ins["item_id"])
            linhas.append({
                "atividade": a.atividade_id, "atividade_codigo": a.codigo, "atividade_nome": a.nome,
                "etapa": a.etapa_id, "origem": origem, "item_orcado": item_orcado_id,
                "insumo": _chave(ins["item_id"], ins["descricao"], ins["unidade"]),
                "item": ins["item_id"], "descricao": ins["descricao"], "unidade": ins["unidade"],
                "categoria": ins["categoria"], "tipo_demanda": _TIPO_DA_CATEGORIA[ins["categoria"]],
                "quantidade": total, "restante": restante, "executado_pct": feito * 100,
                "inicio_atividade": a.inicio_cedo,
                "antecedencia_dias": dias, "antecedencia_origem": de_onde,
                "chegar_ate": chegar, "prazo_fornecedor_dias": prazo,
                "pedir_ate": chegar - timedelta(days=prazo) if prazo else chegar,
                "custo_unitario": ins["custo_unitario"] or ZERO,
            })
    # O material informado na própria atividade — a obra sem orçamento, ou o
    # serviço que ficou fora dele. Mesmas regras: data pelo início, o executado
    # sai da conta, antecedência da atividade > do insumo > da obra.
    from .models import MaterialDaAtividade

    por_id = {a.atividade_id: a for a in atividades}
    manuais = list(MaterialDaAtividade.objects.filter(atividade__cronograma=cronograma))
    extra = {m.item_id for m in manuais if m.item_id} - catalogo
    if extra:
        catalogo |= extra
        prazos.update(_prazos_de_entrega(extra))
    com_material = set()
    for m in manuais:
        a = por_id.get(m.atividade_id)
        if a is None or not a.inicio_cedo:
            continue
        com_material.add(a.atividade_id)
        feito = min(Decimal(100), avancos.get(a.atividade_id, ZERO)) / Decimal(100)
        restante = m.quantidade * (1 - feito)
        if restante <= 0:
            continue
        if a.antecedencia_compra_dias is not None:
            dias, de_onde = a.antecedencia_compra_dias, "atividade"
        elif m.item_id in por_item:
            dias, de_onde = por_item[m.item_id], "insumo"
        elif padrao is not None:
            dias, de_onde = padrao, "obra"
        else:
            dias, de_onde = 0, "nenhuma"
        chegar = a.inicio_cedo - timedelta(days=dias)
        prazo = prazos.get(m.item_id)
        linhas.append({
            "atividade": a.atividade_id, "atividade_codigo": a.codigo, "atividade_nome": a.nome,
            "etapa": a.etapa_id, "origem": "informado", "item_orcado": None,
            "insumo": _chave(m.item_id, m.descricao, m.unidade),
            "item": m.item_id, "descricao": m.descricao, "unidade": m.unidade,
            "categoria": m.categoria, "tipo_demanda": _TIPO_DA_CATEGORIA[m.categoria],
            "quantidade": m.quantidade, "restante": restante, "executado_pct": feito * 100,
            "inicio_atividade": a.inicio_cedo,
            "antecedencia_dias": dias, "antecedencia_origem": de_onde,
            "chegar_ate": chegar, "prazo_fornecedor_dias": prazo,
            "pedir_ate": chegar - timedelta(days=prazo) if prazo else chegar,
            "custo_unitario": m.custo_unitario or ZERO,
        })
    linhas.sort(key=lambda l: (l["pedir_ate"], l["descricao"]))

    # 4. O abatimento, por insumo e na ordem das datas: estoque, pedido, demanda.
    livre = disponivel_na_obra(obra_id, catalogo, tenant_id=tenant_id) if obra_id else {}
    fora = disponivel_fora_da_obra(catalogo, tenant_id=tenant_id, obra_id=obra_id) if obra_id else {}
    sobra = {i: dict(v) for i, v in livre.items()}
    resumo: dict[str, dict] = {}
    for l in linhas:
        falta = l["restante"]
        cobre = {"estoque": ZERO, "em_pedido": ZERO, "em_demanda": ZERO}
        if l["item"] in sobra:
            for fonte in ("estoque", "em_pedido", "em_demanda"):
                usa = min(falta, sobra[l["item"]][fonte])
                cobre[fonte] = usa
                sobra[l["item"]][fonte] -= usa
                falta -= usa
        l["coberto_estoque"], l["coberto_pedido"], l["coberto_demanda"] = (
            cobre["estoque"], cobre["em_pedido"], cobre["em_demanda"])
        l["a_comprar"] = falta
        l["situacao"] = ("coberta" if falta <= 0
                         else "atrasada" if l["pedir_ate"] < hoje else "comprar")
        r = resumo.setdefault(l["insumo"], {
            "insumo": l["insumo"], "item": l["item"], "descricao": l["descricao"],
            "unidade": l["unidade"], "categoria": l["categoria"], "tipo_demanda": l["tipo_demanda"],
            "necessario": ZERO, "a_comprar": ZERO, "primeiro_pedir_ate": l["pedir_ate"],
            "estoque": (livre.get(l["item"]) or {}).get("estoque", ZERO),
            "em_pedido": (livre.get(l["item"]) or {}).get("em_pedido", ZERO),
            "em_demanda": (livre.get(l["item"]) or {}).get("em_demanda", ZERO),
            "valor_a_comprar": ZERO, "atividades": 0,
            "fora_da_obra": fora.get(l["item"], ZERO) if l["item"] else ZERO,
        })
        r["necessario"] += l["restante"]
        r["a_comprar"] += falta
        r["valor_a_comprar"] += falta * l["custo_unitario"]
        r["atividades"] += 1
        if falta > 0 and (r.get("primeira_falta") is None or l["pedir_ate"] < r["primeira_falta"]):
            r["primeira_falta"] = l["pedir_ate"]

    # Cobertura: a folha entra na conta pelo próprio item orçado ou por estar
    # dentro de uma atividade (a etapa) que recebeu itens pela etapa.
    na_conta = {a.atividade_id for a, _, _, _ in consumo} | com_material
    filhos: dict[int, list[int]] = defaultdict(list)
    for a in atividades:
        if a.pai_id:
            filhos[a.pai_id].append(a.atividade_id)
    cobertas = set(na_conta)
    pilha = list(na_conta)
    while pilha:
        for f in filhos.get(pilha.pop(), []):
            if f not in cobertas:
                cobertas.add(f)
                pilha.append(f)
    return {
        "cronograma": cronograma.cronograma_id,
        "obra": obra_id,
        "orcamento": orcamento.pk if orcamento else None,
        "antecedencia_padrao": padrao,
        "linhas": [_texto(l) for l in linhas],
        "por_insumo": [_texto(r) for r in sorted(
            resumo.values(), key=lambda r: (r.get("primeira_falta") or date.max, r["descricao"]))],
        "cobertura": {
            "folhas": len(folhas),
            "folhas_com_item_orcado": sum(1 for a in folhas if a.item_orcado_id),
            "folhas_fora_da_conta": sum(1 for a in folhas if a.atividade_id not in cobertas),
            "etapas_sem_orcamento": plano["etapas_sem_orcamento"],
            "ligadas_a_versao_anterior": plano["remapeadas"],
            "tem_orcamento_vigente": orcamento is not None,
            "folhas_com_material_informado": len(com_material),
        },
    }


def _texto(d: dict) -> dict:
    """Decimal em texto (3 casas para quantidade, 2 para dinheiro) e data ISO."""
    saida = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            casas = Decimal("0.01") if (k.startswith("valor") or k in _CHAVES_DE_DINHEIRO
                                        or k.endswith("_pct")) else _Q3
            saida[k] = str(v.quantize(casas, rounding=ROUND_HALF_UP))
        elif isinstance(v, date):
            saida[k] = v.isoformat()
        else:
            saida[k] = v
    return saida


def centro_de_custo_da_obra(obra):
    """O centro de custo da obra no Suprimentos — criado se ainda não existe.

    É por ele que a necessidade enxerga o que já foi pedido e demandado. Uma
    demanda sem centro de custo some dessa conta, e a próxima leitura mandaria
    comprar de novo o que acabou de ser pedido.
    """
    from moduloscm.models import CentroCusto

    centro = (CentroCusto.objects
              .filter(tenant_id=obra.tenant_id, obra=obra, ativo=True)
              .order_by("centro_custo_id").first())
    if centro is None:
        centro = CentroCusto.objects.create(
            tenant_id=obra.tenant_id, obra=obra, nome=obra.nome_obra[:150],
            tipo=CentroCusto.Tipo.OBRA,
        )
    return centro


@transaction.atomic
def gerar_demandas_do_plano(cronograma: Cronograma, *, insumos: list[str] | None = None,
                            ate: date | None = None, solicitante=None) -> list[dict]:
    """A fila vira **demanda** no Suprimentos — o que falta comprar, nada além.

    Uma demanda por tipo (material; serviço para locação de equipamento), um item
    por insumo com a soma do que falta, em **rascunho**: o comprador agrupa,
    corta e publica. `insumos` restringe às chaves escolhidas; `ate`, ao que se
    precisa pedir até aquela data. O centro de custo é o da obra.

    Não grava vínculo de volta: a próxima leitura da necessidade já conta a
    demanda aberta como "em demanda" — é o que impede comprar duas vezes.
    """
    from moduloscm.models import Demanda, ItemDemanda

    necessidade = necessidade_de_material(cronograma)
    escolhidas = [
        l for l in necessidade["linhas"]
        if Decimal(l["a_comprar"]) > 0
        and (not insumos or l["insumo"] in insumos)
        and (ate is None or date.fromisoformat(l["pedir_ate"]) <= ate)
    ]
    if not escolhidas:
        return []
    obra_nome = getattr(cronograma.obra, "nome_obra", "") if cronograma.obra_id else ""
    centro = centro_de_custo_da_obra(cronograma.obra) if cronograma.obra_id else None

    criadas = []
    for tipo in ("material", "servico"):
        do_tipo = [l for l in escolhidas if l["tipo_demanda"] == tipo]
        if not do_tipo:
            continue
        por_insumo: dict[str, dict] = {}
        for l in do_tipo:
            r = por_insumo.setdefault(l["insumo"], {
                "item": l["item"], "descricao": l["descricao"], "unidade": l["unidade"],
                "quantidade": ZERO, "chegar_ate": l["chegar_ate"], "atividades": [],
            })
            r["quantidade"] += Decimal(l["a_comprar"])
            r["chegar_ate"] = min(r["chegar_ate"], l["chegar_ate"])
            r["atividades"].append(l["atividade_codigo"])
        primeira = min(r["chegar_ate"] for r in por_insumo.values())
        demanda = Demanda.objects.create(
            tenant_id=cronograma.tenant_id, tipo=tipo, centro_custo=centro,
            solicitante=solicitante if getattr(solicitante, "pk", None) else None,
            status=Demanda.Status.RASCUNHO, origem=Demanda.Origem.PLANO,
            observacao=(
                f"Do cronograma{f' da obra {obra_nome}' if obra_nome else ''} "
                f"(v{cronograma.versao}) — primeiro material para chegar até "
                f"{date.fromisoformat(primeira):%d/%m/%Y}. "
                + "; ".join(
                    f"{r['descricao']}: chegar até {date.fromisoformat(r['chegar_ate']):%d/%m} "
                    f"({', '.join(sorted(set(r['atividades'])))})"
                    for r in por_insumo.values()
                )
            )[:4000],
        )
        ItemDemanda.objects.bulk_create([
            ItemDemanda(
                tenant_id=cronograma.tenant_id, demanda=demanda, produto_id=r["item"],
                descricao_servico="" if r["item"] else r["descricao"][:255],
                quantidade=r["quantidade"].quantize(_Q3, rounding=ROUND_HALF_UP),
                unidade=r["unidade"] or "",
            )
            for r in por_insumo.values()
        ])
        criadas.append({"demanda": demanda.pk, "tipo": tipo, "itens": len(por_insumo)})
    if criadas:
        from nucleo.models import Notificacao
        from nucleo.notificacoes import avisar_quem_pode

        avisar_quem_pode(
            tenant_id=cronograma.tenant_id, permissao="scm.demanda.edit",
            titulo=(
                f"Plano{f' da obra {obra_nome}' if obra_nome else ''} abriu "
                f"{len(criadas)} demanda(s) de compra: "
                + ", ".join(str(c["demanda"]) for c in criadas)
            ),
            mensagem=(
                f"Do cronograma v{cronograma.versao}; o primeiro material precisa chegar "
                f"até {date.fromisoformat(min(l['chegar_ate'] for l in escolhidas)):%d/%m/%Y}. "
                f"Nasceram em rascunho: confira e publique."
            ),
            url="/app/scm", nivel=Notificacao.Nivel.DECIDIR,
        )
    return criadas


def fila_de_compras_das_obras(tenant_id) -> dict:
    """A **mesma fila** vista pelo Suprimentos: por insumo, juntando as obras.

    Lê o plano **vigente** de cada obra — é o combinado, e é por ele que a obra
    anda; o rascunho em montagem ainda pode mudar. Só entra o que falta comprar
    (o coberto por estoque, pedido ou demanda fica de fora), com a primeira data
    de "pedir até" e a obra de onde veio cada pedaço — o comprador agrupa o aço
    das três obras numa cotação só, sabendo para quando cada uma precisa.
    """
    planos = (Cronograma.objects
              .filter(tenant_id=tenant_id, status=Cronograma.Status.VIGENTE, obra__isnull=False)
              .select_related("obra").order_by("obra__nome_obra"))
    obras = []
    por_insumo: dict[str, dict] = {}
    for plano in planos:
        n = necessidade_de_material(plano)
        faltas = [r for r in n["por_insumo"] if Decimal(r["a_comprar"]) > 0]
        obras.append({
            "obra": plano.obra_id, "obra_nome": plano.obra.nome_obra,
            "cronograma": plano.cronograma_id, "versao": plano.versao,
            "insumos_a_comprar": len(faltas),
            "primeira_falta": min((r["primeira_falta"] for r in faltas if r.get("primeira_falta")), default=None),
            "valor_a_comprar": str(sum((Decimal(r["valor_a_comprar"]) for r in faltas), ZERO)),
            "cobertura": n["cobertura"], "antecedencia_padrao": n["antecedencia_padrao"],
        })
        for r in faltas:
            g = por_insumo.setdefault(r["insumo"], {
                "insumo": r["insumo"], "item": r["item"], "descricao": r["descricao"],
                "unidade": r["unidade"], "tipo_demanda": r["tipo_demanda"],
                "a_comprar": ZERO, "valor_a_comprar": ZERO, "primeira_falta": None, "obras": [],
            })
            g["a_comprar"] += Decimal(r["a_comprar"])
            g["valor_a_comprar"] += Decimal(r["valor_a_comprar"])
            if r.get("primeira_falta") and (g["primeira_falta"] is None or r["primeira_falta"] < g["primeira_falta"]):
                g["primeira_falta"] = r["primeira_falta"]
            g["obras"].append({
                "obra": plano.obra_id, "obra_nome": plano.obra.nome_obra,
                "cronograma": plano.cronograma_id, "a_comprar": r["a_comprar"],
                "primeira_falta": r.get("primeira_falta"),
            })
    insumos = sorted(por_insumo.values(), key=lambda g: (g["primeira_falta"] or "9999", g["descricao"]))
    return {"obras": obras, "por_insumo": [_texto(g) for g in insumos]}


# ---------------------------------------------------------------------------
# A semana pede ao almoxarifado — e o apontamento avisa o estoque
# ---------------------------------------------------------------------------


def _etapa_efetiva(atividade: Atividade, por_id: dict[int, Atividade]):
    """A etapa da obra da atividade — a dela ou a do ancestral mais próximo.
    É a chave de apropriação do estoque (obra + etapa, o orçado × aplicado)."""
    a = atividade
    while a is not None:
        if a.etapa_id:
            return a.etapa_id
        a = por_id.get(a.pai_id) if a.pai_id else None
    return None


def local_de_estoque_da_obra(obra_id: int, *, tenant_id):
    """O canteiro da obra no Estoque (o local de onde a requisição sai)."""
    from modulosil.models import LocalEstoque

    locais = LocalEstoque.objects.filter(tenant_id=tenant_id, obra_id=obra_id, ativo=True)
    return (locais.filter(tipo=LocalEstoque.Tipo.CANTEIRO).order_by("local_id").first()
            or locais.order_by("local_id").first())


@transaction.atomic
def pedir_material_da_semana(item_programacao, *, solicitante=None):
    """O compromisso da semana pede o material ao almoxarifado — em **rascunho**.

    *(Decisão do dono: botão por compromisso, nada gerado sozinho.)* A
    quantidade é a da semana: o total do insumo na atividade × o percentual
    previsto para a semana (sem passar do que ainda falta executar); sem
    previsto, o que falta. A requisição sai do canteiro da obra, apropriada à
    obra e à etapa — e o engenheiro ajusta antes de mandar para aprovação.

    Uma por compromisso: pedir de novo devolve a que já existe (a menos que ela
    tenha sido cancelada), e o cartão mostra em que pé ela está.
    """
    from django.core.exceptions import ValidationError

    from modulosil.models import ItemRequisicao, Requisicao

    existente = item_programacao.requisicao_sil
    if existente is not None and existente.status != Requisicao.Status.CANCELADA:
        return existente
    atividade = item_programacao.atividade
    cronograma = atividade.cronograma
    obra_id = cronograma.obra_id
    local = local_de_estoque_da_obra(obra_id, tenant_id=item_programacao.tenant_id) if obra_id else None
    if local is None:
        raise ValidationError(
            "A obra não tem local de estoque (canteiro) no módulo Estoque. Cadastre o "
            "canteiro da obra para a requisição ter de onde sair."
        )
    linhas = [
        l for l in necessidade_de_material(cronograma)["linhas"]
        if l["atividade"] == atividade.atividade_id and l["item"] and l["tipo_demanda"] == "material"
    ]
    if not linhas:
        raise ValidationError(
            "Esta atividade não tem material calculado: ligue-a a um item do orçamento "
            "com composição explodida (Inspetor › Ligar ao orçamento)."
        )
    previsto = item_programacao.percentual_previsto
    por_id = {a.atividade_id: a for a in cronograma.atividades.all()}
    requisicao = Requisicao.objects.create(
        tenant_id=item_programacao.tenant_id, local=local, obra_id=obra_id,
        etapa_id=_etapa_efetiva(por_id.get(atividade.atividade_id, atividade), por_id),
        solicitante=solicitante if getattr(solicitante, "pk", None) else None,
        status=Requisicao.Status.RASCUNHO,
        observacao=(
            f"Semana de {item_programacao.programacao.semana_inicio:%d/%m/%Y} — "
            f"{atividade.codigo} {atividade.nome}"
            + (f" ({previsto}% previsto na semana)" if previsto else "")
        )[:2000],
    )
    for l in linhas:
        quantidade = Decimal(l["restante"])
        if previsto:
            quantidade = min(quantidade, Decimal(l["quantidade"]) * Decimal(previsto) / Decimal(100))
        if quantidade > 0:
            ItemRequisicao.objects.create(
                tenant_id=item_programacao.tenant_id, requisicao=requisicao,
                item_id=l["item"], quantidade=quantidade.quantize(_Q3, rounding=ROUND_HALF_UP),
            )
    item_programacao.requisicao_sil = requisicao
    item_programacao.save(update_fields=["requisicao_sil"])
    from nucleo.models import Notificacao
    from nucleo.notificacoes import avisar_quem_pode

    avisar_quem_pode(
        tenant_id=item_programacao.tenant_id, permissao="sil.requisicao.atender",
        titulo=f"Requisição {requisicao.pk} pedida pela semana da obra — {atividade.codigo} {atividade.nome}"[:200],
        mensagem=(
            f"Material para a semana de {item_programacao.programacao.semana_inicio:%d/%m/%Y}, "
            f"saindo do {local}. Nasceu em rascunho no Estoque."
        ),
        url="/app/sil", nivel=Notificacao.Nivel.DECIDIR,
    )
    return requisicao


def consumo_a_baixar(tenant_id, *, obra_id: int | None = None) -> list[dict]:
    """O que o campo apontou e o estoque ainda não baixou — o **aviso** ao almoxarife.

    *(Decisão do dono: "o apontamento não mexe no estoque, mas avisa ao estoque
    para ser feito depois".)* O consumo teórico de cada atividade é o avanço
    apontado × o material dela (a mesma regra da necessidade); o aplicado é o
    que saiu do estoque para a obra e a etapa, menos o que voltou dela. Onde o
    teórico passa do aplicado, a diferença é a baixa que falta registrar — ou o
    desperdício a explicar.

    Por obra (plano vigente), etapa e insumo do catálogo.
    """
    from obras.models import EtapaObra

    try:
        from modulosil.models import MovimentacaoEstoque
    except ImportError:  # pragma: no cover — instalação sem Estoque
        return []

    planos = Cronograma.objects.filter(
        tenant_id=tenant_id, status=Cronograma.Status.VIGENTE, obra__isnull=False,
    ).select_related("obra")
    if obra_id:
        planos = planos.filter(obra_id=obra_id)
    saida = []
    for plano in planos:
        atividades, avancos = _atividades_e_avanco(plano)
        por_id = {a.atividade_id: a for a in atividades}
        dados = consumo_do_plano(plano, atividades)
        teorico: dict[tuple, dict] = {}
        for a, item_orcado_id, fracao, _origem in dados["consumo"]:
            feito = min(Decimal(100), avancos.get(a.atividade_id, ZERO)) / Decimal(100)
            if feito <= 0:
                continue
            etapa = _etapa_efetiva(a, por_id)
            qtd_linha = dados["quantidade_da_linha"].get(item_orcado_id) or ZERO
            for ins in dados["insumos_por_linha"].get(item_orcado_id, []):
                if not ins["item_id"] or ins["categoria"] != "material":
                    continue
                g = teorico.setdefault((etapa, ins["item_id"]), {
                    "descricao": ins["descricao"], "unidade": ins["unidade"], "teorico": ZERO,
                })
                g["teorico"] += (ins["coeficiente"] or ZERO) * qtd_linha * fracao * feito
        if not teorico:
            continue
        aplicado: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        for etapa, item, tipo, qtd in MovimentacaoEstoque.objects.filter(
            tenant_id=tenant_id, obra_id=plano.obra_id,
            tipo__in=(MovimentacaoEstoque.Tipo.SAIDA, MovimentacaoEstoque.Tipo.DEVOLUCAO),
            item_id__in={k[1] for k in teorico},
        ).values_list("etapa_id", "item_id", "tipo", "quantidade"):
            sinal = Decimal(-1) if tipo == MovimentacaoEstoque.Tipo.DEVOLUCAO else Decimal(1)
            aplicado[(etapa, item)] += sinal * abs(qtd or ZERO)
        etapas = dict(
            EtapaObra.objects.filter(pk__in={k[0] for k in teorico if k[0]}).values_list("etapa_id", "nome_etapa")
        )
        for (etapa, item), g in teorico.items():
            falta = g["teorico"] - aplicado[(etapa, item)]
            if falta > Decimal("0.001"):
                saida.append(_texto({
                    "obra": plano.obra_id, "obra_nome": plano.obra.nome_obra, "cronograma": plano.cronograma_id,
                    "etapa": etapa, "etapa_nome": etapas.get(etapa, "sem etapa"),
                    "item": item, "descricao": g["descricao"], "unidade": g["unidade"],
                    "teorico": g["teorico"], "aplicado": aplicado[(etapa, item)], "a_baixar": falta,
                }))
    return sorted(saida, key=lambda r: (r["obra_nome"], r["etapa_nome"], r["descricao"]))


# ---------------------------------------------------------------------------
# O custo dentro do plano — orçado × comprometido × recebido × aplicado × medido
# ---------------------------------------------------------------------------


def custo_do_plano(cronograma: Cronograma) -> dict:
    """Cada etapa (e cada atividade) com o dinheiro dos quatro módulos ao lado.

    - **orçado** — o custo direto da linha orçada, na fração da atividade (a
      mesma regra de quantidade da necessidade, inclusive a revisão vigente);
    - **comprometido** e **recebido** — os pedidos do centro de custo da obra:
      valor pedido e valor entregue, **rateados** por insumo entre as atividades
      na proporção do que cada uma consome dele no orçamento. O pedido não sabe
      para qual serviço comprou; o rateio é declarado (`rateado: true`) para o
      número não se passar por apropriação exata;
    - **aplicado** — o que saiu do estoque para a obra e a etapa, a custo (só
      por etapa: é a chave do ledger);
    - **medido** — o que as medições **aprovadas** pagaram aos empreiteiros, pela
      atividade do item de contrato (pareada pelo código EAP entre versões) ou,
      sem ela, pelo item orçado.

    O que não acha atividade nem etapa vai para `nao_alocado`, que a tela mostra
    — somar escondido daria um total que não fecha com o Suprimentos.
    """
    from obras.models import EtapaObra

    tenant_id = cronograma.tenant_id
    obra_id = cronograma.obra_id
    atividades, _avancos = _atividades_e_avanco(cronograma)
    por_id = {a.atividade_id: a for a in atividades}
    por_codigo = {a.codigo: a for a in atividades if a.codigo}
    dados = consumo_do_plano(cronograma, atividades)

    from moduloorcamento.models import ItemOrcado

    custo_da_linha = dict(
        ItemOrcado.objects.filter(item_orcado_id__in=dados["quantidade_da_linha"])
        .values_list("item_orcado_id", "total_custo_direto")
    )
    linha_ativ: dict[int, dict] = {}

    def da(a: Atividade) -> dict:
        return linha_ativ.setdefault(a.atividade_id, {
            "atividade": a.atividade_id, "codigo": a.codigo, "nome": a.nome,
            "etapa": _etapa_efetiva(a, por_id),
            "orcado": ZERO, "comprometido": ZERO, "recebido": ZERO, "medido": ZERO,
        })

    # Orçado, e quanto de cada insumo cada atividade consome (base do rateio).
    consumo_do_insumo: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    atividades_da_linha: dict[int, list[tuple[Atividade, Decimal]]] = defaultdict(list)
    for a, item_orcado_id, fracao, _origem in dados["consumo"]:
        da(a)["orcado"] += (custo_da_linha.get(item_orcado_id) or ZERO) * fracao
        atividades_da_linha[item_orcado_id].append((a, fracao))
        qtd_linha = dados["quantidade_da_linha"].get(item_orcado_id) or ZERO
        for ins in dados["insumos_por_linha"].get(item_orcado_id, []):
            if ins["item_id"]:
                consumo_do_insumo[ins["item_id"]][a.atividade_id] += (ins["coeficiente"] or ZERO) * qtd_linha * fracao

    nao_alocado = {"comprometido": ZERO, "recebido": ZERO, "aplicado": ZERO, "medido": ZERO}

    # O pedido de **serviço** ligado a um contrato de empreitada (medição ×
    # compra de serviço) se rateia pelas atividades dos itens do contrato.
    from .models import ContratoObra

    pesos_do_pedido: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for contrato in ContratoObra.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id, pedido_scm__isnull=False,
    ).prefetch_related("itens__atividade"):
        for item in contrato.itens.all():
            alvo = por_codigo.get(getattr(item.atividade, "codigo", None) or "")
            if alvo is not None:
                pesos_do_pedido[contrato.pedido_scm_id][alvo.atividade_id] += (
                    (item.quantidade_contratada or ZERO) * (item.preco_unitario or ZERO))

    # Comprometido e recebido — pedidos do centro de custo da obra, rateados.
    try:
        from moduloscm.models import ItemPedido, PedidoCompra

        for linha in (ItemPedido.objects
                      .filter(tenant_id=tenant_id, pedido__centro_custo__obra_id=obra_id)
                      .exclude(pedido__status__in=(PedidoCompra.Status.CANCELADO, PedidoCompra.Status.RASCUNHO))
                      .annotate(recebido=Sum("recebimentos_item__quantidade_recebida"))
                      .values("pedido_id", "produto_id", "quantidade", "preco_unitario", "recebido")):
            preco = linha["preco_unitario"] or ZERO
            pedido_valor = (linha["quantidade"] or ZERO) * preco
            recebido_valor = (linha["recebido"] or ZERO) * preco
            base = consumo_do_insumo.get(linha["produto_id"]) if linha["produto_id"] else None
            if not base:
                base = pesos_do_pedido.get(linha["pedido_id"])
            total = sum(base.values(), ZERO) if base else ZERO
            if not total:
                nao_alocado["comprometido"] += pedido_valor
                nao_alocado["recebido"] += recebido_valor
                continue
            for aid, qtd in base.items():
                parte = qtd / total
                da(por_id[aid])["comprometido"] += pedido_valor * parte
                da(por_id[aid])["recebido"] += recebido_valor * parte
    except ImportError:  # pragma: no cover
        pass

    # Medido — medições aprovadas dos contratos de empreiteiro (a do contrato
    # de receita é faturamento ao contratante, não custo).
    from .models import ItemMedicao, LadoContrato, Medicao

    for atividade_codigo, item_orcado_id, qtd, preco in ItemMedicao.objects.filter(
        tenant_id=tenant_id, medicao__status=Medicao.Status.APROVADA,
        medicao__contrato__obra_id=obra_id, medicao__contrato__lado=LadoContrato.CUSTO,
    ).values_list("item_contrato__atividade__codigo", "item_contrato__item_orcado_id", "quantidade", "preco_unitario"):
        valor = (qtd or ZERO) * (preco or ZERO)
        if atividade_codigo and atividade_codigo in por_codigo:
            da(por_codigo[atividade_codigo])["medido"] += valor
        elif item_orcado_id and atividades_da_linha.get(item_orcado_id):
            for a, fracao in atividades_da_linha[item_orcado_id]:
                da(a)["medido"] += valor * fracao
        else:
            nao_alocado["medido"] += valor

    # Por etapa: a soma das atividades, mais o aplicado (que só tem etapa).
    etapas: dict = {}

    def da_etapa(etapa_id) -> dict:
        return etapas.setdefault(etapa_id, {
            "etapa": etapa_id, "orcado": ZERO, "comprometido": ZERO, "recebido": ZERO,
            "aplicado": ZERO, "medido": ZERO, "atividades": [],
        })

    for linha in linha_ativ.values():
        e = da_etapa(linha["etapa"])
        for k in ("orcado", "comprometido", "recebido", "medido"):
            e[k] += linha[k]
        e["atividades"].append(linha)
    try:
        from modulosil.models import MovimentacaoEstoque

        for etapa_id, tipo, qtd, custo in MovimentacaoEstoque.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id,
            tipo__in=(MovimentacaoEstoque.Tipo.SAIDA, MovimentacaoEstoque.Tipo.DEVOLUCAO),
        ).values_list("etapa_id", "tipo", "quantidade", "custo_unitario"):
            valor = abs(qtd or ZERO) * (custo or ZERO)
            if tipo == MovimentacaoEstoque.Tipo.DEVOLUCAO:
                valor = -valor
            if etapa_id is None:
                nao_alocado["aplicado"] += valor
            else:
                da_etapa(etapa_id)["aplicado"] += valor
    except ImportError:  # pragma: no cover
        pass

    nomes = dict(EtapaObra.objects.filter(pk__in=[k for k in etapas if k]).values_list("etapa_id", "nome_etapa"))
    ordem = dict(EtapaObra.objects.filter(pk__in=[k for k in etapas if k]).values_list("etapa_id", "ordem"))
    saida = []
    for etapa_id, e in sorted(etapas.items(), key=lambda kv: (ordem.get(kv[0], 10**6), nomes.get(kv[0], ""))):
        e["etapa_nome"] = nomes.get(etapa_id, "Sem etapa da obra")
        e["atividades"] = [_texto(a) for a in sorted(e["atividades"], key=lambda a: a["codigo"])]
        saida.append(_texto(e))
    total = {k: sum((Decimal(e[k]) for e in saida), ZERO) for k in ("orcado", "comprometido", "recebido", "aplicado", "medido")}
    return {
        "cronograma": cronograma.cronograma_id,
        "orcamento": dados["orcamento"].pk if dados["orcamento"] else None,
        "etapas": saida,
        "total": _texto({k: v + nao_alocado.get(k, ZERO) for k, v in total.items()}),
        "nao_alocado": _texto(nao_alocado),
        "rateado": True,
    }



@transaction.atomic
def religar_ao_orcamento_vigente(cronograma: Cronograma) -> int:
    """Revisão do orçamento: as atividades passam ao item de mesmo código EAP
    na versão **vigente**.

    A necessidade e o custo já leem pela revisão (ver `consumo_do_plano`); isto
    grava o vínculo, e é o que faz o **peso** do avanço (que vem do valor do
    item orçado) acompanhar o aditivo. Só no plano em rascunho — o vigente não
    se edita. Devolve quantas atividades mudaram.
    """
    from django.core.exceptions import ValidationError

    from moduloorcamento.models import ItemOrcado
    from moduloorcamento.planilha import orcamento_vigente

    if not cronograma.editavel:
        raise ValidationError("Só o plano em rascunho se religa ao orçamento — replaneje antes.")
    orcamento = orcamento_vigente(cronograma.tenant_id, cronograma.obra_id) if cronograma.obra_id else None
    if orcamento is None:
        raise ValidationError("A obra não tem orçamento aprovado.")
    no_vigente = dict(
        ItemOrcado.objects.filter(orcamento=orcamento).exclude(codigo_eap="")
        .values_list("codigo_eap", "item_orcado_id")
    )
    mudaram = 0
    for a in cronograma.atividades.select_related("item_orcado").filter(item_orcado__isnull=False):
        if a.item_orcado.orcamento_id == orcamento.pk:
            continue
        novo = no_vigente.get(a.item_orcado.codigo_eap)
        if novo:
            a.item_orcado_id = novo
            a.save(update_fields=["item_orcado"])
            mudaram += 1
    return mudaram
