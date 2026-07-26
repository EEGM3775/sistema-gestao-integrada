# backend/moduloorcamento/bancos.py
"""ORC.5b — bancos de preço da empresa: adoção, trava e contagem.

O espelho tenant-scoped de `services.py`. A adoção faz a mesma travessia — item
de uma publicação vira `catalogo.Item` da empresa — mas partindo do banco
próprio em vez da base pública, e por isso repete a heurística de tipo em vez de
importá-la: o `InsumoReferencia` e o `ItemBancoPreco` são modelos diferentes com
o mesmo contrato, e um `getattr` genérico atravessando os dois esconderia qual
lado está sendo lido no dia em que um deles mudar.

A **trava** (`BancoPreco.travado`) é o pedido explícito do dono do produto:
banco conferido não pode ser editado por engano. Ela vale para item, componente
e pasta — não só para o cabeçalho —, porque proteger o nome do banco e deixar o
coeficiente editável não protege nada.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from catalogo.models import ComponenteComposicao, Item

from .models import BancoPreco, ComponenteBancoPreco, InsumoReferencia, ItemBancoPreco
from .services import UNIDADES_MAO_DE_OBRA, LIMITE_CODIGO_INTERNO


class BancoTravado(Exception):
    """Escrita tentada em banco travado."""


class AdocaoInvalida(Exception):
    """Item do banco sem código ou unidade."""


def exigir_editavel(banco: BancoPreco) -> None:
    if banco.travado:
        raise BancoTravado(
            f'O banco "{banco.nome}" está travado. Destrave para editar — a trava '
            "existe justamente para o preço conferido não mudar sem alguém decidir."
        )


def codigo_interno_para(item: ItemBancoPreco) -> str:
    """`PREFEITURA-01.02.003`, a partir do nome do banco."""
    prefixo = "".join(c for c in item.banco.nome.upper() if c.isalnum())[:12] or "BANCO"
    return f"{prefixo}-{item.codigo}"[:LIMITE_CODIGO_INTERNO]


def _tipo_e_flags(item: ItemBancoPreco) -> tuple[str, dict]:
    """Mesma heurística conservadora da adoção da base pública."""
    if item.tipo == InsumoReferencia.Tipo.COMPOSICAO:
        return Item.Tipo.COMPOSICAO, {"compravel": False, "estocavel": False, "consumivel": False}
    if item.unidade.strip().upper() in UNIDADES_MAO_DE_OBRA:
        return Item.Tipo.SERVICO, {"compravel": False, "estocavel": False, "consumivel": False}
    return Item.Tipo.MATERIAL, {"compravel": True, "estocavel": True, "consumivel": True}


def _localizar_item(tenant_id, item: ItemBancoPreco) -> Item | None:
    por_referencia = Item.objects.filter(
        tenant_id=tenant_id,
        fonte_referencia=item.banco.fonte,
        codigo_referencia=item.codigo,
    ).first()
    if por_referencia is not None:
        return por_referencia
    return Item.objects.filter(
        tenant_id=tenant_id, codigo_interno=codigo_interno_para(item)
    ).first()


@transaction.atomic
def adotar_no_catalogo(item: ItemBancoPreco, tenant_id, *, recursivo: bool = True) -> Item:
    """Traz o item do banco da empresa para o catálogo da empresa.

    Idempotente pelo mesmo par (fonte, código) da adoção pública, então adotar
    duas vezes atualiza em vez de duplicar.
    """
    if not item.codigo or not item.unidade:
        raise AdocaoInvalida(
            f"Item {item.pk} sem código ou unidade — corrija no banco antes de adotar."
        )

    tipo, flags = _tipo_e_flags(item)
    alvo = _localizar_item(tenant_id, item)
    if alvo is None:
        alvo = Item(tenant_id=tenant_id, codigo_interno=codigo_interno_para(item))
        for campo, valor in flags.items():
            setattr(alvo, campo, valor)
        alvo.tipo = tipo
    alvo.descricao = item.descricao[:255]
    alvo.unidade = item.unidade[:20]
    alvo.codigo_referencia = item.codigo[:30]
    alvo.fonte_referencia = item.banco.fonte
    if item.grupo and not alvo.categoria:
        alvo.categoria = item.grupo[:80]
    alvo.save()

    if recursivo and item.tipo == InsumoReferencia.Tipo.COMPOSICAO:
        _adotar_componentes(item, alvo, tenant_id)
    return alvo


def _adotar_componentes(item: ItemBancoPreco, item_pai: Item, tenant_id) -> None:
    componentes = ComponenteBancoPreco.objects.filter(
        composicao=item
    ).select_related("filho", "filho__banco")
    for componente in componentes:
        filho = adotar_no_catalogo(componente.filho, tenant_id, recursivo=True)
        if filho.pk == item_pai.pk:
            continue
        ComponenteComposicao.objects.update_or_create(
            tenant_id=tenant_id, item_pai=item_pai, item_filho=filho,
            defaults={"coeficiente": componente.coeficiente},
        )


def adotar_muitos(itens, tenant_id, *, recursivo: bool = True) -> list[Item]:
    return [adotar_no_catalogo(i, tenant_id, recursivo=recursivo) for i in itens]


@transaction.atomic
def travar(banco: BancoPreco, *, usuario_nome: str = "") -> BancoPreco:
    banco.travado = True
    banco.travado_em = timezone.now()
    banco.travado_por_nome = (usuario_nome or "")[:150]
    banco.save(update_fields=["travado", "travado_em", "travado_por_nome", "atualizado_em"])
    return banco


@transaction.atomic
def destravar(banco: BancoPreco, *, usuario_nome: str = "") -> BancoPreco:
    """Destravar é registrado — quem destravou fica no campo, e a data zera.

    Sem rastro, "o preço mudou e ninguém sabe quando" volta a ser possível, que
    é exatamente o que a trava evita.
    """
    banco.travado = False
    banco.travado_em = None
    banco.travado_por_nome = (usuario_nome or "")[:150]
    banco.save(update_fields=["travado", "travado_em", "travado_por_nome", "atualizado_em"])
    return banco


def recontar(banco: BancoPreco) -> BancoPreco:
    """Atualiza `total_itens` — desnormalizado porque a listagem de bancos
    precisa do número sem contar linha a linha em cada carga de tela."""
    banco.total_itens = ItemBancoPreco.objects.filter(banco=banco).count()
    banco.save(update_fields=["total_itens", "atualizado_em"])
    return banco


def total_de_linhas(tenant_id) -> int:
    """Linhas de banco próprio que o tenant mantém — o que a quota conta."""
    return ItemBancoPreco.objects.filter(tenant_id=tenant_id).count()


def resumo(tenant_id) -> list[dict]:
    """Bancos do tenant com o que a tela mostra, numa consulta agregada."""
    bancos = (
        BancoPreco.objects.filter(tenant_id=tenant_id, ativo=True)
        .select_related("obra")
        .annotate(itens_contados=Count("itens", distinct=True))
        .order_by("-mes_referencia", "nome")
    )
    return [
        {
            "banco_id": b.banco_id,
            "nome": b.nome,
            "rotulo": b.rotulo_automatico(),
            "fonte": b.fonte,
            "uf": b.uf,
            "mes_referencia": b.mes_referencia,
            "regime_encargos": b.regime_encargos,
            "obra": b.obra_id,
            "obra_nome": b.obra.nome_obra if b.obra_id else None,
            "origem": b.origem,
            "travado": b.travado,
            "travado_em": b.travado_em,
            "travado_por_nome": b.travado_por_nome,
            "total_itens": b.itens_contados,
            "pastas": b.pastas.count(),
        }
        for b in bancos
    ]


@transaction.atomic
def duplicar_item(item: ItemBancoPreco, *, banco_destino: BancoPreco, novo_codigo: str = "") -> ItemBancoPreco:
    """Copia um item (e a composição dele) para outro banco, editável.

    É como se tira uma composição da SINAPI e se ajusta o coeficiente sem tocar
    na oficial: o pedido explícito do dono do produto. O destino não pode estar
    travado — copiar para dentro de um banco conferido o descaracterizaria.
    """
    exigir_editavel(banco_destino)
    codigo = (novo_codigo or item.codigo)[:30]
    if ItemBancoPreco.objects.filter(
        banco=banco_destino, tipo=item.tipo, codigo=codigo
    ).exists():
        codigo = f"{codigo[:26]}-COP"

    clone = ItemBancoPreco.objects.create(
        tenant_id=banco_destino.tenant_id,
        banco=banco_destino,
        pasta=None,
        codigo=codigo,
        descricao=item.descricao,
        unidade=item.unidade,
        tipo=item.tipo,
        custo_unitario=item.custo_unitario,
        grupo=item.grupo,
        observacao=f"Cópia de {item.banco.nome} · {item.codigo}",
    )

    for componente in ComponenteBancoPreco.objects.filter(composicao=item).select_related("filho"):
        filho = _garantir_filho(componente.filho, banco_destino)
        ComponenteBancoPreco.objects.get_or_create(
            tenant_id=banco_destino.tenant_id, composicao=clone, filho=filho,
            defaults={"coeficiente": componente.coeficiente},
        )

    recontar(banco_destino)
    return clone


def _garantir_filho(filho: ItemBancoPreco, banco_destino: BancoPreco) -> ItemBancoPreco:
    """Insumo da composição copiada precisa existir no banco de destino."""
    existente = ItemBancoPreco.objects.filter(
        banco=banco_destino, tipo=filho.tipo, codigo=filho.codigo
    ).first()
    if existente is not None:
        return existente
    return ItemBancoPreco.objects.create(
        tenant_id=banco_destino.tenant_id,
        banco=banco_destino,
        codigo=filho.codigo,
        descricao=filho.descricao,
        unidade=filho.unidade,
        tipo=filho.tipo,
        custo_unitario=filho.custo_unitario,
        grupo=filho.grupo,
    )


@transaction.atomic
def copiar_da_base_publica(
    referencias, *, banco_destino: BancoPreco, com_composicao: bool = True,
) -> int:
    """Traz itens da SINAPI/ORSE para um banco da empresa, **editáveis**.

    O caminho que o dono do produto pediu: "duplicar e copiar itens para serem
    editados em banco próprio sem alterar dados de SINAPI/ORSE". A base pública
    continua read-only; o que nasce aqui é cópia da empresa.
    """
    exigir_editavel(banco_destino)
    criados = 0
    for referencia in referencias:
        item, novo = ItemBancoPreco.objects.get_or_create(
            tenant_id=banco_destino.tenant_id,
            banco=banco_destino,
            tipo=referencia.tipo,
            codigo=referencia.codigo[:30],
            defaults={
                "descricao": referencia.descricao[:500],
                "unidade": referencia.unidade[:20],
                "custo_unitario": referencia.custo_unitario or Decimal("0"),
                "grupo": referencia.grupo[:150],
                "observacao": f"Copiado de {referencia.base.fonte.upper()} {referencia.codigo}",
            },
        )
        criados += 1 if novo else 0
        if com_composicao and referencia.tipo == InsumoReferencia.Tipo.COMPOSICAO:
            criados += _copiar_componentes_publicos(referencia, item, banco_destino)

    recontar(banco_destino)
    return criados


def _copiar_componentes_publicos(referencia, composicao: ItemBancoPreco, banco: BancoPreco) -> int:
    from .models import ComposicaoReferenciaItem

    criados = 0
    for componente in ComposicaoReferenciaItem.objects.filter(
        composicao=referencia
    ).select_related("filho"):
        filho, novo = ItemBancoPreco.objects.get_or_create(
            tenant_id=banco.tenant_id, banco=banco,
            tipo=componente.filho.tipo, codigo=componente.filho.codigo[:30],
            defaults={
                "descricao": componente.filho.descricao[:500],
                "unidade": componente.filho.unidade[:20],
                "custo_unitario": componente.filho.custo_unitario or Decimal("0"),
                "grupo": componente.filho.grupo[:150],
            },
        )
        criados += 1 if novo else 0
        if filho.pk == composicao.pk:
            continue
        ComponenteBancoPreco.objects.get_or_create(
            tenant_id=banco.tenant_id, composicao=composicao, filho=filho,
            defaults={"coeficiente": componente.coeficiente},
        )
    return criados
