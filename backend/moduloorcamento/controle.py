# backend/moduloorcamento/controle.py
"""ORC.3 — controle de custo: quatro colunas e cronograma físico-financeiro.

**As quatro colunas** são a leitura que separa um sistema de gestão de uma
planilha de orçamento. A mesma obra, vista por quatro lentes que respondem
perguntas diferentes:

| Coluna           | Pergunta                                | Fonte              |
|------------------|-----------------------------------------|--------------------|
| **Orçado**       | quanto eu planejei gastar?              | Orçamento aprovado |
| **Comprometido** | quanto eu já me obriguei a pagar?       | Pedidos do SCM     |
| **Aplicado**     | quanto já virou obra de fato?           | Saídas do SIL      |
| **Realizado**    | quanto já saiu do caixa?                | Baixas do ERP      |

Elas **não se somam** — são quatro ângulos sobre o mesmo dinheiro, e é a
distância entre elas que informa: comprometido acima do orçado é estouro
contratado antes de acontecer; aplicado muito acima do realizado é passivo a
pagar; realizado acima do aplicado é adiantamento a fornecedor.

**A curva S** é a mesma leitura no tempo: o previsto acumulado do cronograma
contra o que efetivamente aconteceu, mês a mês. O nome vem do formato — obra
começa devagar, acelera no miolo e desacelera no acabamento.

### Limite honesto da coluna "realizado"

O `moduloerp` amarra despesa a **empreendimento**, não a obra: `ContaPagar` tem
FK de empreendimento e o `CentroCusto` do ERP também. O único caminho preciso
até a obra hoje é pelo SCM — `PedidoCompra.conta_pagar_ref` → `ContaPagar`, com
a obra vindo do centro de custo do pedido.

Então **realizado cobre o que passou por pedido de compra**. Despesa lançada
direto no ERP (medição de empreiteiro, conta de energia do canteiro) ainda não
tem dimensão de obra, e por isso não entra — em vez de ser rateada por
aproximação. A resposta traz `realizado_cobertura` dizendo isso, para a tela
não apresentar um número parcial como se fosse total. Fechar essa lacuna é a
fatia **D.1.4** do ERP (financeiro por obra).
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth

from .models import ItemOrcado, Orcamento, ParcelaEtapa
from .planilha import dinheiro, orcamento_vigente

CEM = Decimal("100")
DEC = DecimalField(max_digits=20, decimal_places=4)
ZERO = Decimal("0")


class CronogramaInvalido(Exception):
    """Distribuição que não fecha 100% ou período impossível."""


# ---------------------------------------------------------------------------
# As quatro colunas
# ---------------------------------------------------------------------------


def _comprometido_por_obra(tenant_id, obra_id=None) -> dict[int, Decimal]:
    """Valor de pedidos de compra atribuídos à obra pelo centro de custo.

    Rascunho não conta (é intenção, não compromisso) e cancelado também não
    (o compromisso foi desfeito). O que sobra é dinheiro que a empresa já se
    obrigou a pagar, mesmo que a nota ainda não tenha chegado.
    """
    from moduloscm.models import PedidoCompra

    qs = (
        PedidoCompra.objects.filter(
            tenant_id=tenant_id, centro_custo__obra__isnull=False,
        )
        .exclude(status__in=[PedidoCompra.Status.RASCUNHO, PedidoCompra.Status.CANCELADO])
    )
    if obra_id:
        qs = qs.filter(centro_custo__obra_id=obra_id)

    linhas = qs.values("centro_custo__obra_id").annotate(
        total=Coalesce(Sum("valor_total", output_field=DEC), ZERO, output_field=DEC)
    )
    return {linha["centro_custo__obra_id"]: linha["total"] for linha in linhas}


def _aplicado_por_obra(tenant_id, obra_id=None) -> dict[int, Decimal]:
    """Material consumido, valorizado pelo custo da saída (mesma conta do SIL)."""
    from modulosil.models import MovimentacaoEstoque

    qs = MovimentacaoEstoque.objects.filter(
        tenant_id=tenant_id, tipo=MovimentacaoEstoque.Tipo.SAIDA, obra__isnull=False,
    )
    if obra_id:
        qs = qs.filter(obra_id=obra_id)

    linhas = qs.values("obra_id").annotate(
        total=Coalesce(
            Sum(F("quantidade") * F("custo_unitario"), output_field=DEC), ZERO, output_field=DEC
        )
    )
    return {linha["obra_id"]: linha["total"] for linha in linhas}


def _realizado_por_obra(tenant_id, obra_id=None) -> dict[int, Decimal]:
    """Dinheiro que saiu do caixa, pelo caminho SCM → ERP.

    Ver a nota sobre cobertura no topo do módulo: só entra despesa que nasceu
    de pedido de compra, porque é o único vínculo preciso com a obra hoje.
    """
    from moduloerp.models import ContaPagar
    from moduloscm.models import PedidoCompra

    pedidos = PedidoCompra.objects.filter(
        tenant_id=tenant_id, centro_custo__obra__isnull=False, conta_pagar_ref__isnull=False,
    ).exclude(status=PedidoCompra.Status.CANCELADO)
    if obra_id:
        pedidos = pedidos.filter(centro_custo__obra_id=obra_id)

    por_conta = dict(pedidos.values_list("conta_pagar_ref", "centro_custo__obra_id"))
    if not por_conta:
        return {}

    pagos = ContaPagar.objects.filter(
        tenant_id=tenant_id, pk__in=list(por_conta.keys())
    ).values_list("pk", "valor_pago")

    realizado: dict[int, Decimal] = {}
    for conta_id, valor_pago in pagos:
        obra = por_conta.get(conta_id)
        if obra is not None:
            realizado[obra] = realizado.get(obra, ZERO) + (valor_pago or ZERO)
    return realizado


def quatro_colunas(tenant_id, obra_id=None) -> list[dict]:
    """Orçado × comprometido × aplicado × realizado, por obra.

    O `orcado` sai do orçamento **aprovado vigente** de cada obra; obra sem
    régua aprovada aparece com `orcado: None` (e não zero), pelo mesmo motivo
    do seam do SIL: um zero se leria como "estourou 100%".
    """
    from obras.models import Obra

    obras = Obra.objects.filter(tenant_id=tenant_id)
    if obra_id:
        obras = obras.filter(pk=obra_id)

    comprometido = _comprometido_por_obra(tenant_id, obra_id)
    aplicado = _aplicado_por_obra(tenant_id, obra_id)
    realizado = _realizado_por_obra(tenant_id, obra_id)

    linhas = []
    for obra in obras.only("obra_id", "nome_obra"):
        vigente = orcamento_vigente(tenant_id, obra.pk)
        orcado = vigente.custo_direto_total if vigente else None
        comp = comprometido.get(obra.pk, ZERO)
        apl = aplicado.get(obra.pk, ZERO)
        real = realizado.get(obra.pk, ZERO)

        linhas.append({
            "obra": obra.pk,
            "obra_nome": obra.nome_obra,
            "orcamento": vigente.pk if vigente else None,
            "orcamento_versao": vigente.versao if vigente else None,
            "orcado": str(orcado) if orcado is not None else None,
            "orcado_com_bdi": str(vigente.valor_total) if vigente else None,
            "comprometido": str(dinheiro(comp)),
            "aplicado": str(dinheiro(apl)),
            "realizado": str(dinheiro(real)),
            # Saldo é contra o COMPROMETIDO, não contra o aplicado: o que já foi
            # pedido é dinheiro que não está mais disponível, ainda que a nota
            # não tenha chegado. É o número que evita comprar duas vezes o mesmo.
            "saldo": str(dinheiro(orcado - comp)) if orcado is not None else None,
            "consumido_pct": (
                str((comp / orcado * CEM).quantize(Decimal("0.01")))
                if orcado and orcado > 0 else None
            ),
            "estourado": bool(orcado is not None and comp > orcado),
            "realizado_cobertura": "pedidos_de_compra",
        })
    return linhas


# ---------------------------------------------------------------------------
# Cronograma físico-financeiro e curva S
# ---------------------------------------------------------------------------


def _competencias(inicio, fim) -> list:
    """Meses de `inicio` a `fim`, inclusive, sempre no dia 1."""
    from datetime import date

    if fim < inicio:
        raise CronogramaInvalido("A data final é anterior à inicial.")
    meses, ano, mes = [], inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        meses.append(date(ano, mes, 1))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


@transaction.atomic
def distribuir_linear(orcamento: Orcamento, *, inicio, fim, etapa=None) -> list[ParcelaEtapa]:
    """Cronograma de partida: distribui o valor igualmente pelos meses.

    Distribuição linear não é a verdade de nenhuma obra — é o **ponto de
    partida editável**, que é como as ferramentas do mercado funcionam: gera-se
    o linear e o planejador ajusta. A alternativa (obrigar a digitar mês a mês
    numa obra de 24 meses) faz a funcionalidade não ser usada.

    O resíduo da divisão vai no **último mês**, para a soma fechar exatamente
    100% — sem isso, 100/3 deixaria 0,01% de sobra e o total do cronograma não
    bateria com o do orçamento.
    """
    meses = _competencias(inicio, fim)
    quantidade = len(meses)
    percentual = (CEM / quantidade).quantize(Decimal("0.0001"))
    ultimo = CEM - percentual * (quantidade - 1)

    base = ParcelaEtapa.objects.filter(orcamento=orcamento, etapa=etapa)
    base.delete()

    parcelas = [
        ParcelaEtapa(
            tenant_id=orcamento.tenant_id, orcamento=orcamento, etapa=etapa,
            competencia=mes,
            percentual=(ultimo if i == quantidade - 1 else percentual),
        )
        for i, mes in enumerate(meses)
    ]
    ParcelaEtapa.objects.bulk_create(parcelas)
    return recalcular_parcelas(orcamento)


@transaction.atomic
def recalcular_parcelas(orcamento: Orcamento) -> list[ParcelaEtapa]:
    """Converte os percentuais em dinheiro, usando o valor de cada etapa.

    Parcela sem etapa distribui o orçamento inteiro; com etapa, distribui só o
    que está orçado naquela etapa — que é o que permite o cronograma refletir a
    obra real (fundação nos primeiros meses, acabamento nos últimos).
    """
    por_etapa = {
        linha["etapa_id"]: linha["total"]
        for linha in ItemOrcado.objects.filter(
            orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO
        ).values("etapa_id").annotate(
            total=Coalesce(Sum("total_com_bdi", output_field=DEC), ZERO, output_field=DEC)
        )
    }
    total_geral = orcamento.valor_total

    parcelas = list(ParcelaEtapa.objects.filter(orcamento=orcamento))
    for parcela in parcelas:
        base = total_geral if parcela.etapa_id is None else por_etapa.get(parcela.etapa_id, ZERO)
        parcela.valor_previsto = dinheiro(base * parcela.percentual / CEM)
    if parcelas:
        ParcelaEtapa.objects.bulk_update(parcelas, ["valor_previsto"], batch_size=500)
    return parcelas


def curva_s(orcamento: Orcamento) -> dict:
    """Previsto acumulado × realizado acumulado, mês a mês.

    O lado realizado vem do **consumo físico** (saídas do SIL da obra), que é o
    que tem data confiável de quando aconteceu. Usar a baixa financeira daria
    uma curva deslocada pelo prazo de pagamento — mostraria a obra atrasada
    quando na verdade é o fornecedor que fatura em 30 dias.

    Meses em que houve consumo mas não havia parcela prevista **aparecem** na
    série, com previsto zero: são exatamente os desvios que a curva existe para
    revelar.
    """
    from modulosil.models import MovimentacaoEstoque

    parcelas = (
        ParcelaEtapa.objects.filter(orcamento=orcamento)
        .values("competencia")
        .annotate(previsto=Coalesce(Sum("valor_previsto", output_field=DEC), ZERO, output_field=DEC))
        .order_by("competencia")
    )
    previsto_por_mes = {p["competencia"]: p["previsto"] for p in parcelas}

    consumo = (
        MovimentacaoEstoque.objects.filter(
            tenant_id=orcamento.tenant_id, obra_id=orcamento.obra_id,
            tipo=MovimentacaoEstoque.Tipo.SAIDA,
        )
        .annotate(mes=TruncMonth("criado_em"))
        .values("mes")
        .annotate(
            real=Coalesce(
                Sum(F("quantidade") * F("custo_unitario"), output_field=DEC), ZERO, output_field=DEC
            )
        )
        .order_by("mes")
    )
    real_por_mes = {
        (linha["mes"].date() if hasattr(linha["mes"], "date") else linha["mes"]).replace(day=1): linha["real"]
        for linha in consumo
        if linha["mes"] is not None
    }

    meses = sorted(set(previsto_por_mes) | set(real_por_mes))
    total_previsto = sum(previsto_por_mes.values(), ZERO)

    serie, acumulado_previsto, acumulado_real = [], ZERO, ZERO
    for mes in meses:
        previsto = previsto_por_mes.get(mes, ZERO)
        real = real_por_mes.get(mes, ZERO)
        acumulado_previsto += previsto
        acumulado_real += real
        serie.append({
            "competencia": mes,
            "previsto": str(dinheiro(previsto)),
            "previsto_acumulado": str(dinheiro(acumulado_previsto)),
            "previsto_pct_acumulado": (
                str((acumulado_previsto / total_previsto * CEM).quantize(Decimal("0.01")))
                if total_previsto > 0 else "0"
            ),
            "realizado": str(dinheiro(real)),
            "realizado_acumulado": str(dinheiro(acumulado_real)),
            "realizado_pct_acumulado": (
                str((acumulado_real / total_previsto * CEM).quantize(Decimal("0.01")))
                if total_previsto > 0 else "0"
            ),
            "desvio_acumulado": str(dinheiro(acumulado_real - acumulado_previsto)),
        })

    return {
        "orcamento": orcamento.pk,
        "obra": orcamento.obra_id,
        "total_previsto": str(dinheiro(total_previsto)),
        "total_realizado": str(dinheiro(acumulado_real)),
        "fonte_realizado": "consumo_fisico_sil",
        "serie": serie,
    }


def cronograma(orcamento: Orcamento) -> dict:
    """A grade do cronograma: linhas = etapas, colunas = meses.

    Formato pensado para a tela renderizar direto, sem ela precisar pivotar —
    é a mesma grade que o orçamentista conhece do Excel.
    """
    parcelas = list(
        ParcelaEtapa.objects.filter(orcamento=orcamento)
        .select_related("etapa")
        .order_by("etapa__ordem", "competencia")
    )
    meses = sorted({p.competencia for p in parcelas})

    por_etapa: dict = {}
    for parcela in parcelas:
        chave = parcela.etapa_id
        linha = por_etapa.setdefault(chave, {
            "etapa": chave,
            "etapa_nome": parcela.etapa.nome_etapa if parcela.etapa else "— orçamento inteiro —",
            "parcelas": {},
            "total": ZERO,
        })
        linha["parcelas"][parcela.competencia.isoformat()] = {
            "parcela_id": parcela.parcela_id,
            "percentual": str(parcela.percentual),
            "valor_previsto": str(parcela.valor_previsto),
        }
        linha["total"] += parcela.valor_previsto

    return {
        "orcamento": orcamento.pk,
        "competencias": [mes.isoformat() for mes in meses],
        "linhas": [
            {**linha, "total": str(dinheiro(linha["total"]))}
            for linha in sorted(por_etapa.values(), key=lambda l: (l["etapa"] is not None, l["etapa"] or 0))
        ],
        "total": str(dinheiro(sum((p.valor_previsto for p in parcelas), ZERO))),
    }


def validar_cronograma(orcamento: Orcamento) -> dict:
    """Confere se cada etapa distribuída soma 100%.

    Não bloqueia — informa. Um cronograma em construção passa por estados
    inconsistentes, e travar a digitação em 100% obrigaria o planejador a
    acertar tudo de uma vez.
    """
    somas = (
        ParcelaEtapa.objects.filter(orcamento=orcamento)
        .values("etapa_id")
        .annotate(soma=Coalesce(Sum("percentual"), ZERO))
    )
    problemas = [
        {
            "etapa": linha["etapa_id"],
            "soma_percentual": str(linha["soma"]),
            "diferenca": str(CEM - linha["soma"]),
        }
        for linha in somas
        if linha["soma"] != CEM
    ]
    return {"consistente": not problemas, "problemas": problemas}


# ---------------------------------------------------------------------------
# ORC.7 — desembolso na granularidade do insumo
# ---------------------------------------------------------------------------


def desembolso_por_insumo(orcamento: Orcamento, *, categoria: str | None = None) -> dict:
    """Quanto de **cada insumo** cai em cada mês — o cronograma que o suprimento usa.

    O cronograma por etapa responde ao financeiro ("quanto sai em setembro?") e
    não responde a quem compra ("quantas toneladas de aço preciso ter em obra em
    setembro?"). São perguntas diferentes e a segunda é a que evita tanto a
    parada por falta quanto o pátio cheio de material parado — que é dinheiro
    imobilizado e é o que a curva de desembolso por insumo torna visível.

    **A distribuição é herdada, não inventada.** O insumo cai nas competências da
    **etapa da linha em que ele aparece**, na mesma proporção que o planejador já
    distribuiu em `ParcelaEtapa`. Um insumo que entra em três serviços de duas
    etapas diferentes é rateado por cada uma na proporção do valor que tem lá —
    inventar uma curva própria por insumo seria fabricar planejamento que
    ninguém fez, e o módulo não fabrica dado.

    Linha sem etapa e etapa sem cronograma ficam **fora** da grade e são
    devolvidas em `sem_distribuicao`: somá-las no primeiro mês encheria setembro
    de compra que ninguém planejou para setembro.
    """
    from .models import ItemOrcadoInsumo

    percentuais: dict[int | None, list[tuple]] = {}
    for parcela in ParcelaEtapa.objects.filter(orcamento=orcamento):
        percentuais.setdefault(parcela.etapa_id, []).append(
            (parcela.competencia, parcela.percentual)
        )

    consulta = ItemOrcadoInsumo.objects.filter(item_orcado__orcamento=orcamento)
    if categoria:
        consulta = consulta.filter(categoria=categoria)

    linhas = consulta.values(
        "item_id", "descricao", "unidade", "categoria", "item_orcado__etapa_id",
    ).annotate(
        quantidade=Coalesce(
            Sum(ExpressionWrapper(
                F("coeficiente") * F("item_orcado__quantidade"),
                output_field=DecimalField(max_digits=24, decimal_places=6),
            )),
            ZERO,
        ),
        valor=Coalesce(
            Sum(ExpressionWrapper(
                F("custo_no_item") * F("item_orcado__quantidade"),
                output_field=DecimalField(max_digits=24, decimal_places=4),
            )),
            ZERO,
        ),
    )

    grade: dict[tuple, dict] = {}
    sem_distribuicao: dict[tuple, dict] = {}
    competencias: set = set()

    for linha in linhas:
        chave = (linha["item_id"], linha["descricao"], linha["unidade"])
        etapa_id = linha["item_orcado__etapa_id"]
        fatias = percentuais.get(etapa_id) or percentuais.get(None)

        destino = grade if fatias else sem_distribuicao
        registro = destino.setdefault(chave, {
            "item": linha["item_id"],
            "descricao": linha["descricao"],
            "unidade": linha["unidade"],
            "categoria": linha["categoria"],
            "quantidade_total": ZERO,
            "valor_total": ZERO,
            "meses": {},
        })
        registro["quantidade_total"] += linha["quantidade"]
        registro["valor_total"] += linha["valor"]

        if not fatias:
            continue
        for competencia, percentual in fatias:
            competencias.add(competencia)
            fracao = percentual / CEM
            mes = registro["meses"].setdefault(
                competencia.isoformat(), {"quantidade": ZERO, "valor": ZERO}
            )
            mes["quantidade"] += linha["quantidade"] * fracao
            mes["valor"] += linha["valor"] * fracao

    def formatar(registros: dict) -> list[dict]:
        saida = []
        for registro in sorted(registros.values(), key=lambda r: r["valor_total"], reverse=True):
            saida.append({
                **registro,
                "quantidade_total": str(registro["quantidade_total"].quantize(Decimal("0.0001"))),
                "valor_total": str(dinheiro(registro["valor_total"])),
                "meses": {
                    mes: {
                        "quantidade": str(v["quantidade"].quantize(Decimal("0.0001"))),
                        "valor": str(dinheiro(v["valor"])),
                    }
                    for mes, v in sorted(registro["meses"].items())
                },
            })
        return saida

    return {
        "orcamento": orcamento.pk,
        "filtro_categoria": categoria or "",
        "competencias": sorted(mes.isoformat() for mes in competencias),
        "insumos": formatar(grade),
        "sem_distribuicao": formatar(sem_distribuicao),
        "nota_sem_distribuicao": (
            "Insumos de linhas cuja etapa não tem cronograma distribuído. Ficam fora "
            "da grade de propósito — jogá-los no primeiro mês fabricaria compra que "
            "ninguém planejou."
        ) if sem_distribuicao else "",
    }
