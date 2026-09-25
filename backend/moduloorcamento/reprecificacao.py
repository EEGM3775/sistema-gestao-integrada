# backend/moduloorcamento/reprecificacao.py
"""ORC.5b — trocar a data-base da planilha, com prévia e desfazer.

A planilha guarda **snapshot** de preço: a linha que entrou em junho gravou o
custo e a data-base de junho, e não muda sozinha quando sai a tabela de julho.
Isso é de propósito (orçamento aprovado é régua histórica), mas cria a operação
oposta — *quero* trocar de data-base, conscientemente.

Três decisões que vêm do domínio:

1. **Qualquer publicação, para frente ou para trás.** Em licitação a data-base é
   a do edital, e ela costuma ser passada; "atualizar" não é sinônimo de "pegar a
   mais nova". O destino é escolhido, nunca inferido.
2. **Prévia antes de aplicar.** O lote nasce `PREVIA` com uma linha por item —
   preço velho, preço novo, delta — e só vira `APLICADA` quando alguém confirma
   a seleção. Descobrir depois que o total subiu 4% sem saber onde é o defeito
   que a prévia existe para impedir.
3. **Desfazer restaura a procedência, não só o número.** Uma linha que voltou ao
   preço velho mas continua dizendo que veio da publicação nova é rastro falso —
   e rastro é o que a auditoria de licitação confere.

**Só em rascunho.** Orçamento aprovado tem a escrita bloqueada por
`planilha.exigir_editavel`, e é assim que deve ser: o SIL já compara consumo
contra aquela régua. Reprecificar aprovado é `revisar` primeiro.

`somente_ate` é a **data de corte** do Sienge: só toca linha cujo preço é igual
ou anterior à data informada. Serve para atualizar o que ficou para trás sem
mexer no que já foi renegociado à mão.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    BancoPreco, BaseReferencial, InsumoReferencia, ItemBancoPreco, ItemOrcado,
    LinhaReprecificacao, Orcamento, Reprecificacao,
)
from .planilha import dinheiro, exigir_editavel, recalcular_orcamento


class ReprecificacaoInvalida(Exception):
    """Operação pedida sobre lote/orçamento em estado que não permite."""


def _como_data(valor) -> date | None:
    """Normaliza a data de corte, que chega em dois formatos por dois caminhos.

    Do shell e dos testes vem `date`; **da API vem string** — o corpo do POST é
    JSON, e JSON não tem tipo data. Sem esta coerção a comparação
    `item.data_base_preco > somente_ate` virava `date > str` e derrubava a
    requisição com 500, embora todo teste passasse: eles chamam o serviço com
    `date` já pronto, e o defeito morava exatamente no degrau entre os dois.

    Aceita ISO (`2026-08-17`, que é o que o `<input type="date">` manda) e o
    `dd/mm/aaaa` que o brasileiro digita, porque um dia alguém vai mandar o
    segundo. O que não for data vira `ReprecificacaoInvalida`, que a view já
    traduz para 400 — erro do pedido, não do servidor.
    """
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            continue
    raise ReprecificacaoInvalida(
        f"Data de corte inválida: {valor!r}. Use AAAA-MM-DD ou DD/MM/AAAA."
    )


def _precos_do_destino(*, base: BaseReferencial | None, banco: BancoPreco | None) -> dict[str, dict]:
    """Índice `código → preço` da publicação de destino, numa consulta só.

    Um SELECT por linha da planilha seria o caminho óbvio e transformaria a
    prévia de um orçamento de 800 itens em 800 idas ao banco.
    """
    if base is not None:
        linhas = InsumoReferencia.objects.filter(base=base).values(
            "codigo", "custo_unitario", "descricao", "unidade",
        )
        fonte = base.fonte
        data_base = base.mes_referencia
    elif banco is not None:
        linhas = ItemBancoPreco.objects.filter(banco=banco).values(
            "codigo", "custo_unitario", "descricao", "unidade",
        )
        fonte = banco.fonte
        data_base = banco.mes_referencia
    else:
        raise ReprecificacaoInvalida("Informe a publicação ou o banco de destino.")

    return {
        linha["codigo"]: {
            "custo": linha["custo_unitario"],
            "descricao": linha["descricao"],
            "unidade": linha["unidade"],
            "fonte": fonte,
            "data_base": data_base,
        }
        for linha in linhas
    }


def _onde_mais_existe(
    codigos: set[str], base: BaseReferencial | None,
) -> dict[str, list[str]]:
    """Para cada código ausente do destino, em que **outras UFs** ele existe
    naquele mesmo fonte + mês.

    Existe por causa da ORC.8, que criou uma segunda causa para "não achei este
    código aqui" — e as duas pedem ações opostas:

    - **aposentado pela fonte** (a causa do D99): a SINAPI tirou o item do
      catálogo. Ele não volta, e a linha precisa de substituto;
    - **sem pesquisa nesta UF** (a causa nova): o item existe no mês, com preço
      em outros estados, e o que faltou foi a **pesquisa** naquele. O cabeçalho
      do arquivo oficial declara isso — *"preço em branco para determinado
      estado significa que não houve pesquisa"* —, e por isso a carga não grava
      a linha (§4.1, regra 1: branco não é zero). O item está vivo, costuma
      voltar no mês seguinte, e o caminho é outro: usar a publicação vizinha,
      cotar, ou pôr no banco de preço da empresa.

    Dizer "não existe na publicação de destino" no segundo caso é verdade
    literal e mentira prática: manda procurar substituto para um insumo que não
    morreu. Uma consulta só, e só quando falta alguém.
    """
    if not codigos or base is None:
        return {}
    achados: dict[str, list[str]] = {}
    for codigo, uf in (
        InsumoReferencia.objects
        .filter(
            base__fonte=base.fonte,
            base__mes_referencia=base.mes_referencia,
            codigo__in=codigos,
        )
        # Fora a **UF inteira** do destino, não só aquela publicação: o outro
        # regime do mesmo estado não é "outro lugar onde o item existe", e
        # listá-lo faria a mensagem mandar o orçamentista de BA procurar preço
        # na BA. O que interessa é a UF vizinha.
        .exclude(base__uf=base.uf)
        .values_list("codigo", "base__uf")
        .distinct()
    ):
        if uf and uf not in achados.setdefault(codigo, []):
            achados[codigo].append(uf)
    for ufs in achados.values():
        ufs.sort()
    return achados


@transaction.atomic
def gerar_previa(
    orcamento: Orcamento,
    *,
    base_destino: BaseReferencial | None = None,
    banco_destino: BancoPreco | None = None,
    somente_ate=None,
    usuario_nome: str = "",
) -> Reprecificacao:
    """Monta o lote em `PREVIA`, sem tocar em nenhuma linha da planilha."""
    exigir_editavel(orcamento)
    if base_destino is None and banco_destino is None:
        raise ReprecificacaoInvalida("Escolha a publicação ou o banco de destino.")
    if base_destino is not None and banco_destino is not None:
        raise ReprecificacaoInvalida("Escolha só uma origem de preço.")
    somente_ate = _como_data(somente_ate)

    precos = _precos_do_destino(base=base_destino, banco=banco_destino)
    data_base_destino = base_destino.mes_referencia if base_destino else banco_destino.mes_referencia

    # Prévia anterior ainda aberta vira lixo assim que outra é pedida: duas
    # prévias vivas sobre o mesmo orçamento aplicariam preços conflitantes.
    Reprecificacao.objects.filter(
        orcamento=orcamento, status=Reprecificacao.Status.PREVIA
    ).delete()

    lote = Reprecificacao.objects.create(
        tenant_id=orcamento.tenant_id,
        orcamento=orcamento,
        base_destino=base_destino,
        banco_destino=banco_destino,
        data_base_destino=data_base_destino,
        somente_ate=somente_ate,
        status=Reprecificacao.Status.PREVIA,
        total_antes=orcamento.valor_total or Decimal("0"),
        criado_por_nome=(usuario_nome or "")[:150],
    )

    candidatas = ItemOrcado.objects.filter(
        orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
        # ORC.10e — linha com preço travado fica fora do lote inteiro, e não
        # apenas desmarcada: travar é declarar que aquele número é cotação
        # fechada, e uma prévia que a oferecesse marcável faria o desfazer ser
        # a única defesa contra desfazer a negociação sem ninguém ver.
        preco_travado=False,
    ).exclude(codigo_referencia="")

    # Os que o destino não tem — apurados antes do laço para a distinção entre
    # "aposentado" e "sem pesquisa nesta UF" custar **uma** consulta, e não uma
    # por linha faltante.
    faltantes = {
        item.codigo_referencia for item in candidatas
        if item.codigo_referencia and item.codigo_referencia not in precos
        and not (somente_ate and item.data_base_preco and item.data_base_preco > somente_ate)
    }
    tambem_em = _onde_mais_existe(faltantes, base_destino)

    linhas: list[LinhaReprecificacao] = []
    descontinuadas = 0
    for item in candidatas:
        if somente_ate and item.data_base_preco and item.data_base_preco > somente_ate:
            continue
        novo = precos.get(item.codigo_referencia)
        if novo is None:
            # O código não está na publicação de destino. Pular em silêncio (o
            # que se fazia aqui) deixava a linha com o preço velho enquanto o
            # cabeçalho passava a anunciar a data-base nova: a planilha mentia,
            # e mentia com aparência de certa, que é o pior tipo de erro numa
            # peça de licitação. Entra no lote como aviso, com
            # `custo_depois == custo_antes` para não mover nada e
            # `selecionada=False` para nunca ser aplicada.
            #
            # **Duas causas, um efeito** (ORC.8): o item pode ter sido aposentado
            # pela fonte ou simplesmente não ter tido pesquisa naquela UF. O
            # efeito é o mesmo — não há preço novo para aplicar, e a linha fica
            # com a data antiga —, mas a **ação** de quem orça é oposta, e é por
            # isso que a distinção mora no `motivo` em vez de virar dois estados:
            # quem lê a prévia precisa saber se procura substituto ou se olha a
            # publicação vizinha. Ver `_onde_mais_existe`.
            outras_ufs = tambem_em.get(item.codigo_referencia or "", [])
            if outras_ufs:
                motivo = (
                    f"Sem pesquisa de preço para {item.codigo_referencia} nesta "
                    f"publicação — o item existe no mesmo mês em "
                    f"{', '.join(outras_ufs[:6])}"
                    f"{'…' if len(outras_ufs) > 6 else ''}. "
                    f"Preço mantido de {item.data_base_preco or 'origem desconhecida'}."
                )
            else:
                motivo = (
                    f"Código {item.codigo_referencia} não existe na publicação de "
                    f"destino — item aposentado pela fonte. Preço mantido de "
                    f"{item.data_base_preco or 'origem desconhecida'}."
                )
            descontinuadas += 1
            linhas.append(LinhaReprecificacao(
                tenant_id=orcamento.tenant_id,
                reprecificacao=lote,
                item_orcado=item,
                custo_antes=item.custo_unitario,
                custo_depois=item.custo_unitario,
                fonte_antes=item.fonte_referencia or "",
                codigo_antes=item.codigo_referencia or "",
                data_base_antes=item.data_base_preco,
                fonte_depois="",
                codigo_depois="",
                data_base_depois=None,
                selecionada=False,
                descontinuado=True,
                motivo=motivo[:255],
            ))
            continue
        if novo["custo"] == item.custo_unitario:
            continue
        linhas.append(LinhaReprecificacao(
            tenant_id=orcamento.tenant_id,
            reprecificacao=lote,
            item_orcado=item,
            custo_antes=item.custo_unitario,
            custo_depois=novo["custo"],
            fonte_antes=item.fonte_referencia or "",
            codigo_antes=item.codigo_referencia or "",
            data_base_antes=item.data_base_preco,
            fonte_depois=novo["fonte"] or "",
            codigo_depois=item.codigo_referencia or "",
            data_base_depois=novo["data_base"],
            selecionada=True,
        ))

    if linhas:
        LinhaReprecificacao.objects.bulk_create(linhas, batch_size=500)

    # `linhas_afetadas` conta preço que muda. A descontinuada não muda preço
    # nenhum — somá-la aqui faria o lote anunciar um efeito que ele não tem.
    lote.linhas_afetadas = len(linhas) - descontinuadas
    lote.linhas_descontinuadas = descontinuadas
    lote.total_depois = _total_simulado(orcamento, linhas)
    lote.save(update_fields=["linhas_afetadas", "linhas_descontinuadas", "total_depois"])
    return lote


def _total_simulado(orcamento: Orcamento, linhas: list[LinhaReprecificacao]) -> Decimal:
    """Total que o orçamento teria se todas as linhas do lote fossem aplicadas.

    Aproximação deliberada: soma o delta de cada linha (Δcusto × quantidade ×
    fator de BDI padrão) sobre o total atual, em vez de reexecutar o recálculo da
    árvore. O número exato sai do `recalcular_orcamento` na hora de aplicar; aqui
    o que importa é a ordem de grandeza para a decisão, e reexecutar a árvore
    inteira só para uma prévia custaria caro numa planilha grande.
    """
    fator = Decimal("1") + (orcamento.bdi_percentual or Decimal("0")) / Decimal("100")
    delta = Decimal("0")
    for linha in linhas:
        if linha.descontinuado:
            continue  # não tem preço novo; entrou no lote só para ser vista
        quantidade = linha.item_orcado.quantidade or Decimal("0")
        delta += (linha.custo_depois - linha.custo_antes) * quantidade * fator
    return dinheiro((orcamento.valor_total or Decimal("0")) + delta)


@transaction.atomic
def aplicar(
    lote: Reprecificacao,
    *,
    selecionadas: list[int] | None = None,
    usuario_nome: str = "",
) -> Reprecificacao:
    """Aplica as linhas escolhidas e congela o lote como `APLICADA`.

    `selecionadas` são ids de `LinhaReprecificacao`; `None` = todas. O que não
    entrou fica no lote com `selecionada=False`, então o histórico mostra o que
    foi oferecido e recusado, não só o que passou.
    """
    if lote.status != Reprecificacao.Status.PREVIA:
        raise ReprecificacaoInvalida("Só uma prévia pode ser aplicada.")
    orcamento = lote.orcamento
    exigir_editavel(orcamento)

    linhas = list(lote.linhas.select_related("item_orcado"))
    if selecionadas is not None:
        escolhidas = set(selecionadas)
        for linha in linhas:
            # Descontinuada nunca é selecionável, nem que venha marcada no pedido:
            # não existe preço novo para aplicar, e aceitar a seleção gravaria o
            # preço velho como se fosse da publicação nova.
            linha.selecionada = (linha.linha_id in escolhidas) and not linha.descontinuado
        LinhaReprecificacao.objects.bulk_update(linhas, ["selecionada"], batch_size=500)

    aplicar_estas = [linha for linha in linhas if linha.selecionada and not linha.descontinuado]
    itens: list[ItemOrcado] = []
    for linha in aplicar_estas:
        item = linha.item_orcado
        item.custo_unitario = linha.custo_depois
        item.fonte_referencia = linha.fonte_depois or item.fonte_referencia
        item.data_base_preco = linha.data_base_depois
        itens.append(item)
        linha.aplicada = True

    if itens:
        ItemOrcado.objects.bulk_update(
            itens, ["custo_unitario", "fonte_referencia", "data_base_preco"], batch_size=500,
        )
        LinhaReprecificacao.objects.bulk_update(aplicar_estas, ["aplicada"], batch_size=500)

    # A data-base do cabeçalho acompanha, senão a planilha diria "junho" com
    # preços de julho — e é o cabeçalho que a peça de licitação carrega.
    if lote.data_base_destino:
        orcamento.data_base = lote.data_base_destino
    if lote.base_destino_id:
        orcamento.base_referencial_id = lote.base_destino_id
    orcamento.save(update_fields=["data_base", "base_referencial", "atualizado_em"])

    recalcular_orcamento(orcamento)
    orcamento.refresh_from_db()

    lote.status = Reprecificacao.Status.APLICADA
    lote.aplicada_em = timezone.now()
    lote.linhas_afetadas = len(aplicar_estas)
    lote.total_depois = orcamento.valor_total or Decimal("0")
    if usuario_nome:
        lote.criado_por_nome = usuario_nome[:150]
    lote.save(update_fields=[
        "status", "aplicada_em", "linhas_afetadas", "total_depois", "criado_por_nome",
    ])
    return lote


@transaction.atomic
def desfazer(lote: Reprecificacao) -> Reprecificacao:
    """Restaura preço, fonte e data-base de cada linha aplicada.

    Só o **último** lote aplicado pode ser desfeito. Desfazer um lote antigo
    sobrescreveria o preço posto por um lote posterior com um valor mais velho
    ainda, e o histórico deixaria de descrever a planilha.
    """
    if lote.status != Reprecificacao.Status.APLICADA:
        raise ReprecificacaoInvalida("Só um lote aplicado pode ser desfeito.")

    ultimo = (
        Reprecificacao.objects
        .filter(orcamento=lote.orcamento, status=Reprecificacao.Status.APLICADA)
        .order_by("-aplicada_em", "-reprecificacao_id").first()
    )
    if ultimo and ultimo.pk != lote.pk:
        raise ReprecificacaoInvalida(
            "Desfaça primeiro a reprecificação mais recente — desfazer fora de ordem "
            "deixaria a planilha com preços de lotes diferentes."
        )

    orcamento = lote.orcamento
    exigir_editavel(orcamento)

    linhas = list(lote.linhas.filter(aplicada=True).select_related("item_orcado"))
    itens: list[ItemOrcado] = []
    for linha in linhas:
        item = linha.item_orcado
        item.custo_unitario = linha.custo_antes
        item.fonte_referencia = linha.fonte_antes
        item.data_base_preco = linha.data_base_antes
        itens.append(item)

    if itens:
        ItemOrcado.objects.bulk_update(
            itens, ["custo_unitario", "fonte_referencia", "data_base_preco"], batch_size=500,
        )

    anterior = (
        Reprecificacao.objects
        .filter(orcamento=orcamento, status=Reprecificacao.Status.APLICADA)
        .exclude(pk=lote.pk).order_by("-aplicada_em", "-reprecificacao_id").first()
    )
    orcamento.data_base = anterior.data_base_destino if anterior else _data_base_original(lote)
    if lote.base_destino_id and anterior is None:
        orcamento.base_referencial_id = None
    orcamento.save(update_fields=["data_base", "base_referencial", "atualizado_em"])

    recalcular_orcamento(orcamento)

    lote.status = Reprecificacao.Status.DESFEITA
    lote.desfeita_em = timezone.now()
    lote.save(update_fields=["status", "desfeita_em"])
    return lote


def _data_base_original(lote: Reprecificacao):
    """Data-base que as linhas do lote tinham antes — a mais frequente entre elas.

    Não há um campo "data-base anterior do cabeçalho" e inventar um exigiria
    migração; a moda das linhas reconstrói o valor com fidelidade suficiente,
    porque um lote reprecifica linhas que vinham todas da mesma publicação.
    """
    contagem: dict = {}
    for data in lote.linhas.values_list("data_base_antes", flat=True):
        if data:
            contagem[data] = contagem.get(data, 0) + 1
    if not contagem:
        return None
    return max(contagem.items(), key=lambda par: par[1])[0]


def serializar_previa(lote: Reprecificacao) -> dict:
    """A prévia como a tela precisa: item a item e o efeito no total."""
    linhas = lote.linhas.select_related("item_orcado").order_by("item_orcado__codigo_eap")
    return {
        "reprecificacao": lote.pk,
        "orcamento": lote.orcamento_id,
        "status": lote.status,
        "destino": (
            lote.base_destino.rotulo or lote.base_destino.rotulo_automatico()
            if lote.base_destino_id else
            lote.banco_destino.rotulo_automatico() if lote.banco_destino_id else None
        ),
        "data_base_destino": lote.data_base_destino,
        "somente_ate": lote.somente_ate,
        "total_antes": str(lote.total_antes),
        "total_depois": str(lote.total_depois),
        "delta": str(dinheiro(lote.delta)),
        "delta_pct": (
            str((lote.delta / lote.total_antes * Decimal("100")).quantize(Decimal("0.01")))
            if lote.total_antes else None
        ),
        "linhas_afetadas": lote.linhas_afetadas,
        "linhas_descontinuadas": lote.linhas_descontinuadas,
        "linhas": [
            {
                "linha": linha.linha_id,
                "item_orcado": linha.item_orcado_id,
                "codigo_eap": linha.item_orcado.codigo_eap,
                "descricao": linha.item_orcado.descricao,
                "unidade": linha.item_orcado.unidade,
                "quantidade": str(linha.item_orcado.quantidade),
                "codigo_referencia": linha.codigo_antes,
                "custo_antes": str(linha.custo_antes),
                "custo_depois": str(linha.custo_depois),
                "delta_unitario": str(linha.delta_unitario),
                "delta_pct": (
                    str((linha.delta_unitario / linha.custo_antes * Decimal("100")).quantize(Decimal("0.01")))
                    if linha.custo_antes else None
                ),
                "delta_total": str(dinheiro(linha.delta_unitario * (linha.item_orcado.quantidade or Decimal("0")))),
                "data_base_antes": linha.data_base_antes,
                "data_base_depois": linha.data_base_depois,
                "selecionada": linha.selecionada,
                "aplicada": linha.aplicada,
                "descontinuado": linha.descontinuado,
                "motivo": linha.motivo,
            }
            for linha in linhas
        ],
    }


# ---------------------------------------------------------------------------
# O aviso que fica no orçamento, depois que o lote passou
# ---------------------------------------------------------------------------


def avisos_de_data_base(orcamento: Orcamento) -> dict:
    """Linhas cujo preço é mais velho que a data-base que a planilha anuncia.

    O lote avisa **no momento** da reprecificação; este aviso é o que sobra
    **depois**, e ele precisa existir porque é a planilha — não o lote — que vai
    para a licitação. Quem abrir o orçamento seis meses depois não vai atrás do
    histórico de lotes para descobrir que três linhas ficaram para trás.

    Derivado, não gravado: a comparação é `ItemOrcado.data_base_preco` contra
    `Orcamento.data_base`. Um campo "está desatualizada" gravado na linha seria
    uma terceira verdade para manter sincronizada com as outras duas, e
    dessincronizaria na primeira reprecificação parcial.

    Pega mais do que o item descontinuado — pega também a linha que o operador
    desmarcou na prévia, que é igualmente uma linha fora da data-base anunciada.
    Isso é de propósito: para a auditoria as duas são o mesmo defeito.
    """
    if orcamento.data_base is None:
        return {"tem_aviso": False, "data_base": None, "linhas_atrasadas": 0, "linhas": []}

    atrasadas = (
        ItemOrcado.objects
        .filter(
            orcamento=orcamento,
            tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
            data_base_preco__lt=orcamento.data_base,
        )
        .exclude(codigo_referencia="")
        .order_by("codigo_eap")
    )
    linhas = [
        {
            "item_orcado": item.pk,
            "codigo_eap": item.codigo_eap,
            "descricao": item.descricao,
            "codigo_referencia": item.codigo_referencia,
            "fonte_referencia": item.fonte_referencia,
            "custo_unitario": str(item.custo_unitario),
            "data_base_preco": item.data_base_preco,
        }
        for item in atrasadas
    ]
    return {
        "tem_aviso": bool(linhas),
        "data_base": orcamento.data_base,
        "linhas_atrasadas": len(linhas),
        "linhas": linhas,
        "mensagem": (
            f"{len(linhas)} linha(s) com preço anterior à data-base {orcamento.data_base:%m/%Y} "
            f"da planilha — item aposentado pela fonte ou não reprecificado. "
            f"O total não reflete a data-base anunciada."
        ) if linhas else "",
    }
