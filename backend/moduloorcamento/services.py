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
from django.db import transaction

from catalogo.models import ComponenteComposicao, Item

from .models import ComposicaoReferenciaItem, InsumoReferencia

# Unidades de mão de obra na SINAPI/ORSE (hora e mês de profissional). Item com
# esta unidade não é material: não se estoca nem se compra em pedido de material,
# então nasce no catálogo como serviço.
UNIDADES_MAO_DE_OBRA = {"H", "HORA", "MES", "MÊS", "H/M", "MÊS/H"}

# Prefixo do código interno gerado na adoção. Mantém o item da base distinguível
# do cadastro próprio da empresa na lista do catálogo, e evita colisão com SKU
# interno (que raramente começa por "SINAPI-").
LIMITE_CODIGO_INTERNO = 40


class AdocaoInvalida(Exception):
    """Referência inconsistente para adoção (sem código, sem unidade)."""


def codigo_interno_para(referencia: InsumoReferencia) -> str:
    """`SINAPI-88489`. Truncado ao limite do campo do catálogo."""
    fonte = referencia.base.fonte.upper()
    return f"{fonte}-{referencia.codigo}"[:LIMITE_CODIGO_INTERNO]


def _tipo_e_flags(referencia: InsumoReferencia) -> tuple[str, dict]:
    """Traduz o item da base para o vocabulário do catálogo-mestre.

    O catálogo distingue o item por `tipo` + flags por domínio; a base
    referencial só sabe "insumo" ou "composição". A tradução é uma heurística
    honesta e conservadora:

    - **composição** → `Tipo.COMPOSICAO`, não comprável nem estocável: quem
      compra e estoca são os insumos dela; a composição é construto de orçamento.
    - **insumo com unidade de hora/mês** → `Tipo.SERVICO` (mão de obra), não
      estocável.
    - **demais insumos** → `Tipo.MATERIAL`, comprável e estocável.

    O usuário pode corrigir o item depois no catálogo — a heurística escolhe o
    default menos arriscado, não a verdade final.
    """
    if referencia.tipo == InsumoReferencia.Tipo.COMPOSICAO:
        return Item.Tipo.COMPOSICAO, {
            "compravel": False, "estocavel": False, "consumivel": False,
        }
    if referencia.unidade.strip().upper() in UNIDADES_MAO_DE_OBRA:
        return Item.Tipo.SERVICO, {
            "compravel": False, "estocavel": False, "consumivel": False,
        }
    return Item.Tipo.MATERIAL, {"compravel": True, "estocavel": True, "consumivel": True}


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
def adotar_no_catalogo(referencia: InsumoReferencia, tenant_id, *, recursivo: bool = True) -> Item:
    """Cria (ou atualiza) o `catalogo.Item` do tenant a partir da referência.

    Devolve o item adotado. Com `recursivo`, adota também os componentes da
    composição e grava os `ComponenteComposicao` correspondentes.
    """
    if not referencia.codigo or not referencia.unidade:
        raise AdocaoInvalida(
            f"Referência {referencia.pk} sem código ou unidade — base importada incompleta."
        )

    tipo, flags = _tipo_e_flags(referencia)
    item = _localizar_item(tenant_id, referencia)
    if item is None:
        item = Item(tenant_id=tenant_id, codigo_interno=codigo_interno_para(referencia))
        # Flags só são definidas na CRIAÇÃO: se a empresa marcou o item como não
        # estocável, uma re-adoção não pode desfazer essa decisão dela.
        for campo, valor in flags.items():
            setattr(item, campo, valor)
        item.tipo = tipo
    item.descricao = referencia.descricao[:255]
    item.unidade = referencia.unidade[:20]
    item.codigo_referencia = referencia.codigo[:30]
    item.fonte_referencia = referencia.base.fonte
    if referencia.grupo and not item.categoria:
        item.categoria = referencia.grupo[:80]
    item.save()

    if recursivo and referencia.tipo == InsumoReferencia.Tipo.COMPOSICAO:
        _adotar_componentes(referencia, item, tenant_id)
    return item


def _adotar_componentes(referencia: InsumoReferencia, item_pai: Item, tenant_id) -> None:
    """Explode a composição no catálogo do tenant, um nível por chamada recursiva."""
    componentes = ComposicaoReferenciaItem.objects.filter(
        composicao=referencia
    ).select_related("filho", "filho__base")
    for componente in componentes:
        item_filho = adotar_no_catalogo(componente.filho, tenant_id, recursivo=True)
        if item_filho.pk == item_pai.pk:
            # Autorreferência na base (dado sujo) — ignorada: um item composto de
            # si mesmo explodiria em laço na precificação.
            continue
        ComponenteComposicao.objects.update_or_create(
            tenant_id=tenant_id, item_pai=item_pai, item_filho=item_filho,
            defaults={"coeficiente": componente.coeficiente},
        )


def adotar_muitos(referencias, tenant_id, *, recursivo: bool = True) -> list[Item]:
    """Adoção em lote (a tela adota a seleção da busca de uma vez)."""
    return [adotar_no_catalogo(r, tenant_id, recursivo=recursivo) for r in referencias]
