# backend/moduloscm/edicao.py
"""Editar e cancelar o pedido de compra (D284).

*Dono, 11/10/2026:* "pode ser editado a qualquer momento até o recebimento.
Quando tem o recebimento só pode ser editado os saldos. Essas edições também
têm que ir como anotações ao ERP."

Dois regimes, decididos pelo que já chegou:

- **Nada recebido** → edição livre: fornecedor, centro de custo, entrega,
  observação e as linhas (tirar, pôr, mudar quantidade e preço).
- **Algo recebido** → só o **saldo**: a quantidade de cada linha, nunca abaixo
  do que já entrou (o estoque já recebeu). Preço, fornecedor e linhas novas
  ficam travados — mudar o preço do que já foi conferido e estocado reescreveria
  o custo do estoque por baixo.

Toda edição sobe a revisão do pedido (o PDF reenviado diz "revisão 2"), vai ao
histórico e vira anotação nos títulos do ERP. Se o valor mudou e a cobrança já
existia, a cobrança deixa de fechar e a tela pede para redefini-la; o título não
é reescrito sozinho, porque é de quem paga.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.dateparse import parse_date

from catalogo.models import Item

from . import financeiro
from .models import CentroCusto, EventoPedido, ItemPedido, PedidoCompra
from .recebimento import recalcular_status, recebido_por_item

ZERO = Decimal("0")


class EdicaoInvalida(ValueError):
    pass


def _dec(v, casas: str) -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")).quantize(Decimal(casas))
    except (InvalidOperation, TypeError) as exc:
        raise EdicaoInvalida("Quantidade ou preço inválido.") from exc


def _fmt(q: Decimal) -> str:
    return f"{q.normalize():f}"


def _nome(it: ItemPedido) -> str:
    return it.produto.descricao if it.produto_id else (it.descricao or f"Item #{it.pk}")


def regime(pedido) -> str:
    """'livre' até o primeiro recebimento; 'saldo' depois; 'travado' se cancelado."""
    if pedido.status == PedidoCompra.Status.CANCELADO:
        return "travado"
    return "saldo" if any(v > 0 for v in recebido_por_item(pedido).values()) else "livre"


def _recalcular_total(pedido) -> Decimal:
    total = sum((it.quantidade * it.preco_unitario for it in pedido.itens.all()), ZERO).quantize(Decimal("0.01"))
    pedido.valor_total = total
    return total


@transaction.atomic
def editar(pedido: PedidoCompra, dados: dict, *, autor=None) -> list[str]:
    """Aplica a edição; devolve as mudanças em frases (vazio = nada mudou)."""
    modo = regime(pedido)
    if modo == "travado":
        raise EdicaoInvalida("Pedido cancelado não se edita.")
    mudancas: list[str] = []
    valor_antes = pedido.valor_total or ZERO
    itens_atuais = {it.pk: it for it in pedido.itens.select_related("produto")}
    linhas = dados.get("itens")

    # --- cabeçalho ---
    if "data_entrega_prevista" in dados:
        nova = parse_date(str(dados.get("data_entrega_prevista") or "")) if dados.get("data_entrega_prevista") else None
        if nova != pedido.data_entrega_prevista:
            mudancas.append(f"entrega prevista: {pedido.data_entrega_prevista or '—'} → {nova or '—'}")
            pedido.data_entrega_prevista = nova
    if "observacao" in dados and (dados.get("observacao") or "") != pedido.observacao:
        pedido.observacao = (dados.get("observacao") or "")[:2000]
        mudancas.append("observação alterada")

    if modo == "saldo":
        for campo in ("fornecedor", "centro_custo"):
            if campo in dados and dados[campo] not in (None, "") and int(dados[campo]) != getattr(pedido, f"{campo}_id"):
                raise EdicaoInvalida("O pedido já teve recebimento: só os saldos (quantidades) podem mudar.")
    else:
        if dados.get("fornecedor") not in (None, "") and int(dados["fornecedor"]) != pedido.fornecedor_id:
            from fornecedores.models import Fornecedor

            novo = Fornecedor.objects.filter(tenant_id=pedido.tenant_id, pk=dados["fornecedor"]).first()
            if novo is None:
                raise EdicaoInvalida("Fornecedor não encontrado.")
            vivos = financeiro.titulos(pedido)
            if any(c.valor_pago and c.valor_pago > 0 for c in vivos):
                raise EdicaoInvalida("Um título deste pedido já foi pago: o fornecedor não pode mudar.")
            mudancas.append(f"fornecedor: {pedido.fornecedor.razao_social} → {novo.razao_social}")
            pedido.fornecedor = novo
            for conta in vivos:
                conta.fornecedor_id = novo.pk
                conta.save(update_fields=["fornecedor"])
        if "centro_custo" in dados:
            cc_id = dados.get("centro_custo") or None
            if (int(cc_id) if cc_id else None) != pedido.centro_custo_id:
                novo_cc = CentroCusto.objects.filter(tenant_id=pedido.tenant_id, pk=cc_id).first() if cc_id else None
                mudancas.append(f"centro de custo: {getattr(pedido.centro_custo, 'nome', '—')} → {getattr(novo_cc, 'nome', '—')}")
                pedido.centro_custo = novo_cc

    # --- linhas ---
    if linhas is not None:
        if not isinstance(linhas, list):
            raise EdicaoInvalida("Envie as linhas do pedido.")
        recebido = recebido_por_item(pedido)
        vistos = set()
        for n, bruto in enumerate(linhas, start=1):
            ip = int(bruto.get("item_pedido") or 0)
            quantidade = _dec(bruto.get("quantidade"), "0.001")
            if ip:
                it = itens_atuais.get(ip)
                if it is None:
                    raise EdicaoInvalida(f"Linha {n}: não é deste pedido.")
                vistos.add(ip)
                ja = recebido.get(ip, ZERO)
                if quantidade < ja:
                    raise EdicaoInvalida(
                        f"{_nome(it)}: já chegaram {_fmt(ja)}; a quantidade não pode ficar abaixo disso."
                    )
                if quantidade != it.quantidade:
                    mudancas.append(f"{_nome(it)}: quantidade {_fmt(it.quantidade)} → {_fmt(quantidade)}")
                    it.quantidade = quantidade
                    # Saldo encerrado nunca passa do que ainda faltaria.
                    it.quantidade_encerrada = min(it.quantidade_encerrada, max(quantidade - ja, ZERO))
                if "preco_unitario" in bruto:
                    preco = _dec(bruto["preco_unitario"], "0.01")
                    if preco != it.preco_unitario:
                        if modo == "saldo":
                            raise EdicaoInvalida("O pedido já teve recebimento: o preço não muda mais.")
                        if preco < 0:
                            raise EdicaoInvalida(f"{_nome(it)}: preço negativo.")
                        mudancas.append(f"{_nome(it)}: preço R$ {it.preco_unitario} → R$ {preco}")
                        it.preco_unitario = preco
                it.save()
                continue
            # linha nova
            if modo == "saldo":
                raise EdicaoInvalida("O pedido já teve recebimento: não se acrescentam linhas — faça outro pedido.")
            produto = None
            if bruto.get("produto"):
                produto = Item.objects.filter(tenant_id=pedido.tenant_id, pk=bruto["produto"]).first()
                if produto is None:
                    raise EdicaoInvalida(f"Linha {n}: item do catálogo não encontrado.")
            descricao = (bruto.get("descricao") or "").strip()[:255]
            if produto is None and not descricao:
                raise EdicaoInvalida(f"Linha {n}: diga o que está sendo comprado.")
            preco = _dec(bruto.get("preco_unitario") or "0", "0.01")
            if quantidade <= 0 or preco < 0:
                raise EdicaoInvalida(f"Linha {n}: quantidade positiva e preço não negativo.")
            novo = ItemPedido.objects.create(
                tenant_id=pedido.tenant_id, pedido=pedido, produto=produto,
                descricao="" if produto else descricao,
                unidade=(produto.unidade if produto else (bruto.get("unidade") or "").strip())[:20],
                quantidade=quantidade, preco_unitario=preco,
            )
            mudancas.append(f"incluído: {_nome(novo)} {_fmt(quantidade)} × R$ {preco}")
        for ip, it in itens_atuais.items():
            if ip in vistos:
                continue
            if modo == "saldo":
                raise EdicaoInvalida("O pedido já teve recebimento: as linhas não saem — zere o saldo dela.")
            mudancas.append(f"retirado: {_nome(it)}")
            it.delete()
        if not pedido.itens.exists():
            raise EdicaoInvalida("O pedido precisa de ao menos uma linha.")

    if not mudancas:
        return []

    total = _recalcular_total(pedido)
    pedido.revisao += 1
    pedido.save()
    recalcular_status(pedido)

    texto = f"Revisão {pedido.revisao}: " + "; ".join(mudancas) + "."
    if total != valor_antes:
        texto += f" Valor do pedido: R$ {valor_antes} → R$ {total}."
        if pedido.meios_pagamento.exists():
            texto += " A cobrança não fecha mais com o pedido — redefina-a."
    motivo = (dados.get("motivo") or "").strip()
    if motivo:
        texto += f" Motivo: {motivo[:300]}"
    financeiro.registrar_evento(pedido, EventoPedido.Tipo.EDICAO, texto,
                                valor=total if total != valor_antes else None, autor=autor, vai_ao_erp=True)
    if total != valor_antes:
        financeiro.avisar_divergencia(pedido, f"pedido editado, valor R$ {valor_antes} → R$ {total}.")
    return mudancas


@transaction.atomic
def cancelar(pedido: PedidoCompra, *, motivo: str = "", autor=None) -> dict:
    """Cancela o pedido que nada recebeu, e os títulos sem pagamento dele."""
    if pedido.status == PedidoCompra.Status.CANCELADO:
        raise EdicaoInvalida("O pedido já está cancelado.")
    if regime(pedido) == "saldo":
        raise EdicaoInvalida(
            "O pedido já teve recebimento: em vez de cancelar, finalize o recebimento com o saldo a menos."
        )
    pedido.status = PedidoCompra.Status.CANCELADO
    pedido.save(update_fields=["status"])
    texto = "Pedido cancelado." + (f" Motivo: {motivo.strip()[:300]}" if motivo.strip() else "")
    cancelados, pagos = financeiro.cancelar_titulos(pedido, motivo=texto, autor=autor)
    financeiro.registrar_evento(pedido, EventoPedido.Tipo.CANCELAMENTO, texto, autor=autor)
    return {"titulos_cancelados": cancelados, "titulos_com_pagamento": pagos}
