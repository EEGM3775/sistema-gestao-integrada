# backend/moduloorcamento/duplicacao.py
"""ORC.5b — duplicar orçamento e copiar linhas entre orçamentos.

**Duplicar ≠ revisar.** `planilha.revisar_orcamento` cria a versão seguinte *da
mesma obra*, rebaixa a anterior a `SUPERADO` e exige motivo — é aditivo
contratual. Duplicar é outra coisa: reaproveitar uma planilha pronta como ponto
de partida para **outra obra**, que é como construtora orça obra parecida sem
redigitar. A duplicata nasce v1, em rascunho, sem `orcamento_origem` e sem
registro de revisão — ela não revisa nada, é planilha nova.

Duas travas que vêm do domínio:

- **A etapa não atravessa a obra.** `ItemOrcado.etapa` aponta para
  `obras.EtapaObra`, que é de uma obra específica. Copiar para outra obra
  carregando a etapa antiga faria o orçado casar com o aplicado da obra errada
  no `aplicado/` do SIL. Então, ao mudar de obra, a etapa é **descartada** (e a
  resposta diz quantas linhas perderam a etapa, em vez de fazer isso calado).
- **O snapshot é preservado.** Descrição, unidade, custo unitário, fonte, código
  e data-base do preço são copiados como estão. Duplicar não é reprecificar: se
  a intenção for atualizar preço, o caminho é a reprecificação, que registra o
  antes e o depois.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from .models import ItemOrcado, Orcamento
from .planilha import exigir_editavel, proxima_versao, recalcular_orcamento

CAMPOS_SNAPSHOT = (
    "codigo_eap", "ordem", "tipo_linha", "item", "descricao", "unidade",
    "quantidade", "custo_unitario", "fonte_referencia", "codigo_referencia",
    "data_base_preco", "observacao",
)


class CopiaInvalida(Exception):
    """Cópia pedida entre orçamentos que não podem ser ligados assim."""


@transaction.atomic
def duplicar_orcamento(
    origem: Orcamento,
    *,
    obra_destino=None,
    descricao: str = "",
    usuario_nome: str = "",
) -> tuple[Orcamento, int]:
    """Clona a planilha inteira numa nova, em rascunho.

    Devolve `(novo, linhas_sem_etapa)` — a contagem existe para a tela avisar
    que a apropriação por etapa se perdeu na travessia de obra, em vez de o
    orçamentista descobrir isso quando o confronto orçado × aplicado vier vazio.
    """
    obra_id = obra_destino.pk if obra_destino is not None else origem.obra_id
    mudou_de_obra = obra_id != origem.obra_id

    novo = Orcamento.objects.create(
        tenant_id=origem.tenant_id,
        obra_id=obra_id,
        descricao=(descricao or f"{origem.descricao} (cópia)")[:200],
        versao=proxima_versao(obra_id),
        orcamento_origem=None,
        base_referencial=origem.base_referencial,
        data_base=origem.data_base,
        regime_encargos=origem.regime_encargos,
        encargos_sociais_percentual=origem.encargos_sociais_percentual,
        bdi_percentual=origem.bdi_percentual,
        status=Orcamento.Status.RASCUNHO,
        observacao=(
            f"Duplicado de \"{origem.descricao}\" (v{origem.versao})"
            + (f" por {usuario_nome}" if usuario_nome else "")
        ),
    )

    sem_etapa = _clonar_arvore(origem, novo, manter_etapa=not mudou_de_obra)
    recalcular_orcamento(novo)
    return novo, sem_etapa


@transaction.atomic
def copiar_itens(
    *,
    destino: Orcamento,
    itens: list[ItemOrcado],
    pai=None,
) -> tuple[int, int]:
    """Copia um bloco de linhas de outro orçamento para dentro de `destino`.

    Só as linhas passadas e a subárvore de cada uma — copiar um sintético sem os
    filhos produziria um agrupador que soma zero, que é pior que não copiar.
    Devolve `(linhas_copiadas, linhas_sem_etapa)`.
    """
    exigir_editavel(destino)
    if pai is not None and pai.orcamento_id != destino.orcamento_id:
        raise CopiaInvalida("A linha-pai precisa ser do orçamento de destino.")

    origens = {i.orcamento_id for i in itens}
    if len(origens) > 1:
        raise CopiaInvalida("Copie de um orçamento por vez.")
    if not itens:
        return 0, 0

    orcamento_origem_id = itens[0].orcamento_id
    todos = list(ItemOrcado.objects.filter(orcamento_id=orcamento_origem_id))
    por_pai: dict[int | None, list[ItemOrcado]] = {}
    for item in todos:
        por_pai.setdefault(item.pai_id, []).append(item)

    obra_igual = (
        Orcamento.objects.filter(pk=orcamento_origem_id)
        .values_list("obra_id", flat=True).first() == destino.obra_id
    )

    base_ordem = (
        ItemOrcado.objects.filter(
            orcamento=destino, pai=pai
        ).count()
    )
    copiadas = 0
    sem_etapa = 0

    def copiar(item: ItemOrcado, novo_pai, ordem: int):
        nonlocal copiadas, sem_etapa
        dados = {campo: getattr(item, campo) for campo in CAMPOS_SNAPSHOT}
        dados["ordem"] = ordem
        etapa_id = item.etapa_id if obra_igual else None
        if item.etapa_id and not obra_igual:
            sem_etapa += 1
        clone = ItemOrcado.objects.create(
            tenant_id=destino.tenant_id,
            orcamento=destino,
            pai=novo_pai,
            etapa_id=etapa_id,
            **dados,
        )
        copiadas += 1
        for n, filho in enumerate(sorted(por_pai.get(item.item_orcado_id, []), key=lambda i: (i.ordem, i.item_orcado_id)), start=1):
            copiar(filho, clone, n)

    for n, item in enumerate(itens, start=base_ordem + 1):
        copiar(item, pai, n)

    recalcular_orcamento(destino)
    return copiadas, sem_etapa


def _clonar_arvore(origem: Orcamento, destino: Orcamento, *, manter_etapa: bool) -> int:
    """Duas passadas: cria tudo com `pai` nulo e depois religa, pelo mesmo motivo
    de `planilha._clonar_itens` — `pai` aponta para linhas do próprio lote."""
    originais = list(ItemOrcado.objects.filter(orcamento=origem).order_by("item_orcado_id"))
    de_para: dict[int, int] = {}
    sem_etapa = 0

    for original in originais:
        dados = {campo: getattr(original, campo) for campo in CAMPOS_SNAPSHOT}
        if original.etapa_id and not manter_etapa:
            sem_etapa += 1
        clone = ItemOrcado.objects.create(
            tenant_id=destino.tenant_id,
            orcamento=destino,
            pai=None,
            etapa_id=original.etapa_id if manter_etapa else None,
            **dados,
        )
        de_para[original.item_orcado_id] = clone.item_orcado_id

    religar = []
    for original in originais:
        if original.pai_id:
            clone = ItemOrcado(item_orcado_id=de_para[original.item_orcado_id])
            clone.pai_id = de_para[original.pai_id]
            religar.append(clone)
    if religar:
        ItemOrcado.objects.bulk_update(religar, ["pai"], batch_size=500)

    return sem_etapa


def resumo_da_duplicata(novo: Orcamento, sem_etapa: int) -> dict:
    """O que a tela precisa dizer depois de duplicar."""
    return {
        "orcamento": novo.pk,
        "obra": novo.obra_id,
        "versao": novo.versao,
        "descricao": novo.descricao,
        "total_itens": ItemOrcado.objects.filter(orcamento=novo).count(),
        "valor_total": str(novo.valor_total or Decimal("0")),
        "linhas_sem_etapa": sem_etapa,
        "aviso_etapa": (
            "As linhas foram copiadas para outra obra, então a apropriação por etapa "
            "não veio junto — reatribua as etapas para o confronto orçado × aplicado "
            "voltar a fechar."
        ) if sem_etapa else "",
    }
