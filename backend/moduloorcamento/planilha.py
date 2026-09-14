# backend/moduloorcamento/planilha.py
"""ORC.1 — a mecânica da planilha: recálculo, EAP, aprovação e revisão.

Separado de `services.py` (que é a adoção da base referencial) por concern, não
por tamanho: adoção fala com a base pública, isto aqui fala com o orçamento do
tenant. As duas metades do módulo se encontram só no `catalogo.Item`.

Três operações que o resto do módulo assume corretas:

- **`recalcular_orcamento`** — a única fonte de verdade dos totais. Ninguém
  soma planilha na mão em serializer ou view.
- **`aprovar_orcamento`** — congela a régua.
- **`revisar_orcamento`** — clona a régua congelada numa versão nova editável,
  deixando rastro do porquê.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models import ItemOrcado, Orcamento, RevisaoOrcamento

CEM = Decimal("100")
CENTAVO = Decimal("0.01")


class OrcamentoNaoEditavel(Exception):
    """Escrita tentada em orçamento aprovado/superado/cancelado."""


class RevisaoInvalida(Exception):
    """Revisão pedida sobre um orçamento que não está aprovado."""


def dinheiro(valor: Decimal) -> Decimal:
    """Arredondamento monetário explícito (2 casas, meio-para-cima).

    Explícito porque o default do `Decimal` é `ROUND_HALF_EVEN` (bankers'
    rounding), que numa planilha de milhares de linhas produz um total alguns
    centavos diferente do que o orçamentista confere na calculadora — e essa
    diferença vira dúvida sobre o sistema inteiro.
    """
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def exigir_editavel(orcamento: Orcamento) -> None:
    if not orcamento.editavel:
        raise OrcamentoNaoEditavel(
            f"Orçamento v{orcamento.versao} está {orcamento.get_status_display().lower()} — "
            "crie uma revisão para alterá-lo."
        )


def _arvore(itens: list[ItemOrcado]) -> dict[int | None, list[ItemOrcado]]:
    """Índice pai → filhos, ordenado como a planilha se lê."""
    filhos: dict[int | None, list[ItemOrcado]] = {}
    for item in itens:
        filhos.setdefault(item.pai_id, []).append(item)
    for irmaos in filhos.values():
        irmaos.sort(key=lambda i: (i.ordem, i.item_orcado_id))
    return filhos


@transaction.atomic
def recalcular_orcamento(orcamento: Orcamento) -> Orcamento:
    """Renumera a EAP e recalcula todos os totais, de baixo para cima.

    Percorre a árvore uma vez só, em pós-ordem: os analíticos calculam
    `quantidade × custo_unitario`, os sintéticos somam os filhos já calculados.
    O total do orçamento é a soma das **raízes** — não a soma de todas as
    linhas, que contaria cada custo duas vezes (uma no analítico, outra no
    sintético que o agrupa).

    O BDI multiplica no fim de cada linha analítica, não no total: é assim que a
    planilha de licitação é conferida, item a item.
    """
    itens = list(ItemOrcado.objects.filter(orcamento=orcamento))
    filhos = _arvore(itens)
    fator_padrao = Decimal("1") + (orcamento.bdi_percentual / CEM)
    # BDI diferenciado por linha (ORC.2): o TCU admite BDI próprio para
    # fornecimento de equipamentos. Carregado de uma vez — a alternativa seria
    # um SELECT por linha da planilha.
    fatores = {
        bdi_id: Decimal("1") + (percentual / CEM)
        for bdi_id, percentual in orcamento.composicoes_bdi.values_list(
            "bdi_id", "percentual_calculado"
        )
    }

    visitados: set[int] = set()
    alterados: list[ItemOrcado] = []

    def visitar(item: ItemOrcado, prefixo: str, posicao: int) -> tuple[Decimal, Decimal]:
        # Guarda contra ciclo (`pai` é auto-FK; dado corrompido ou importação
        # malfeita poderia fechar um laço e estourar a pilha).
        if item.item_orcado_id in visitados:
            return Decimal("0"), Decimal("0")
        visitados.add(item.item_orcado_id)

        codigo = f"{prefixo}{posicao}" if not prefixo else f"{prefixo}.{posicao}"
        meus_filhos = filhos.get(item.item_orcado_id, [])

        if item.custa and not meus_filhos:
            direto = dinheiro(item.quantidade * item.custo_unitario)
            com_bdi = dinheiro(direto * fatores.get(item.bdi_id, fator_padrao))
        else:
            # Sintético — ou analítico que ganhou filhos, e aí passa a valer
            # como agrupador (o custo está nas folhas).
            direto = Decimal("0")
            com_bdi = Decimal("0")
            for i, filho in enumerate(meus_filhos, start=1):
                d, b = visitar(filho, codigo, i)
                direto += d
                com_bdi += b
            direto = dinheiro(direto)
            com_bdi = dinheiro(com_bdi)

        if (item.codigo_eap, item.total_custo_direto, item.total_com_bdi) != (codigo, direto, com_bdi):
            item.codigo_eap = codigo
            item.total_custo_direto = direto
            item.total_com_bdi = com_bdi
            alterados.append(item)
        return direto, com_bdi

    total_direto = Decimal("0")
    total_com_bdi = Decimal("0")
    for posicao, raiz in enumerate(filhos.get(None, []), start=1):
        d, b = visitar(raiz, "", posicao)
        total_direto += d
        total_com_bdi += b

    if alterados:
        ItemOrcado.objects.bulk_update(
            alterados, ["codigo_eap", "total_custo_direto", "total_com_bdi"], batch_size=500
        )

    orcamento.custo_direto_total = dinheiro(total_direto)
    orcamento.valor_total = dinheiro(total_com_bdi)
    orcamento.save(update_fields=["custo_direto_total", "valor_total", "atualizado_em"])
    return orcamento


@transaction.atomic
def aprovar_orcamento(orcamento: Orcamento, *, usuario_nome: str = "") -> Orcamento:
    """Congela a régua de custo.

    Recalcula antes de congelar — aprovar um total defasado por uma edição que
    não passou pelo recálculo seria congelar o número errado, e é justamente o
    número congelado que todo o controle de custo vai usar depois.
    """
    exigir_editavel(orcamento)
    if not ItemOrcado.objects.filter(orcamento=orcamento).exists():
        raise OrcamentoNaoEditavel("Orçamento sem itens não pode ser aprovado.")

    recalcular_orcamento(orcamento)
    orcamento.status = Orcamento.Status.APROVADO
    orcamento.aprovado_em = timezone.now()
    orcamento.aprovado_por_nome = (usuario_nome or "")[:150]
    orcamento.save(update_fields=["status", "aprovado_em", "aprovado_por_nome", "atualizado_em"])
    return orcamento


def proxima_versao(obra_id) -> int:
    """Próximo número de versão livre da obra.

    Quem numera é o servidor, nunca o cliente: a unicidade `(obra, versao)` é
    constraint de banco, então deixar o número vir do payload transformaria uma
    regra de domínio em erro de formulário. Os três caminhos que criam orçamento
    (POST, `revisar_orcamento`, `duplicar_orcamento`) passam por aqui — antes,
    cada um numerava por conta própria e o POST não numerava, nascia sempre v1.
    """
    maior = (
        # `todos`, e não `objects`: o gerente padrão filtra a lápide (D116), e um
        # orçamento na lixeira devolveria um número **já usado**. Número de versão
        # é identidade numa cadeia de revisão, não rótulo — reusá-lo faria a
        # restauração colidir com o orçamento que nasceu no lugar dele, e faria
        # "v3" significar duas planilhas diferentes no histórico da obra.
        Orcamento.todos.filter(obra_id=obra_id)
        .order_by("-versao")
        .values_list("versao", flat=True)
        .first()
    )
    return (maior or 0) + 1


@transaction.atomic
def revisar_orcamento(
    orcamento: Orcamento, *, tipo: str, motivo: str, usuario_nome: str = ""
) -> Orcamento:
    """Clona o orçamento aprovado na versão seguinte, editável.

    A versão anterior vira `SUPERADO` — continua existindo e continua sendo a
    régua **daquele momento** (medições já feitas contra ela não mudam de base).
    A nova nasce em rascunho com a árvore inteira copiada, para o orçamentista
    mexer no que o aditivo mudou em vez de redigitar a planilha.
    """
    if orcamento.status != Orcamento.Status.APROVADO:
        raise RevisaoInvalida(
            "Só orçamento aprovado gera revisão — rascunho é editado direto."
        )

    nova = Orcamento.objects.create(
        tenant_id=orcamento.tenant_id,
        obra=orcamento.obra,
        descricao=orcamento.descricao,
        versao=proxima_versao(orcamento.obra_id),
        orcamento_origem=orcamento,
        base_referencial=orcamento.base_referencial,
        data_base=orcamento.data_base,
        regime_encargos=orcamento.regime_encargos,
        encargos_sociais_percentual=orcamento.encargos_sociais_percentual,
        bdi_percentual=orcamento.bdi_percentual,
        status=Orcamento.Status.RASCUNHO,
        observacao=orcamento.observacao,
    )
    _clonar_itens(orcamento, nova)
    recalcular_orcamento(nova)

    numero = RevisaoOrcamento.objects.filter(orcamento__obra=orcamento.obra).count() + 1
    RevisaoOrcamento.objects.create(
        tenant_id=orcamento.tenant_id,
        orcamento=nova,
        orcamento_anterior=orcamento,
        numero=numero,
        tipo=tipo,
        motivo=motivo,
        valor_anterior=orcamento.valor_total,
        valor_novo=nova.valor_total,
        criado_por_nome=(usuario_nome or "")[:150],
    )

    orcamento.status = Orcamento.Status.SUPERADO
    orcamento.save(update_fields=["status", "atualizado_em"])
    return nova


def _clonar_itens(origem: Orcamento, destino: Orcamento) -> None:
    """Copia a árvore preservando a hierarquia.

    Duas passadas porque `pai` aponta para linhas do mesmo lote: a primeira cria
    todas as linhas com `pai` nulo e guarda o de-para de ids; a segunda religa
    os pais. Simples e sem depender da ordem de inserção.
    """
    originais = list(ItemOrcado.objects.filter(orcamento=origem).order_by("item_orcado_id"))
    de_para: dict[int, int] = {}

    for original in originais:
        clone = ItemOrcado.objects.create(
            tenant_id=destino.tenant_id,
            orcamento=destino,
            pai=None,
            codigo_eap=original.codigo_eap,
            ordem=original.ordem,
            tipo_linha=original.tipo_linha,
            etapa=original.etapa,
            item=original.item,
            descricao=original.descricao,
            unidade=original.unidade,
            quantidade=original.quantidade,
            custo_unitario=original.custo_unitario,
            fonte_referencia=original.fonte_referencia,
            codigo_referencia=original.codigo_referencia,
            data_base_preco=original.data_base_preco,
            observacao=original.observacao,
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


def orcamento_vigente(tenant_id, obra_id) -> Orcamento | None:
    """O orçamento que vale para uma obra: a maior versão **aprovada**.

    Rascunho não é régua (ainda está sendo digitado) e superado já foi
    substituído. Sem aprovado, não há orçado — e o controle de custo diz isso
    em vez de inventar um número.
    """
    return (
        Orcamento.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, status=Orcamento.Status.APROVADO
        )
        .order_by("-versao")
        .first()
    )


def orcado_por_etapa(tenant_id, obra_id=None) -> dict[tuple[int, int | None], dict[str, Decimal]]:
    """Custo orçado por (obra, etapa) — o lado "orçado" do físico-financeiro.

    Chave igual à do `aplicado/` do SIL, que agrega movimentação por
    `(obra_id, etapa_id)`. Só considera linhas **analíticas**: o sintético é
    soma dos filhos e entraria em duplicidade.

    Devolve custo direto **e** valor com BDI porque a comparação certa depende
    da pergunta: material aplicado sai do estoque a custo, então o confronto
    honesto do SIL é contra o **custo direto**; o valor com BDI é o preço de
    venda, útil para margem, não para consumo.
    """
    from django.db.models import Sum

    orcamentos = [
        o
        for o in Orcamento.objects.filter(
            tenant_id=tenant_id, status=Orcamento.Status.APROVADO,
            **({"obra_id": obra_id} if obra_id else {}),
        ).order_by("obra_id", "-versao")
    ]
    # Uma obra pode ter mais de uma versão aprovada no histórico? Não deveria
    # (revisar rebaixa a anterior), mas o agrupamento abaixo garante que só a
    # maior versão de cada obra conte, mesmo se um dado antigo escapar.
    vigentes = {}
    for o in orcamentos:
        vigentes.setdefault(o.obra_id, o)

    if not vigentes:
        return {}

    linhas = (
        ItemOrcado.objects.filter(
            orcamento_id__in=[o.orcamento_id for o in vigentes.values()],
            tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
        )
        .values("orcamento__obra_id", "etapa_id")
        .annotate(direto=Sum("total_custo_direto"), com_bdi=Sum("total_com_bdi"))
    )
    return {
        (linha["orcamento__obra_id"], linha["etapa_id"]): {
            "orcado": linha["direto"] or Decimal("0"),
            "orcado_com_bdi": linha["com_bdi"] or Decimal("0"),
        }
        for linha in linhas
    }
