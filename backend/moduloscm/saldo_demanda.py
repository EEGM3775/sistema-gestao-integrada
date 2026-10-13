# backend/moduloscm/saldo_demanda.py
"""O que de uma demanda ainda falta comprar.

Uma demanda pode ser comprada em mais de um pedido (fornecedores diferentes,
itens diferentes). Ela só está **atendida** quando os pedidos cobrem todas as
linhas; até lá continua na fila de decisão com o saldo que falta. O pedido
cancelado não conta.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .models import Cotacao, Demanda, ItemPedido, PedidoCompra


def _chave(produto_id, descricao: str):
    return ("p", produto_id) if produto_id else ("d", (descricao or "").strip().lower())


def saldos(demanda: Demanda) -> dict[int, Decimal]:
    """`{item_demanda_id: quantidade que falta}`; nunca negativo."""
    comprado: dict = defaultdict(lambda: Decimal("0"))
    pedidos = (ItemPedido.objects.filter(pedido__demanda=demanda, tenant_id=demanda.tenant_id)
               .exclude(pedido__status=PedidoCompra.Status.CANCELADO))
    for ip in pedidos:
        comprado[_chave(ip.produto_id, ip.descricao)] += ip.quantidade
    resultado = {}
    for item in demanda.itens.order_by("item_demanda_id"):
        chave = _chave(item.produto_id, item.descricao_servico)
        coberto = min(comprado[chave], item.quantidade)
        comprado[chave] -= coberto  # linhas repetidas consomem o comprado em ordem
        resultado[item.item_demanda_id] = item.quantidade - coberto
    return resultado


def atualizar_status(demanda: Demanda) -> bool:
    """Fecha a demanda (e as cotações abertas dela) se nada mais falta. Devolve se fechou."""
    falta = saldos(demanda)
    if not falta or any(q > 0 for q in falta.values()):
        return False
    Demanda.objects.filter(pk=demanda.pk).update(status=Demanda.Status.ATENDIDA)
    Cotacao.objects.filter(demanda=demanda, status=Cotacao.Status.ABERTA).update(status=Cotacao.Status.ENCERRADA)
    return True
