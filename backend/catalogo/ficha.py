# backend/catalogo/ficha.py
"""A ficha do item — tudo o que o sistema sabe dele, numa resposta.

*Dono, 11/10/2026:* "o catálogo precisa dizer todos os detalhes sobre os itens,
de onde veio, onde está registrado, loja e preço."

O catálogo é fundação e não conhece os módulos que o usam; cada bloco abaixo
importa o módulo **tarde e tolerante**, como o SCM faz com o Orçamento: quem não
tem o SIL instalado recebe a ficha sem a seção de estoque, não um 500. E nada
aqui é estimado — loja sem compra mostra o preço da oferta e "sem compra".
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Sum

from payment.planos import (
    CATALOGO_FICHA_GRAFICO_PONTOS as GRAFICO_PONTOS,
    CATALOGO_FICHA_HISTORICO_LINHAS as HISTORICO_LINHAS,
)


def _dec(v) -> str | None:
    return None if v is None else str(v)


def _ofertas_e_precos(item) -> tuple[list, list]:
    try:
        from moduloscm.models import ItemPedido, OfertaFornecedor, PedidoCompra
    except ImportError:  # pragma: no cover - instalação sem Suprimentos
        return [], []

    compras = list(
        ItemPedido.objects.filter(tenant_id=item.tenant_id, produto=item)
        .exclude(pedido__status=PedidoCompra.Status.CANCELADO)
        .select_related("pedido__fornecedor")
        .order_by("-pedido__data_pedido", "-item_pedido_id")[:HISTORICO_LINHAS]
    )
    historico = [{
        "pedido": c.pedido_id,
        "data": c.pedido.data_pedido.isoformat(),
        "fornecedor": c.pedido.fornecedor_id,
        "fornecedor_nome": c.pedido.fornecedor.razao_social,
        "quantidade": _dec(c.quantidade),
        "unidade": c.unidade or item.unidade,
        "preco_unitario": _dec(c.preco_unitario),
    } for c in compras]

    ultima_por_fornecedor: dict[int, dict] = {}
    for h in historico:
        ultima_por_fornecedor.setdefault(h["fornecedor"], h)

    lojas = []
    vistos = set()
    for o in (OfertaFornecedor.objects.filter(tenant_id=item.tenant_id, produto=item)
              .select_related("fornecedor").order_by("preco_direto")):
        ultima = ultima_por_fornecedor.get(o.fornecedor_id)
        vistos.add(o.fornecedor_id)
        lojas.append({
            "fornecedor": o.fornecedor_id, "fornecedor_nome": o.fornecedor.razao_social,
            "oferta": o.oferta_id, "codigo_no_fornecedor": o.codigo_no_fornecedor,
            "preco_oferta": _dec(o.preco_direto), "compra_direta": o.compra_direta,
            "prazo_entrega_dias": o.prazo_entrega_dias, "ativo": o.ativo,
            "ultimo_preco_pago": ultima["preco_unitario"] if ultima else None,
            "ultima_compra": ultima["data"] if ultima else None,
        })
    # Quem vendeu sem ter oferta cadastrada também é loja do item.
    for forn, ultima in ultima_por_fornecedor.items():
        if forn in vistos:
            continue
        lojas.append({
            "fornecedor": forn, "fornecedor_nome": ultima["fornecedor_nome"],
            "oferta": None, "codigo_no_fornecedor": "", "preco_oferta": None,
            "compra_direta": False, "prazo_entrega_dias": None, "ativo": True,
            "ultimo_preco_pago": ultima["preco_unitario"], "ultima_compra": ultima["data"],
        })
    return lojas, historico


def _grafico_precos(item) -> dict:
    """Preço do item por fornecedor ao longo do tempo: cada compra paga e cada
    preço cotado é um ponto (sem média — o ponto diz de qual pedido/cotação veio).
    Últimos `GRAFICO_PONTOS` de cada série, devolvidos em ordem cronológica."""
    try:
        from moduloscm.models import ItemPedido, ItemProposta, PedidoCompra
    except ImportError:  # pragma: no cover - instalação sem Suprimentos
        return {"pagos": [], "cotados": []}

    pagos = list(
        ItemPedido.objects.filter(tenant_id=item.tenant_id, produto=item)
        .exclude(pedido__status=PedidoCompra.Status.CANCELADO)
        .select_related("pedido__fornecedor")
        .order_by("-pedido__data_pedido", "-item_pedido_id")[:GRAFICO_PONTOS]
    )
    # A cotação que virou compra é substituída pelo preço pago (dono, 16/10/2026):
    # sai a proposta que gerou um pedido vivo deste item. Pedido cancelado não
    # comprou nada — a cotação volta a aparecer.
    virou_compra = ItemPedido.objects.filter(
        tenant_id=item.tenant_id, produto=item,
        pedido__proposta_vencedora=OuterRef("proposta"),
    ).exclude(pedido__status=PedidoCompra.Status.CANCELADO)
    cotados = list(
        ItemProposta.objects.filter(tenant_id=item.tenant_id, item_demanda__produto=item)
        .exclude(Exists(virou_compra))
        .select_related("proposta__fornecedor")
        .order_by("-proposta__recebida_em", "-item_proposta_id")[:GRAFICO_PONTOS]
    )
    return {
        "pagos": [{
            "data": c.pedido.data_pedido.isoformat(),
            "fornecedor": c.pedido.fornecedor_id,
            "fornecedor_nome": c.pedido.fornecedor.razao_social,
            "pedido": c.pedido_id,
            "quantidade": _dec(c.quantidade),
            "preco_unitario": _dec(c.preco_unitario),
        } for c in reversed(pagos)],
        "cotados": [{
            "data": p.proposta.recebida_em.isoformat(),
            # Proposta da rede não tem FK: o rótulo durável é o que identifica.
            "fornecedor": p.proposta.fornecedor_id,
            "fornecedor_nome": (p.proposta.fornecedor.razao_social if p.proposta.fornecedor
                                else p.proposta.fornecedor_nome or "Fornecedor da rede"),
            "cotacao": p.proposta.cotacao_id,
            "status": p.proposta.status,
            "quantidade": _dec(p.quantidade),
            "preco_unitario": _dec(p.preco_unitario),
        } for p in reversed(cotados)],
    }


def _orcamentos(item) -> list:
    try:
        from moduloorcamento.models import ItemOrcado
    except ImportError:  # pragma: no cover
        return []
    linhas = (
        ItemOrcado.objects.filter(tenant_id=item.tenant_id, item=item)
        .values("orcamento_id", "orcamento__descricao", "orcamento__versao", "orcamento__obra__nome_obra")
        .annotate(linhas=Count("item_orcado_id"), quantidade=Sum("quantidade"))
        .order_by("-orcamento_id")[:20]
    )
    return [{
        "orcamento": r["orcamento_id"], "descricao": r["orcamento__descricao"],
        "versao": r["orcamento__versao"], "obra": r["orcamento__obra__nome_obra"] or "",
        "linhas": r["linhas"], "quantidade": _dec(r["quantidade"]),
    } for r in linhas]


def _estoque(item) -> list:
    try:
        from modulosil.models import SaldoEstoque
    except ImportError:  # pragma: no cover
        return []
    return [{
        "local": s.local_id, "local_nome": s.local.nome,
        "quantidade": _dec(s.quantidade), "reservado": _dec(s.reservado),
        "custo_medio": _dec(s.custo_medio),
    } for s in SaldoEstoque.objects.filter(tenant_id=item.tenant_id, item=item).select_related("local")]


def _contagens(item) -> dict:
    saida = {"demandas": 0, "pedidos": 0}
    try:
        from moduloscm.models import ItemDemanda, ItemPedido
    except ImportError:  # pragma: no cover
        return saida
    saida["demandas"] = ItemDemanda.objects.filter(tenant_id=item.tenant_id, produto=item).values("demanda_id").distinct().count()
    saida["pedidos"] = ItemPedido.objects.filter(tenant_id=item.tenant_id, produto=item).values("pedido_id").distinct().count()
    return saida


def ficha_do_item(item) -> dict:
    lojas, historico = _ofertas_e_precos(item)
    estoque = _estoque(item)
    precos = [Decimal(h["preco_unitario"]) for h in historico]
    return {
        "item": item.item_id,
        "codigo_interno": item.codigo_interno,
        "descricao": item.descricao,
        "unidade": item.unidade,
        "tipo": item.tipo,
        "tipo_nome": item.get_tipo_display(),
        "categoria": item.categoria,
        "ncm": item.ncm,
        "gtin": item.gtin,
        "estocavel": item.estocavel,
        "ativo": item.ativo,
        "origem": {
            "tipo": item.origem,
            "rotulo": item.get_origem_display(),
            "detalhe": item.origem_detalhe,
            "criado_em": item.criado_em.isoformat() if item.criado_em else None,
            "fonte_referencia": item.fonte_referencia,
            "fonte_nome": item.get_fonte_referencia_display() if item.fonte_referencia else "",
            "codigo_referencia": item.codigo_referencia,
            "publicacao_referencia": item.publicacao_referencia,
        },
        "lojas": lojas,
        "historico_precos": historico,
        "grafico_precos": _grafico_precos(item),
        "preco_resumo": {
            "ultimo": historico[0]["preco_unitario"] if historico else None,
            "menor": _dec(min(precos)) if precos else None,
            "maior": _dec(max(precos)) if precos else None,
            "compras": len(historico),
        },
        "orcamentos": _orcamentos(item),
        "estoque": estoque,
        "estoque_total": _dec(sum((Decimal(s["quantidade"]) for s in estoque), Decimal("0"))),
        "uso": _contagens(item),
    }
