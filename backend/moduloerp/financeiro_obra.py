"""D.1.4 — financeiro por obra: de qual obra é cada real, e a DRE da obra.

**A atribuição.** Uma conta (a pagar ou a receber) chega à obra por dois
caminhos, e só por eles — nada é rateado por aproximação:

1. **Rateio por centro de custo com obra** (`CentroCusto.obra`): cada rateio
   leva à obra dele a fração `rateio.valor / conta.valor`.
2. **A obra da própria conta** (`conta.obra`): fica com o que o rateio não
   atribuiu — a conta inteira, se não houver rateio para obra.

A fração vale para tudo da conta: o valor (competência), o pago (caixa) e cada
`Transacao` de baixa (o mês em que o dinheiro saiu). Conta sem nenhum dos dois
caminhos não é de obra nenhuma, e a DRE diz quantas são em vez de chutá-las.

**De onde vem a obra sem ninguém digitar.** A medição e a liberação de retenção
do PDCA (contrato de obra) nascem com ela; a migration 0021 preencheu o que já
existia, inclusive o que veio de pedido de compra do SCM.

**As colunas da DRE** seguem o vocabulário das quatro colunas do Orçamento
(`moduloorcamento/controle.py`): *apropriado* é o custo lançado (competência),
*pago* é o que saiu do caixa — este é o *realizado* de lá.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q

from .models import ContaPagar, ContaReceber, StatusConta, Transacao

ZERO = Decimal("0")
UM = Decimal("1")
CENTAVO = Decimal("0.01")


def _q(valor: Decimal) -> Decimal:
    return (valor or ZERO).quantize(CENTAVO)


def fracoes(conta) -> list[tuple[int, int | None, Decimal]]:
    """`[(obra_id, etapa_id, fração)]` da conta. As frações somam no máximo 1.

    Lê `conta.rateios` já com `centro_custo` (prefetch do chamador)."""
    etapa = getattr(conta, "etapa_id", None)
    saida, atribuido = [], ZERO
    valor = conta.valor or ZERO
    if valor > 0:
        for rateio in conta.rateios.all():
            obra = rateio.centro_custo.obra_id
            if obra is None:
                continue
            fracao = min(UM, (rateio.valor or ZERO) / valor)
            # A etapa da conta só vale para a obra da conta.
            saida.append((obra, etapa if obra == conta.obra_id else None, fracao))
            atribuido += fracao
    if conta.obra_id and atribuido < UM:
        saida.append((conta.obra_id, etapa, UM - atribuido))
    return saida


def _contas(modelo, tenant_id, obra_id=None):
    filtro = Q(obra__isnull=False) | Q(rateios__centro_custo__obra__isnull=False)
    if obra_id:
        filtro = Q(obra_id=obra_id) | Q(rateios__centro_custo__obra_id=obra_id)
    return (
        modelo.objects.filter(filtro, tenant_id=tenant_id)
        .exclude(status=StatusConta.CANCELADO)
        .distinct()
        .prefetch_related("rateios__centro_custo")
    )


def _vazio():
    return {"valor": ZERO, "pago": ZERO, "contas": 0}


def por_obra(tenant_id, obra_id=None) -> dict[int, dict]:
    """Despesa e receita atribuídas a cada obra: `{obra: {"despesa", "receita",
    "despesa_por_etapa"}}`, cada uma com `valor` (competência) e `pago` (caixa)."""
    saida: dict[int, dict] = defaultdict(lambda: {
        "despesa": _vazio(), "receita": _vazio(), "despesa_por_etapa": defaultdict(_vazio),
    })
    for lado, modelo in (("despesa", ContaPagar), ("receita", ContaReceber)):
        for conta in _contas(modelo, tenant_id, obra_id):
            for obra, etapa, fracao in fracoes(conta):
                if obra_id and obra != int(obra_id):
                    continue
                alvo = saida[obra][lado]
                alvo["valor"] += (conta.valor or ZERO) * fracao
                alvo["pago"] += (conta.valor_pago or ZERO) * fracao
                alvo["contas"] += 1
                if lado == "despesa":
                    linha = saida[obra]["despesa_por_etapa"][etapa]
                    linha["valor"] += (conta.valor or ZERO) * fracao
                    linha["pago"] += (conta.valor_pago or ZERO) * fracao
                    linha["contas"] += 1
    return saida


def realizado_por_obra(tenant_id, obra_id=None) -> dict[int, Decimal]:
    """O que saiu do caixa por obra — a coluna *realizado* do Orçamento."""
    return {obra: dados["despesa"]["pago"] for obra, dados in por_obra(tenant_id, obra_id).items()}


def _mensal(tenant_id, obra_id) -> list[dict]:
    """Entradas e saídas de caixa da obra, mês a mês, pelas `Transacao` das
    contas atribuídas (com a mesma fração)."""
    meses: dict = defaultdict(lambda: {"entradas": ZERO, "saidas": ZERO})
    for lado, modelo, campo in (
        ("saidas", ContaPagar, "conta_pagar_id"), ("entradas", ContaReceber, "conta_receber_id"),
    ):
        fracao_da_conta = {}
        for conta in _contas(modelo, tenant_id, obra_id):
            fracao = sum((f for o, _, f in fracoes(conta) if o == int(obra_id)), ZERO)
            if fracao:
                fracao_da_conta[conta.pk] = fracao
        if not fracao_da_conta:
            continue
        transacoes = Transacao.objects.filter(
            tenant_id=tenant_id, **{f"{campo}__in": list(fracao_da_conta)},
        ).values_list(campo, "valor", "data_transacao")
        for conta_id, valor, quando in transacoes:
            mes = quando.date().replace(day=1)
            meses[mes][lado] += (valor or ZERO) * fracao_da_conta[conta_id]
    acumulado, linhas = ZERO, []
    for mes in sorted(meses):
        entradas, saidas = meses[mes]["entradas"], meses[mes]["saidas"]
        acumulado += entradas - saidas
        linhas.append({
            "mes": mes.isoformat(), "entradas": str(_q(entradas)), "saidas": str(_q(saidas)),
            "saldo_acumulado": str(_q(acumulado)),
        })
    return linhas


def _orcado(tenant_id, obra_id):
    """A régua do Orçamento (aprovado vigente), ou `None` sem ela."""
    from moduloorcamento.planilha import orcado_por_etapa, orcamento_vigente

    vigente = orcamento_vigente(tenant_id, obra_id)
    if vigente is None:
        return None, {}
    por_etapa = {etapa: v for (obra, etapa), v in orcado_por_etapa(tenant_id, obra_id).items() if obra == int(obra_id)}
    return vigente, por_etapa


def dre(tenant_id, obra, *, com_orcado: bool) -> dict:
    """A DRE gerencial da obra: receita × custo, por competência e por caixa,
    o custo por etapa contra o orçado e o caixa mês a mês."""
    from obras.models import EtapaObra

    dados = por_obra(tenant_id, obra.pk).get(obra.pk) or {
        "despesa": _vazio(), "receita": _vazio(), "despesa_por_etapa": {},
    }
    receita, despesa = dados["receita"], dados["despesa"]
    vigente, orcado_etapa = _orcado(tenant_id, obra.pk) if com_orcado else (None, {})

    etapas = {e.pk: e for e in EtapaObra.objects.filter(tenant_id=tenant_id, obra=obra).order_by("ordem")}
    ids = list(etapas) + [e for e in dados["despesa_por_etapa"] if e not in etapas] + (
        [None] if None in dados["despesa_por_etapa"] or None in orcado_etapa else []
    )
    por_etapa = []
    for etapa_id in dict.fromkeys(ids):
        gasto = dados["despesa_por_etapa"].get(etapa_id) or _vazio()
        orc = orcado_etapa.get(etapa_id)
        if not gasto["contas"] and orc is None:
            continue
        orcado = orc["orcado"] if orc else None
        por_etapa.append({
            "etapa": etapa_id,
            "etapa_nome": etapas[etapa_id].nome_etapa if etapa_id in etapas else "Sem etapa",
            "orcado": str(_q(orcado)) if orcado is not None else None,
            "apropriado": str(_q(gasto["valor"])),
            "pago": str(_q(gasto["pago"])),
            "consumido_pct": (
                str((gasto["valor"] / orcado * 100).quantize(CENTAVO)) if orcado else None
            ),
        })

    resultado_competencia = receita["valor"] - despesa["valor"]
    return {
        "obra": obra.pk,
        "obra_nome": obra.nome_obra,
        "empreendimento": obra.empreendimento_id,
        "receita": {
            "faturado": str(_q(receita["valor"])), "recebido": str(_q(receita["pago"])),
            "a_receber": str(_q(receita["valor"] - receita["pago"])), "contas": receita["contas"],
        },
        "custo": {
            "apropriado": str(_q(despesa["valor"])), "pago": str(_q(despesa["pago"])),
            "a_pagar": str(_q(despesa["valor"] - despesa["pago"])), "contas": despesa["contas"],
        },
        "resultado": {
            "competencia": str(_q(resultado_competencia)),
            "caixa": str(_q(receita["pago"] - despesa["pago"])),
            "margem_pct": (
                str((resultado_competencia / receita["valor"] * 100).quantize(CENTAVO))
                if receita["valor"] else None
            ),
        },
        # `None` (e não zero) sem régua aprovada ou sem o módulo: zero se
        # leria como "estourou 100%" — mesma regra das quatro colunas.
        "orcado": (
            {"custo_direto": str(vigente.custo_direto_total), "com_bdi": str(vigente.valor_total),
             "orcamento": vigente.pk, "versao": vigente.versao}
            if vigente else None
        ),
        "por_etapa": por_etapa,
        "mensal": _mensal(tenant_id, obra.pk),
    }


def resumo_das_obras(tenant_id) -> list[dict]:
    """Uma linha por obra com movimento financeiro — a lista da página."""
    from obras.models import Obra

    dados = por_obra(tenant_id)
    nomes = dict(Obra.objects.filter(tenant_id=tenant_id, pk__in=list(dados)).values_list("pk", "nome_obra"))
    linhas = []
    for obra_id, d in dados.items():
        if obra_id not in nomes:
            continue
        linhas.append({
            "obra": obra_id, "obra_nome": nomes[obra_id],
            "receita": str(_q(d["receita"]["valor"])), "recebido": str(_q(d["receita"]["pago"])),
            "custo": str(_q(d["despesa"]["valor"])), "pago": str(_q(d["despesa"]["pago"])),
            "resultado": str(_q(d["receita"]["valor"] - d["despesa"]["valor"])),
        })
    return sorted(linhas, key=lambda l: l["obra_nome"])
