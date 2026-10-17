# backend/moduloscm/propostas.py
"""A proposta que o comprador registra, e o mapa comparativo que sai dela.

*Dono, 16/10/2026:* "cotação também pode ser alimentada pelo usuário, tanto com
importação quanto digitando, não só recebendo do fornecedor — a rede ainda não
está no ar e a cotação fica inútil." O preço chega por telefone, e-mail ou
WhatsApp; quem compra o digita aqui, ou sobe a planilha que o fornecedor
devolveu ([impexp.py](impexp.py)). As duas portas gravam por `registrar`, então
as regras são uma só.

E o mapa sai para a reunião: `mapa_da_cotacao` é o mesmo comparativo da tela,
em dado, para o PDF e o XLSX de [documento_cotacao.py](documento_cotacao.py).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import Cotacao, ItemDemanda, ItemProposta, Proposta


class PropostaInvalida(ValueError):
    pass


def _decimal(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        texto = str(valor).strip().replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        raise PropostaInvalida(f"Preço inválido: {valor!r}.")


def _exigir_aberta(cotacao: Cotacao) -> None:
    if cotacao.status != Cotacao.Status.ABERTA:
        raise PropostaInvalida("A cotação não está aberta: proposta só entra ou muda enquanto ela está em aberto.")


def registrar(
    cotacao: Cotacao, *, fornecedor, itens: list[dict], recebida_em: date | None = None,
    prazo_entrega_dias: int | None = None, observacao: str = "", proposta: Proposta | None = None,
) -> Proposta:
    """Cria (ou, com `proposta`, substitui) a proposta de um fornecedor.

    `itens`: `[{item_demanda, preco_unitario}]` — o item que o fornecedor não
    cotou fica de fora (ou com preço vazio). A quantidade é a da demanda: o
    fornecedor responde ao que se pediu. Um fornecedor tem uma proposta por
    cotação; outra vez é editar a que existe.
    """
    _exigir_aberta(cotacao)
    if fornecedor is None or fornecedor.tenant_id != cotacao.tenant_id:
        raise PropostaInvalida("Escolha um fornecedor da sua empresa.")
    if proposta is not None and proposta.status == Proposta.Status.VENCEDORA:
        raise PropostaInvalida("A proposta vencedora não muda.")
    outra = cotacao.propostas.filter(fornecedor=fornecedor)
    if proposta is not None:
        outra = outra.exclude(pk=proposta.pk)
    if outra.exists():
        raise PropostaInvalida("Este fornecedor já tem proposta nesta cotação — edite a que existe.")

    linhas = {i.pk: i for i in ItemDemanda.objects.filter(demanda_id=cotacao.demanda_id)}
    precos: dict[int, Decimal] = {}
    for item in itens or []:
        try:
            chave = int(item.get("item_demanda"))
        except (TypeError, ValueError):
            raise PropostaInvalida("Item sem identificação.")
        if chave not in linhas:
            raise PropostaInvalida("Item que não é desta cotação.")
        preco = _decimal(item.get("preco_unitario"))
        if preco is None:
            continue
        if preco < 0:
            raise PropostaInvalida("Preço negativo.")
        precos[chave] = preco
    if not precos:
        raise PropostaInvalida("Informe o preço de pelo menos um item.")
    if prazo_entrega_dias is not None and int(prazo_entrega_dias) < 0:
        raise PropostaInvalida("Prazo negativo.")

    with transaction.atomic():
        if proposta is None:
            proposta = Proposta(tenant_id=cotacao.tenant_id, cotacao=cotacao)
        proposta.fornecedor = fornecedor
        proposta.fornecedor_nome = fornecedor.razao_social
        proposta.recebida_em = recebida_em or timezone.localdate()
        proposta.prazo_entrega_dias = prazo_entrega_dias
        proposta.observacao = (observacao or "").strip()
        proposta.valor_total = sum(
            (preco * linhas[chave].quantidade for chave, preco in precos.items()), Decimal("0"),
        ).quantize(Decimal("0.01"))
        proposta.save()
        proposta.itens.all().delete()
        ItemProposta.objects.bulk_create([
            ItemProposta(
                tenant_id=cotacao.tenant_id, proposta=proposta, item_demanda=linhas[chave],
                preco_unitario=preco, quantidade=linhas[chave].quantidade,
            ) for chave, preco in precos.items()
        ])
    return proposta


def apagar(proposta: Proposta) -> None:
    _exigir_aberta(proposta.cotacao)
    proposta.delete()


def recalcular_total(proposta: Proposta) -> None:
    """Total = Σ preço × quantidade das linhas cotadas (a importação grava linha a linha)."""
    total = sum((i.preco_unitario * i.quantidade for i in proposta.itens.all()), Decimal("0"))
    proposta.valor_total = total.quantize(Decimal("0.01"))
    proposta.save(update_fields=["valor_total"])


# --- o mapa comparativo -----------------------------------------------------------

def _descricao(item: ItemDemanda) -> str:
    if item.produto_id:
        return item.produto.descricao
    return item.descricao_servico or f"Item #{item.pk}"


def mapa_da_cotacao(cotacao: Cotacao) -> dict:
    """Itens × propostas, com o menor de cada linha e a recomendação.

    A recomendação é o menor total **entre as propostas que cotaram tudo** —
    proposta que deixou item de fora parece mais barata só porque cobra menos
    coisa. Sem nenhuma completa, vale o menor total entre as que há, e o mapa
    diz que nenhuma cotou tudo.
    """
    demanda = cotacao.demanda
    itens = list(demanda.itens.select_related("produto").order_by("item_demanda_id"))
    propostas = list(
        cotacao.propostas.select_related("fornecedor").prefetch_related("itens")
        .order_by("valor_total", "proposta_id")
    )
    precos = {(ip.proposta_id, ip.item_demanda_id): ip.preco_unitario for p in propostas for ip in p.itens.all()}

    colunas = []
    for p in propostas:
        cotados = sum(1 for i in itens if (p.pk, i.pk) in precos)
        colunas.append({
            "proposta": p.pk,
            "fornecedor": p.fornecedor.razao_social if p.fornecedor_id else (p.fornecedor_nome or "Fornecedor da rede"),
            "total": p.valor_total,
            "prazo_entrega_dias": p.prazo_entrega_dias,
            "recebida_em": p.recebida_em,
            "status": p.status,
            "status_rotulo": p.get_status_display(),
            "cotados": cotados,
            "completa": cotados == len(itens),
            "observacao": p.observacao,
        })

    validas = [c for c in colunas if c["status"] != Proposta.Status.RECUSADA and c["total"] is not None]
    candidatas = [c for c in validas if c["completa"]] or validas
    recomendada = min(candidatas, key=lambda c: c["total"]) if candidatas else None
    vencedora = next((c for c in colunas if c["status"] == Proposta.Status.VENCEDORA), None)

    linhas = []
    for item in itens:
        valores = [precos.get((c["proposta"], item.pk)) for c in colunas]
        presentes = [v for v in valores if v is not None]
        menor = min(presentes) if presentes else None
        linhas.append({
            "item_demanda": item.pk,
            "codigo": item.produto.codigo_interno if item.produto_id else "",
            "descricao": _descricao(item),
            "unidade": item.unidade or (item.produto.unidade if item.produto_id else ""),
            "quantidade": item.quantidade,
            "precos": [{"valor": v, "menor": v is not None and v == menor and len(presentes) > 1} for v in valores],
        })

    centro = getattr(demanda, "centro_custo", None)
    obra = getattr(centro, "obra", None) if centro else None
    return {
        "cotacao": cotacao.pk,
        "demanda": demanda.pk,
        "status": cotacao.get_status_display(),
        "criada_em": cotacao.criado_em,
        "data_limite": cotacao.data_limite,
        "centro_custo": centro.nome if centro else "",
        "obra": obra.nome_obra if obra else "",
        "itens": linhas,
        "propostas": colunas,
        "recomendada": recomendada["proposta"] if recomendada else None,
        "nenhuma_completa": bool(validas) and not any(c["completa"] for c in validas),
        "vencedora": vencedora["proposta"] if vencedora else None,
    }
