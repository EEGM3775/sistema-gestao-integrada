# backend/moduloorcamento/edicao.py
"""ORC.10 — a planilha como documento que se edita, não como lista que se preenche.

Separado de `planilha.py` (recálculo, EAP, aprovação e revisão) e de
`precificacao.py` (composição e BDI) por concern: aqui moram os **verbos de
edição estrutural** que o orçamentista usa o dia inteiro num Arquimedes ou num
Volare e que o módulo não tinha — mover, indentar, duplicar, aplicar em lote,
recompor a decomposição e desfazer.

Três invariantes que todo verbo daqui respeita, e que são o motivo de eles não
serem só `PATCH` soltos na `ItemOrcadoViewSet`:

1. **A árvore não fecha ciclo.** `pai` é auto-FK; arrastar uma etapa para dentro
   de um filho dela estouraria a pilha do recálculo. Toda mudança de `pai` passa
   por `_descendentes`.
2. **A ordem entre irmãos é densa e começa em zero.** Depois de qualquer mexida,
   cada grupo de irmãos é renumerado `0,1,2…`. Sem isso o `ordem` vira um campo
   com buracos, dois irmãos empatam e a EAP sai não-determinística.
3. **Quem fecha a conta é `planilha.recalcular_orcamento`.** Nenhuma função
   daqui escreve total nem código EAP na mão.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from . import planilha
from .models import (
    BancoPreco,
    ComponenteBancoPreco,
    InsumoReferencia,
    ItemBancoPreco,
    ItemOrcado,
    ItemOrcadoInsumo,
    LinhaMedicao,
    Orcamento,
)

QUATRO_CASAS = Decimal("0.0001")


class EdicaoInvalida(Exception):
    """Operação que a árvore ou o documento não admitem.

    Vira 400 na API — é erro do pedido, não do documento estar fechado (isso é
    `planilha.OrcamentoNaoEditavel`, que vira 409).
    """


# ---------------------------------------------------------------------------
# Leitura da árvore
# ---------------------------------------------------------------------------

def _por_id(orcamento: Orcamento) -> dict[int, ItemOrcado]:
    return {
        item.item_orcado_id: item
        for item in ItemOrcado.objects.filter(orcamento=orcamento)
    }


def _irmaos(itens: dict[int, ItemOrcado], pai_id: int | None) -> list[ItemOrcado]:
    """Filhos diretos de `pai_id`, na ordem em que a planilha se lê."""
    grupo = [i for i in itens.values() if i.pai_id == pai_id]
    grupo.sort(key=lambda i: (i.ordem, i.item_orcado_id))
    return grupo


def _descendentes(itens: dict[int, ItemOrcado], raiz_id: int) -> set[int]:
    """Ids de tudo que pende de `raiz_id`, ele inclusive.

    É a guarda contra ciclo (invariante 1) e também o que faz mover e duplicar
    levarem a subárvore junto — arrastar "Estrutura" sem os serviços dela não é
    mover, é desmontar.
    """
    filhos_de: dict[int | None, list[int]] = {}
    for item in itens.values():
        filhos_de.setdefault(item.pai_id, []).append(item.item_orcado_id)

    fechado: set[int] = set()
    pilha = [raiz_id]
    while pilha:
        atual = pilha.pop()
        if atual in fechado:
            continue
        fechado.add(atual)
        pilha.extend(filhos_de.get(atual, []))
    return fechado


def _renumerar(itens: dict[int, ItemOrcado]) -> None:
    """Densifica `ordem` em cada grupo de irmãos (invariante 2)."""
    grupos: dict[int | None, list[ItemOrcado]] = {}
    for item in itens.values():
        grupos.setdefault(item.pai_id, []).append(item)

    alterados = []
    for irmaos in grupos.values():
        irmaos.sort(key=lambda i: (i.ordem, i.item_orcado_id))
        for posicao, item in enumerate(irmaos):
            if item.ordem != posicao:
                item.ordem = posicao
                alterados.append(item)
    if alterados:
        ItemOrcado.objects.bulk_update(alterados, ["ordem"], batch_size=500)


def _carregar_selecao(orcamento: Orcamento, ids) -> tuple[dict[int, ItemOrcado], list[ItemOrcado]]:
    """Valida que os ids são deste orçamento e devolve a seleção em ordem de leitura."""
    itens = _por_id(orcamento)
    unicos = list(dict.fromkeys(int(i) for i in ids))
    if not unicos:
        raise EdicaoInvalida("Nenhuma linha selecionada.")
    fora = [i for i in unicos if i not in itens]
    if fora:
        raise EdicaoInvalida(
            f"Linha(s) {', '.join(str(i) for i in fora)} não pertencem a este orçamento."
        )
    selecao = [itens[i] for i in unicos]
    selecao.sort(key=lambda i: (i.ordem, i.item_orcado_id))
    return itens, selecao


# ---------------------------------------------------------------------------
# ORC.10b — mover, indentar, reordenar
# ---------------------------------------------------------------------------

OPERACOES_DE_BLOCO = ("indentar", "desindentar", "cima", "baixo")


@transaction.atomic
def mover(orcamento: Orcamento, ids, *, operacao=None, pai_id=None, posicao=None) -> int:
    """Move linhas (com as subárvores) para outro pai e/ou outra posição.

    Duas formas de pedir, porque são dois gestos diferentes na tela:

    - **`operacao`** — o gesto de teclado: `indentar`, `desindentar`, `cima`,
      `baixo`. Exige que a seleção seja de **irmãos**, que é como ela nasce
      quando se escolhe um bloco na grade; seleção espalhada pela árvore não tem
      "um nível acima" bem definido, e adivinhar um faria a planilha se
      reorganizar de um jeito que ninguém pediu.
    - **`pai_id` + `posicao`** — o gesto do mouse: arrastar e soltar num ponto
      exato. `posicao` é o índice entre os irmãos do destino **depois** de tirar
      de lá o que está sendo movido; `None` joga para o fim.

    O bloco movido mantém a ordem relativa interna. Devolve quantas linhas
    mudaram de lugar (as subárvores não contam — elas acompanham).
    """
    planilha.exigir_editavel(orcamento)
    itens, selecao = _carregar_selecao(orcamento, ids)

    if operacao:
        if operacao not in OPERACOES_DE_BLOCO:
            raise EdicaoInvalida(f"Operação '{operacao}' não existe.")
        pais = {i.pai_id for i in selecao}
        if len(pais) > 1:
            raise EdicaoInvalida(
                "Para indentar, desindentar ou reordenar, a seleção precisa ser de linhas "
                "irmãs — as escolhidas estão em níveis diferentes."
            )
        pai_atual = pais.pop()
        grupo = _irmaos(itens, pai_atual)
        marcados = {i.item_orcado_id for i in selecao}
        posicoes = [n for n, i in enumerate(grupo) if i.item_orcado_id in marcados]
        primeiro, ultimo = posicoes[0], posicoes[-1]

        if operacao == "indentar":
            # O novo pai é o irmão imediatamente acima que **não** está na
            # seleção. Sem ele não há nível para descer: a linha do topo de um
            # grupo não tem sob quem se abrigar.
            acima = next(
                (g for g in reversed(grupo[:primeiro]) if g.item_orcado_id not in marcados), None,
            )
            if acima is None:
                raise EdicaoInvalida(
                    "Não há linha acima no mesmo nível para receber esta — indentar "
                    "penduraria a linha no nada."
                )
            pai_id, posicao = acima.item_orcado_id, None

        elif operacao == "desindentar":
            if pai_atual is None:
                raise EdicaoInvalida("Esta linha já está no nível mais alto da planilha.")
            pai = itens[pai_atual]
            avos = _irmaos(itens, pai.pai_id)
            # Sobe um nível e pousa logo **depois** do antigo pai, que é onde o
            # olho espera encontrá-la — jogar para o fim do grupo faria a linha
            # sumir de vista na planilha grande.
            indice_do_pai = next(
                n for n, a in enumerate(avos) if a.item_orcado_id == pai.item_orcado_id
            )
            pai_id, posicao = pai.pai_id, indice_do_pai + 1

        else:  # cima / baixo — o bloco anda um passo dentro do próprio nível
            livres = [n for n, _ in enumerate(grupo) if n not in posicoes]
            alvo = None
            if operacao == "cima":
                alvo = max((n for n in livres if n < primeiro), default=None)
            else:
                alvo = min((n for n in livres if n > ultimo), default=None)
            if alvo is None:
                borda = "primeira" if operacao == "cima" else "última"
                raise EdicaoInvalida(f"A seleção já está na {borda} posição deste nível.")
            pai_id = pai_atual
            # A posição é contada sobre o grupo **sem** os selecionados, que é a
            # mesma régua do caminho de arrastar — assim as duas formas de pedir
            # não divergem numa linha de código a mais.
            restantes = [g for g in grupo if g.item_orcado_id not in marcados]
            posicao = next(
                n for n, g in enumerate(restantes)
                if g.item_orcado_id == grupo[alvo].item_orcado_id
            )
            if operacao == "baixo":
                posicao += 1

    else:
        pai_id = int(pai_id) if pai_id not in (None, "") else None

    if pai_id is not None and pai_id not in itens:
        raise EdicaoInvalida("A linha-pai de destino não é deste orçamento.")

    # Invariante 1 — ciclo. Vale para cada selecionado: soltar "Estrutura"
    # dentro de "Estrutura › Pilares" faria o recálculo girar para sempre.
    if pai_id is not None:
        for item in selecao:
            if pai_id in _descendentes(itens, item.item_orcado_id):
                raise EdicaoInvalida(
                    f"'{item.descricao}' não pode ser movida para dentro de si mesma "
                    "ou de uma linha que pende dela."
                )

    marcados = {i.item_orcado_id for i in selecao}
    destino = [g for g in _irmaos(itens, pai_id) if g.item_orcado_id not in marcados]
    corte = len(destino) if posicao is None else max(0, min(int(posicao), len(destino)))
    nova_ordem = destino[:corte] + selecao + destino[corte:]

    alterados = []
    for n, item in enumerate(nova_ordem):
        # `* 2` deixa buraco entre irmãos para o `_renumerar` densificar depois
        # sem empatar com quem não foi tocado neste grupo.
        if item.pai_id != pai_id or item.ordem != n * 2:
            item.pai_id = pai_id
            item.ordem = n * 2
            alterados.append(item)
    if alterados:
        ItemOrcado.objects.bulk_update(alterados, ["pai", "ordem"], batch_size=500)
        for item in alterados:
            itens[item.item_orcado_id] = item

    _renumerar(itens)
    planilha.recalcular_orcamento(orcamento)
    return len(selecao)


# ---------------------------------------------------------------------------
# ORC.10c — a composição da linha é editável, e o que se edita vira banco
# ---------------------------------------------------------------------------

NOME_DO_BANCO_DA_OBRA = "Composições — {obra}"


def banco_da_obra(orcamento: Orcamento) -> BancoPreco:
    """O banco da empresa onde as composições **daquela obra** vivem.

    A decisão do dono foi "composição editada mora sempre no banco de preço da
    empresa". Do jeito cru isso quebraria o snapshot: mexer no coeficiente de
    uma composição para a Obra A mudaria o custo da Obra B que usa a mesma, e
    planilha aprovada deixaria de ser régua. `BancoPreco.obra` já existe para
    exatamente este caso — o banco é da empresa, com obra declarada —, então a
    edição grava num banco por obra, criado sozinho na primeira vez.

    Reuso continua existindo e fica **explícito**: `promover_para_banco` copia a
    composição para um banco sem obra, que é o acervo geral da empresa.
    """
    nome = NOME_DO_BANCO_DA_OBRA.format(obra=orcamento.obra.nome_obra)[:120]
    banco, _ = BancoPreco.objects.get_or_create(
        tenant_id=orcamento.tenant_id,
        nome=nome,
        defaults={
            "descricao": (
                "Criado pelo Orçamento: guarda as composições ajustadas nas planilhas "
                "desta obra. Editar aqui não mexe em orçamento já montado — a linha "
                "guarda o seu próprio snapshot."
            ),
            "obra": orcamento.obra,
            "origem": BancoPreco.Origem.PROPRIA,
            "mes_referencia": orcamento.data_base,
        },
    )
    return banco


def _item_de_banco(banco: BancoPreco, *, codigo, descricao, unidade, tipo, custo) -> ItemBancoPreco:
    """Espelha um insumo/serviço no banco, pela chave `(banco, tipo, codigo)`."""
    item, criado = ItemBancoPreco.objects.get_or_create(
        tenant_id=banco.tenant_id,
        banco=banco,
        tipo=tipo,
        codigo=(codigo or "")[:30],
        defaults={
            "descricao": (descricao or "")[:500],
            "unidade": (unidade or "")[:20],
            "custo_unitario": Decimal(custo or 0),
        },
    )
    if not criado:
        item.descricao = (descricao or "")[:500]
        item.unidade = (unidade or "")[:20]
        item.custo_unitario = Decimal(custo or 0)
        item.save(update_fields=["descricao", "unidade", "custo_unitario"])
    return item


def _codigo_da_linha(linha: ItemOrcado) -> str:
    """Código estável para a composição da linha dentro do banco.

    Ordem de preferência: o código do catálogo, o da fonte, e por último um
    sintético derivado do id — feio, mas único, e melhor que deixar duas
    composições diferentes colidirem na chave do banco.
    """
    do_catalogo = getattr(linha.item, "codigo_interno", "") if linha.item_id else ""
    return (do_catalogo or linha.codigo_referencia or f"ORC-{linha.item_orcado_id}")[:30]


@transaction.atomic
def recompor_linha(linha: ItemOrcado, *, espelhar: bool = True) -> Decimal:
    """Refaz o custo unitário da linha a partir dos insumos que ela tem agora.

    É a metade que faltava da ORC.2: a explosão sabia **gerar** a memória de
    cálculo a partir do catálogo, mas nada sabia ler a memória de volta depois
    que alguém mexeu num coeficiente — e como não havia rota para mexer, isso
    nunca doeu. É o núcleo do Arquimedes: abrir a partida, trocar o consumo de
    argamassa, ver o preço mudar.

    O custo é a soma de `custo_no_item`, que já vem com encargo social embutido
    na parcela de mão de obra (quem embute é `ItemOrcadoInsumoSerializer`, na
    escrita) — somar `coeficiente × custo_unitario` aqui perderia o encargo e
    baratearia toda composição com pedreiro.

    `linha.preco_travado` respeitado: quem travou o preço declarou que a
    composição é memória e o número é cotação. Recompor por cima disso apagaria
    a cotação sem avisar.
    """
    total = sum(
        (i.custo_no_item for i in ItemOrcadoInsumo.objects.filter(item_orcado=linha)),
        Decimal("0"),
    )
    total = total.quantize(QUATRO_CASAS, rounding=ROUND_HALF_UP)
    if not linha.preco_travado and linha.custo_unitario != total:
        linha.custo_unitario = total
        linha.save(update_fields=["custo_unitario"])
    if espelhar:
        espelhar_no_banco(linha, banco_da_obra(linha.orcamento))
    planilha.recalcular_orcamento(linha.orcamento)
    return total


@transaction.atomic
def espelhar_no_banco(linha: ItemOrcado, banco: BancoPreco) -> ItemBancoPreco:
    """Grava a composição da linha como composição **do banco** informado.

    `ComponenteBancoPreco.filho` aponta um `ItemBancoPreco`, então cada insumo
    também precisa existir lá — é o que este laço faz antes de amarrar os
    componentes. Banco travado é recusado: a trava existe para proteger banco
    conferido, e ela não pode ter uma porta dos fundos pela grade do orçamento.
    """
    if not banco.editavel:
        raise EdicaoInvalida(
            f"O banco '{banco.nome}' está travado — destrave-o para gravar composição nele."
        )

    composicao = _item_de_banco(
        banco,
        codigo=_codigo_da_linha(linha),
        descricao=linha.descricao,
        unidade=linha.unidade,
        tipo=InsumoReferencia.Tipo.COMPOSICAO,
        custo=linha.custo_unitario,
    )

    insumos = list(ItemOrcadoInsumo.objects.filter(item_orcado=linha).select_related("item"))
    vistos = set()
    for insumo in insumos:
        codigo = (
            getattr(insumo.item, "codigo_interno", "") if insumo.item_id else ""
        ) or f"INS-{insumo.insumo_id}"
        filho = _item_de_banco(
            banco, codigo=codigo, descricao=insumo.descricao, unidade=insumo.unidade,
            tipo=InsumoReferencia.Tipo.INSUMO, custo=insumo.custo_unitario,
        )
        ComponenteBancoPreco.objects.update_or_create(
            tenant_id=banco.tenant_id, composicao=composicao, filho=filho,
            defaults={"coeficiente": insumo.coeficiente},
        )
        vistos.add(filho.pk)

    # Insumo tirado da linha sai do espelho também, senão o banco acumularia
    # componentes fantasmas que ninguém removeu de lugar nenhum.
    ComponenteBancoPreco.objects.filter(composicao=composicao).exclude(
        filho_id__in=vistos
    ).delete()

    banco.total_itens = ItemBancoPreco.objects.filter(banco=banco).count()
    banco.save(update_fields=["total_itens", "atualizado_em"])
    return composicao


@transaction.atomic
def promover_para_banco(linha: ItemOrcado, banco: BancoPreco) -> ItemBancoPreco:
    """Publica a composição da linha num banco **sem obra** — o acervo da empresa.

    É o reuso explícito: o que se ajusta numa obra só vira régua da empresa
    quando alguém diz que vira.
    """
    if banco.tenant_id != linha.tenant_id:
        raise EdicaoInvalida("O banco de destino é de outra empresa.")
    return espelhar_no_banco(linha, banco)


# ---------------------------------------------------------------------------
# ORC.10d — lote, duplicar e desfazer
# ---------------------------------------------------------------------------

CAMPOS_CLONAVEIS = (
    "tipo_linha", "etapa_id", "item_id", "descricao", "unidade", "quantidade",
    "custo_unitario", "fonte_referencia", "codigo_referencia", "data_base_preco",
    "bdi_id", "observacao", "texto_longo", "preco_travado",
)


def _clonar_um(origem: ItemOrcado, *, pai_id, ordem) -> ItemOrcado:
    dados = {campo: getattr(origem, campo) for campo in CAMPOS_CLONAVEIS}
    copia = ItemOrcado.objects.create(
        tenant_id=origem.tenant_id, orcamento_id=origem.orcamento_id,
        pai_id=pai_id, ordem=ordem, **dados,
    )
    ItemOrcadoInsumo.objects.bulk_create([
        ItemOrcadoInsumo(
            tenant_id=i.tenant_id, item_orcado=copia, item_id=i.item_id, descricao=i.descricao,
            unidade=i.unidade, categoria=i.categoria, coeficiente=i.coeficiente,
            custo_unitario=i.custo_unitario, custo_no_item=i.custo_no_item,
        )
        for i in ItemOrcadoInsumo.objects.filter(item_orcado=origem)
    ])
    LinhaMedicao.objects.bulk_create([
        LinhaMedicao(
            tenant_id=m.tenant_id, item_orcado=copia, ordem=m.ordem, descricao=m.descricao,
            sinal=m.sinal, repeticoes=m.repeticoes, comprimento=m.comprimento,
            largura=m.largura, altura=m.altura, formula=m.formula, total=m.total,
            referencia_projeto=m.referencia_projeto,
        )
        for m in LinhaMedicao.objects.filter(item_orcado=origem)
    ])
    return copia


@transaction.atomic
def duplicar(orcamento: Orcamento, ids) -> list[int]:
    """Duplica linhas **com a subárvore**, logo abaixo de cada original.

    Leva junto a memória de cálculo e a memória do quantitativo: uma cópia que
    perdesse a composição viraria preço digitado sem procedência, e é
    exatamente o oposto do que duplicar serve — repetir um trecho conferido.
    """
    planilha.exigir_editavel(orcamento)
    itens, selecao = _carregar_selecao(orcamento, ids)

    # Selecionado que já está dentro de outro selecionado é ignorado: a
    # subárvore dele já vai na cópia do ancestral, e duplicá-lo de novo geraria
    # uma cópia dentro da cópia.
    raizes = []
    for item in selecao:
        ancestral = item.pai_id
        dentro = False
        while ancestral is not None:
            if any(s.item_orcado_id == ancestral for s in selecao):
                dentro = True
                break
            ancestral = itens[ancestral].pai_id if ancestral in itens else None
        if not dentro:
            raizes.append(item)

    filhos_de: dict[int | None, list[ItemOrcado]] = {}
    for item in itens.values():
        filhos_de.setdefault(item.pai_id, []).append(item)
    for grupo in filhos_de.values():
        grupo.sort(key=lambda i: (i.ordem, i.item_orcado_id))

    # Abre espaço entre os irmãos **antes** de copiar. Sem isto a cópia nasceria
    # com `ordem` empatada com a do irmão seguinte, e o desempate por id a
    # jogaria para depois dele — a cópia apareceria longe da original, que é
    # exatamente o que duplicar não pode fazer.
    espacados = []
    for item in itens.values():
        item.ordem = item.ordem * 2
        espacados.append(item)
    ItemOrcado.objects.bulk_update(espacados, ['ordem'], batch_size=500)

    novos: list[int] = []

    def copiar(origem: ItemOrcado, pai_id, ordem) -> ItemOrcado:
        copia = _clonar_um(origem, pai_id=pai_id, ordem=ordem)
        novos.append(copia.item_orcado_id)
        for n, filho in enumerate(filhos_de.get(origem.item_orcado_id, [])):
            copiar(filho, copia.item_orcado_id, n)
        return copia

    for origem in raizes:
        copiar(origem, origem.pai_id, origem.ordem + 1)

    _renumerar(_por_id(orcamento))
    planilha.recalcular_orcamento(orcamento)
    return novos


@transaction.atomic
def excluir(orcamento: Orcamento, ids) -> dict:
    """Exclui linhas e devolve o **material para refazê-las**.

    Sem esse retorno não haveria Ctrl+Z de exclusão: a pilha do cliente
    conseguiria desfazer edição de célula e movimentação (ambas reversíveis por
    outro pedido), mas uma linha apagada não voltaria de lugar nenhum. O
    payload é a árvore inteira, achatada, com a posição de cada uma.
    """
    planilha.exigir_editavel(orcamento)
    itens, selecao = _carregar_selecao(orcamento, ids)

    atingidos: set[int] = set()
    for item in selecao:
        atingidos |= _descendentes(itens, item.item_orcado_id)

    ordenados = sorted(
        (itens[i] for i in atingidos), key=lambda i: (i.ordem, i.item_orcado_id),
    )
    payload = [
        {
            "id_antigo": item.item_orcado_id,
            "pai_antigo": item.pai_id,
            "ordem": item.ordem,
            **{
                campo.replace("_id", ""): (
                    str(valor) if isinstance(valor := getattr(item, campo), Decimal)
                    else (valor.isoformat() if hasattr(valor, "isoformat") else valor)
                )
                for campo in CAMPOS_CLONAVEIS
            },
        }
        for item in ordenados
    ]

    ItemOrcado.objects.filter(item_orcado_id__in=atingidos).delete()
    _renumerar(_por_id(orcamento))
    planilha.recalcular_orcamento(orcamento)
    return {"excluidas": len(atingidos), "desfazer": payload}


@transaction.atomic
def restaurar(orcamento: Orcamento, payload) -> list[int]:
    """Recria o que `excluir` devolveu — o outro lado do Ctrl+Z.

    Os ids **mudam**: o banco não reaproveita chave primária, e fingir que
    reaproveitaria seria mentir para quem tivesse guardado o id antigo. O que se
    preserva é o que importa numa planilha — a forma da árvore, a ordem e o
    conteúdo. `pai_antigo` é traduzido pelo mapa à medida que as linhas nascem,
    o que funciona porque o payload vem em ordem de leitura (pai antes de filho).
    """
    planilha.exigir_editavel(orcamento)
    de_para: dict[int, int] = {}
    criados: list[int] = []

    for bruto in payload:
        pai_antigo = bruto.get("pai_antigo")
        pai_id = de_para.get(pai_antigo) if pai_antigo is not None else None
        # Pai que não estava no payload (a linha tinha pai fora do trecho
        # apagado) volta para onde estava, se ele ainda existe.
        if pai_id is None and pai_antigo is not None:
            pai_id = pai_antigo if ItemOrcado.objects.filter(
                orcamento=orcamento, pk=pai_antigo,
            ).exists() else None

        linha = ItemOrcado.objects.create(
            tenant_id=orcamento.tenant_id, orcamento=orcamento, pai_id=pai_id,
            ordem=bruto.get("ordem") or 0,
            tipo_linha=bruto.get("tipo_linha") or ItemOrcado.TipoLinha.ANALITICO,
            etapa_id=bruto.get("etapa") or None,
            item_id=bruto.get("item") or None,
            descricao=bruto.get("descricao") or "",
            unidade=bruto.get("unidade") or "",
            quantidade=Decimal(str(bruto.get("quantidade") or 0)),
            custo_unitario=Decimal(str(bruto.get("custo_unitario") or 0)),
            fonte_referencia=bruto.get("fonte_referencia") or "",
            codigo_referencia=bruto.get("codigo_referencia") or "",
            data_base_preco=bruto.get("data_base_preco") or None,
            bdi_id=bruto.get("bdi") or None,
            observacao=bruto.get("observacao") or "",
            texto_longo=bruto.get("texto_longo") or "",
            preco_travado=bool(bruto.get("preco_travado")),
        )
        de_para[bruto.get("id_antigo")] = linha.item_orcado_id
        criados.append(linha.item_orcado_id)

    _renumerar(_por_id(orcamento))
    planilha.recalcular_orcamento(orcamento)
    return criados


@transaction.atomic
def aplicar_percentual(orcamento: Orcamento, ids, percentual, *, campo="custo_unitario") -> int:
    """Aplica ±x% sobre quantidade ou custo unitário da seleção.

    O verbo de lote que todo orçamentista usa quando a proposta precisa fechar
    num número: −3% no custo, +10% na quantidade de um trecho. Só linha
    analítica — sintético não tem número próprio, é soma dos filhos, e aplicar
    percentual nele contaria duas vezes.

    **Linha com preço travado fica de fora** quando o campo é o custo: a trava é
    a declaração de que aquele número é cotação fechada, e um lote que a
    ignorasse desfaria em silêncio o que o travamento existe para segurar.
    """
    if campo not in ("custo_unitario", "quantidade"):
        raise EdicaoInvalida(f"Campo '{campo}' não aceita percentual.")
    planilha.exigir_editavel(orcamento)
    _, selecao = _carregar_selecao(orcamento, ids)

    fator = Decimal("1") + (Decimal(str(percentual)) / Decimal("100"))
    if fator < 0:
        raise EdicaoInvalida("Redução maior que 100% deixaria o valor negativo.")

    alterados = []
    for linha in selecao:
        if linha.tipo_linha != ItemOrcado.TipoLinha.ANALITICO:
            continue
        if campo == "custo_unitario" and linha.preco_travado:
            continue
        setattr(
            linha, campo,
            (getattr(linha, campo) * fator).quantize(QUATRO_CASAS, rounding=ROUND_HALF_UP),
        )
        alterados.append(linha)

    if alterados:
        ItemOrcado.objects.bulk_update(alterados, [campo], batch_size=500)
    planilha.recalcular_orcamento(orcamento)
    return len(alterados)


@transaction.atomic
def arredondar(orcamento: Orcamento, ids, casas=2, *, campo="quantidade") -> int:
    """Arredonda quantidade ou custo da seleção para N casas.

    Existe pelo mesmo motivo do percentual: quantidade que saiu de um takeoff
    vem com quatro casas, e a peça que vai para a licitação não se lê assim.
    """
    if campo not in ("custo_unitario", "quantidade"):
        raise EdicaoInvalida(f"Campo '{campo}' não se arredonda.")
    planilha.exigir_editavel(orcamento)
    _, selecao = _carregar_selecao(orcamento, ids)

    casas = max(0, min(int(casas), 4))
    passo = Decimal(1).scaleb(-casas)
    alterados = []
    for linha in selecao:
        if linha.tipo_linha != ItemOrcado.TipoLinha.ANALITICO:
            continue
        if campo == "custo_unitario" and linha.preco_travado:
            continue
        novo = getattr(linha, campo).quantize(passo, rounding=ROUND_HALF_UP)
        if novo != getattr(linha, campo):
            setattr(linha, campo, novo)
            alterados.append(linha)

    if alterados:
        ItemOrcado.objects.bulk_update(alterados, [campo], batch_size=500)
    planilha.recalcular_orcamento(orcamento)
    return len(alterados)


@transaction.atomic
def substituir_texto(orcamento: Orcamento, procurar, trocar_por, *, ids=None) -> int:
    """Localizar e substituir na descrição — ORC.10f.

    Restrito a `descricao` de propósito. Substituição cega em campo numérico ou
    em código de referência é o tipo de conveniência que corrompe uma planilha
    inteira em um clique, e o desfazer da grade não alcançaria o que já foi
    gravado no banco.
    """
    planilha.exigir_editavel(orcamento)
    if not procurar:
        raise EdicaoInvalida("Informe o texto a procurar.")

    if ids:
        _, alvos = _carregar_selecao(orcamento, ids)
    else:
        alvos = list(ItemOrcado.objects.filter(orcamento=orcamento))

    alterados = []
    for linha in alvos:
        if procurar in linha.descricao:
            linha.descricao = linha.descricao.replace(procurar, trocar_por or "")[:255]
            alterados.append(linha)
    if alterados:
        ItemOrcado.objects.bulk_update(alterados, ["descricao"], batch_size=500)
    return len(alterados)


# ---------------------------------------------------------------------------
# ORC.10e — reabrir o documento fechado, com nome e motivo
# ---------------------------------------------------------------------------

@transaction.atomic
def destravar_orcamento(orcamento: Orcamento, *, motivo: str, usuario_nome: str = "") -> Orcamento:
    """Devolve um orçamento aprovado ao rascunho — sob permissão própria.

    O congelamento continua sendo o padrão: aprovado é a régua contra a qual o
    custo real é medido, e o caminho normal para mudá-lo é `revisar`, que
    versiona. Mas exigir uma versão nova para corrigir um erro de digitação
    encontrado dez minutos depois de aprovar é atrito sem ganho, e foi por isso
    que o dono escolheu o meio-termo: quem tem `orcamento.orcamento.destravar`
    reabre, **com motivo obrigatório e rastro**.

    O rastro fica na `observacao` porque ela sobrevive à mudança de status e
    acompanha o documento para onde ele for — inclusive para a exportação, que é
    onde um conferente externo vai procurar. `RevisaoOrcamento` não serve aqui:
    ela documenta a diferença entre **duas versões aprovadas**, e destravar não
    cria versão nenhuma.
    """
    if orcamento.status != Orcamento.Status.APROVADO:
        raise EdicaoInvalida(
            f"Só orçamento aprovado se destrava — este está "
            f"{orcamento.get_status_display().lower()}."
        )
    if not (motivo or "").strip():
        raise EdicaoInvalida("Destravar exige motivo declarado.")

    from django.utils import timezone

    carimbo = timezone.now().strftime("%d/%m/%Y %H:%M")
    quem = usuario_nome or "usuário não identificado"
    registro = f"[{carimbo}] Destravado por {quem}: {motivo.strip()}"
    orcamento.observacao = f"{orcamento.observacao}\n{registro}".strip()
    orcamento.status = Orcamento.Status.RASCUNHO
    orcamento.aprovado_em = None
    orcamento.aprovado_por_nome = ""
    orcamento.save(
        update_fields=["status", "observacao", "aprovado_em", "aprovado_por_nome", "atualizado_em"]
    )
    return orcamento
