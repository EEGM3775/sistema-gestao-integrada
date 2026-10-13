# backend/moduloscm/recebimento.py
"""Receber o pedido linha por linha — e o que isso faz no Estoque e no ERP (D284).

O defeito que originou isto: a tela gravava só o cabeçalho do `Recebimento`, sem
as linhas, e a entrada no estoque (SIL) escuta justamente a **linha**
(`ItemRecebimento`, `modulosil.signals`). Nenhum recebimento feito pela tela
entrava no estoque.

Regras decididas com o dono em 11/10/2026:

- **Chegou a menos e o pedido continua aberto**: fica parcial, esperando o resto.
  Nada vai ao ERP — ainda não é divergência, é entrega em andamento.
- **Chegou a menos e se finaliza o recebimento** (`encerrar`): o que faltava é
  *saldo encerrado* (`ItemPedido.quantidade_encerrada`) e vai ao ERP como
  divergência, com o valor, para o título ser ajustado.
- **Chegou a mais**: aceita — o estoque recebe o que chegou de fato — e vai ao
  ERP como divergência na hora.

Nota fiscal não é condição: o pedido recebido sem nota fica "aguardando NF-e",
no SCM e na linha do título do ERP.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import financeiro
from .models import EventoPedido, ItemPedido, ItemRecebimento, PedidoCompra, Recebimento

ZERO = Decimal("0")


class RecebimentoInvalido(ValueError):
    pass


def recebido_por_item(pedido) -> dict[int, Decimal]:
    return {
        r["item_pedido_id"]: r["q"] or ZERO
        for r in ItemRecebimento.objects.filter(tenant_id=pedido.tenant_id, item_pedido__pedido=pedido)
        .values("item_pedido_id").annotate(q=Sum("quantidade_recebida"))
    }


def saldos(pedido) -> list[dict]:
    """Por linha: pedido, recebido, encerrado e o que ainda falta."""
    recebido = recebido_por_item(pedido)
    saida = []
    for it in pedido.itens.select_related("produto").order_by("item_pedido_id"):
        rec = recebido.get(it.item_pedido_id, ZERO)
        saida.append({
            "item_pedido": it.item_pedido_id,
            "produto": it.produto_id,
            "descricao": it.produto.descricao if it.produto_id else it.descricao,
            "codigo": it.produto.codigo_interno if it.produto_id else "",
            "unidade": (it.produto.unidade if it.produto_id else it.unidade) or "",
            "estocavel": bool(it.produto_id and it.produto.estocavel),
            "quantidade": it.quantidade, "recebido": rec, "encerrado": it.quantidade_encerrada,
            "pendente": max(it.quantidade - rec - it.quantidade_encerrada, ZERO),
            "excedente": max(rec - it.quantidade, ZERO),
            "preco_unitario": it.preco_unitario,
        })
    return saida


def recalcular_status(pedido) -> str:
    """Recebido total quando nada mais falta (recebido ou encerrado); parcial
    quando algo chegou; senão, o status de antes (aprovado/enviado)."""
    if pedido.status == PedidoCompra.Status.CANCELADO:
        return pedido.status
    linhas = saldos(pedido)
    chegou = any(l["recebido"] > 0 or l["encerrado"] > 0 for l in linhas)
    if not chegou:
        return pedido.status
    novo = (PedidoCompra.Status.RECEBIDO_TOTAL if all(l["pendente"] <= 0 for l in linhas)
            else PedidoCompra.Status.RECEBIDO_PARCIAL)
    if novo != pedido.status:
        pedido.status = novo
        pedido.save(update_fields=["status"])
    return novo


def _qtd(v) -> Decimal:
    try:
        q = Decimal(str(v if v not in (None, "") else "0").replace(",", "."))
    except (InvalidOperation, TypeError) as exc:
        raise RecebimentoInvalido("Quantidade inválida.") from exc
    if q < 0:
        raise RecebimentoInvalido("Quantidade não pode ser negativa.")
    return q.quantize(Decimal("0.001"))


def _rotulo(linha: dict) -> str:
    return f"{linha['descricao']} ({linha['unidade'] or 'un'})"


@transaction.atomic
def receber(pedido, *, itens, data=None, local_entrega="", observacao="", encerrar=False, autor=None,
            nota: dict | None = None) -> dict:
    """`nota` (opcional): `{numero, serie, chave, xml_arquivo, pdf_arquivo}` da NF-e
    que veio com a entrega — lançada junto, ligada a este recebimento."""
    if pedido.status == PedidoCompra.Status.CANCELADO:
        raise RecebimentoInvalido("Pedido cancelado não recebe.")
    if not isinstance(itens, list):
        raise RecebimentoInvalido("Envie as linhas recebidas.")
    data = data if hasattr(data, "isoformat") else (parse_date(str(data or "")) or timezone.localdate())

    linhas = {l["item_pedido"]: l for l in saldos(pedido)}
    quantidades: dict[int, Decimal] = {}
    for bruto in itens:
        ip = int((bruto or {}).get("item_pedido") or 0)
        if ip not in linhas:
            raise RecebimentoInvalido("Há uma linha que não é deste pedido.")
        q = _qtd(bruto.get("quantidade"))
        if q > 0:
            quantidades[ip] = quantidades.get(ip, ZERO) + q
    if not quantidades and not encerrar:
        raise RecebimentoInvalido("Informe ao menos uma quantidade recebida.")

    recebimento = Recebimento.objects.create(
        tenant_id=pedido.tenant_id, pedido=pedido, data=data, local_entrega=(local_entrega or "")[:100],
        observacao=(observacao or "")[:2000], encerrou_saldo=bool(encerrar),
        recebido_por=autor if getattr(autor, "pk", None) else None,
    )
    # Uma a uma (não bulk_create): o `post_save` de cada linha é o que dá a
    # entrada no estoque.
    for ip, q in quantidades.items():
        ItemRecebimento.objects.create(
            tenant_id=pedido.tenant_id, recebimento=recebimento, item_pedido_id=ip, quantidade_recebida=q,
        )

    a_mais, valor_a_mais = [], ZERO
    for ip, q in quantidades.items():
        linha = linhas[ip]
        sobra = q - max(linha["pendente"], ZERO)
        if sobra > 0:
            a_mais.append(f"{_rotulo(linha)} +{sobra.normalize():f}")
            valor_a_mais += sobra * linha["preco_unitario"]

    encerrados, valor_encerrado = [], ZERO
    if encerrar:
        for ip, linha in linhas.items():
            falta = linha["pendente"] - quantidades.get(ip, ZERO)
            if falta > 0:
                ItemPedido.objects.filter(pk=ip).update(quantidade_encerrada=linha["encerrado"] + falta)
                encerrados.append(f"{_rotulo(linha)} −{falta.normalize():f}")
                valor_encerrado += falta * linha["preco_unitario"]

    status = recalcular_status(pedido)
    recebimento.tipo = Recebimento.Tipo.TOTAL if status == PedidoCompra.Status.RECEBIDO_TOTAL else Recebimento.Tipo.PARCIAL
    recebimento.save(update_fields=["tipo"])

    nota_lancada = None
    if nota and (nota.get("numero") or nota.get("chave") or nota.get("xml_arquivo")):
        from .notas import lancar_nota

        nota_lancada = lancar_nota(pedido, recebimento=recebimento, autor=autor, **nota)

    resumo = ", ".join(f"{linhas[ip]['descricao']} {q.normalize():f}" for ip, q in quantidades.items())
    financeiro.registrar_evento(
        pedido, EventoPedido.Tipo.RECEBIMENTO,
        (f"Recebido em {data.strftime('%d/%m/%Y')}: {resumo}." if resumo else "Recebimento finalizado sem nova entrega.")
        + (" Pedido sem NF-e: fica aguardando a nota." if not pedido.notas_fiscais.exists() else ""),
        autor=autor,
    )
    if a_mais:
        texto = (f"Chegou a mais do que o pedido: {'; '.join(a_mais)} — R$ {valor_a_mais.quantize(Decimal('0.01'))} "
                 "acima do pedido. O estoque recebeu o que chegou; ajuste o título se o fornecedor cobrar.")
        financeiro.registrar_evento(pedido, EventoPedido.Tipo.DIVERGENCIA, texto,
                                    valor=valor_a_mais.quantize(Decimal("0.01")), autor=autor, vai_ao_erp=True)
        financeiro.avisar_divergencia(pedido, texto)
    if encerrados:
        texto = (f"Recebimento finalizado com saldo a menos: {'; '.join(encerrados)} — R$ "
                 f"{valor_encerrado.quantize(Decimal('0.01'))} que não vai chegar. Ajuste o título.")
        financeiro.registrar_evento(pedido, EventoPedido.Tipo.DIVERGENCIA, texto,
                                    valor=valor_encerrado.quantize(Decimal("0.01")), autor=autor, vai_ao_erp=True)
        financeiro.avisar_divergencia(pedido, texto)

    return {
        "recebimento_id": recebimento.recebimento_id, "tipo": recebimento.tipo, "status_pedido": status,
        "a_mais": a_mais, "valor_a_mais": str(valor_a_mais.quantize(Decimal("0.01"))),
        "encerrados": encerrados, "valor_encerrado": str(valor_encerrado.quantize(Decimal("0.01"))),
        "aguardando_nfe": not pedido.notas_fiscais.exists(),
        "nota": nota_lancada.nota_id if nota_lancada else None,
    }
