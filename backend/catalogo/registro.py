# backend/catalogo/registro.py
"""Cadastrar um item próprio a partir de um texto — a porta única.

*Dono, 11/10/2026:* "quando o item é só texto aparece um botão ao lado esquerdo
para cadastrar […] cuidado com o código para não bater com o código de outros
itens" e "itens registrados no orçamento já deveriam ir para o catálogo".

Três gestos chegam aqui com a mesma pergunta — "este texto já é um item?": a
linha de compra digitada no Suprimentos, a linha de preço digitado no
Orçamento e quem mais vier. Uma função só responde, para que o mesmo "Luva
32mm" não vire dois cadastros conforme a tela de onde veio.

- **Código**: `ITM-000123`, o próximo da sequência do tenant. A unicidade é do
  banco (`catalogo_item_codigo_por_tenant`); a função só escolhe o candidato e,
  se outra gravação levou o número no meio do caminho, tenta o seguinte.
- **Duplicado**: mesma descrição (sem acento, caixa ou espaço) e mesma unidade
  devolve o item que já existe em vez de criar outro.
- **Teto do plano**: só itens novos contam (`catalogo_itens`, `payment/planos.py`).
"""
from __future__ import annotations

import re
import unicodedata

from django.db import IntegrityError, transaction
from django.db.models import IntegerField, Max
from django.db.models.functions import Cast, Substr

from .models import Item

PREFIXO = "ITM-"
_SEQ = re.compile(r"^ITM-\d+$")


class TextoInvalido(ValueError):
    """Não há o que cadastrar (descrição vazia)."""


def chave_de_descricao(texto: str) -> str:
    """"Luva 32 mm", "LUVA 32MM" e "luva  32mm" são o mesmo item."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _chave_unidade(unidade: str) -> str:
    return chave_de_descricao(unidade)


def proximo_codigo(tenant_id) -> str:
    """O próximo `ITM-NNNNNN` livre do tenant."""
    maior = (
        Item.objects.filter(tenant_id=tenant_id, codigo_interno__regex=_SEQ.pattern)
        .annotate(n=Cast(Substr("codigo_interno", len(PREFIXO) + 1), IntegerField()))
        .aggregate(m=Max("n"))["m"]
    ) or 0
    return f"{PREFIXO}{maior + 1:06d}"


def item_equivalente(tenant_id, descricao: str, unidade: str) -> Item | None:
    """O item do tenant que já é este texto, ou `None`."""
    chave = chave_de_descricao(descricao)
    if not chave:
        return None
    palavra = next((p for p in re.findall(r"\w{2,}", descricao) if p), "")
    candidatos = Item.objects.filter(tenant_id=tenant_id)
    if palavra:
        candidatos = candidatos.filter(descricao__icontains=palavra)
    alvo_un = _chave_unidade(unidade)
    for item in candidatos.only("item_id", "descricao", "unidade", "codigo_interno")[:500]:
        if chave_de_descricao(item.descricao) == chave and (
            not alvo_un or _chave_unidade(item.unidade) == alvo_un
        ):
            return item
    return None


def registrar_item_proprio(
    *, tenant_id, descricao: str, unidade: str = "", tipo: str = Item.Tipo.MATERIAL,
    origem: str = Item.Origem.MANUAL, origem_detalhe: str = "", categoria: str = "",
    usuario=None,
) -> tuple[Item, bool]:
    """Devolve `(item, criado)`. Levanta `TextoInvalido` sem descrição e
    `nucleo.quotas.QuotaExcedida` (402) quando o plano não comporta mais um item
    — **só** se `usuario` vier; sem ele (rotina de sistema) o teto não se aplica.
    """
    descricao = re.sub(r"\s+", " ", (descricao or "").strip())[:255]
    if not descricao:
        raise TextoInvalido("Diga o que é o item.")
    unidade = (unidade or "").strip()[:20] or "un"

    existente = item_equivalente(tenant_id, descricao, unidade)
    if existente is not None:
        return existente, False

    if usuario is not None:
        from nucleo.quotas import checar_quota

        checar_quota(usuario, "catalogo_itens")

    for _tentativa in range(5):
        try:
            with transaction.atomic():
                item = Item.objects.create(
                    tenant_id=tenant_id, codigo_interno=proximo_codigo(tenant_id),
                    descricao=descricao, unidade=unidade, tipo=tipo,
                    categoria=(categoria or "")[:80], origem=origem,
                    origem_detalhe=(origem_detalhe or "")[:120],
                    # Mão de obra e serviço não entram no almoxarifado.
                    estocavel=tipo in (Item.Tipo.MATERIAL, Item.Tipo.EPI, Item.Tipo.EQUIPAMENTO),
                )
            return item, True
        except IntegrityError:
            # Outra gravação levou o número entre a leitura e o insert: o
            # próximo `proximo_codigo` já o enxerga e devolve o seguinte.
            continue
    raise IntegrityError("Não foi possível reservar um código livre para o item.")
