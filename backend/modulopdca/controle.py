# backend/modulopdca/controle.py
"""O **controle** da obra: o dinheiro e o material contra o plano.

*Decisão do dono, 10/10/2026:* controlar é execução, e execução é do PDCA. O
Orçamento planeja (a planilha, o cronograma físico-financeiro por etapa); aqui
se lê quanto a obra já se obrigou a pagar, quanto já virou obra, quanto saiu do
caixa — e, com o avanço apontado, **para onde o custo final está indo**.

### As colunas

| Coluna           | Pergunta                                 | Fonte                          |
|------------------|------------------------------------------|--------------------------------|
| **Orçado**       | quanto se planejou gastar?               | orçamento aprovado (custo direto) |
| **Comprometido** | quanto a empresa já se obrigou a pagar?  | pedidos do SCM + contratos de empreiteiro (lado custo) |
| **Aplicado**     | quanto material já virou obra?           | saídas do SIL (menos devoluções) |
| **Medido**       | quanto serviço de empreiteiro foi aceito?| medições aprovadas              |
| **Realizado**    | quanto já saiu do caixa?                 | baixas do ERP                  |

Elas **não se somam**. O contrato de empreiteiro que tem pedido de serviço no
Suprimentos já está no pedido — somar o contrato de novo contaria duas vezes,
então só entra o contrato **sem** pedido ligado.

### Valor agregado (a projeção)

O custo real até aqui (**CR**) é o que já se **incorreu**: material aplicado +
serviço medido. Com o avanço físico do plano vigente:

    ONT = orçado            VP = % previsto × ONT        VA = % realizado × ONT
    IDC = VA ÷ CR           IDP = VA ÷ VP
    custo a incorrer = (ONT − VA) ÷ IDC        ENT = CR + custo a incorrer
    VNT = ONT − ENT         (negativo = a obra vai estourar)

Sem avanço apontado ou sem custo incorrido, os índices ficam **nulos** — um
IDC de 1,00 inventado diria que está tudo no orçamento sem saber.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

ZERO = Decimal("0")
CEM = Decimal("100")
DEC = DecimalField(max_digits=20, decimal_places=4)


def _d(valor: Decimal | None, casas: str = "0.01") -> str | None:
    return None if valor is None else str(valor.quantize(Decimal(casas)))


def _razao(a: Decimal, b: Decimal) -> Decimal | None:
    return (a / b) if b and b > 0 else None


# ---------------------------------------------------------------------------
# As colunas — cada uma da sua fonte
# ---------------------------------------------------------------------------


def comprometido_em_pedidos(tenant_id, obra_id) -> Decimal:
    """Pedidos do centro de custo da obra — rascunho é intenção, cancelado foi desfeito."""
    from moduloscm.models import PedidoCompra

    return (
        PedidoCompra.objects.filter(tenant_id=tenant_id, centro_custo__obra_id=obra_id)
        .exclude(status__in=[PedidoCompra.Status.RASCUNHO, PedidoCompra.Status.CANCELADO])
        .aggregate(t=Coalesce(Sum("valor_total", output_field=DEC), ZERO, output_field=DEC))["t"]
    )


def contratos_comprometidos(tenant_id, obra_id) -> list[dict]:
    """Contratos de empreiteiro em vigor (ou encerrados), pelo valor de hoje.

    `conta` diz se o contrato entra no comprometido: o que tem pedido de serviço
    no Suprimentos já está contado no pedido. **Só o lado custo**: o contrato com
    o contratante (`receita`) é o que a obra vai receber, não o que ela deve.
    """
    from . import services
    from .models import ContratoObra, LadoContrato

    saida = []
    for contrato in (ContratoObra.objects
                     .filter(tenant_id=tenant_id, obra_id=obra_id, lado=LadoContrato.CUSTO,
                             status__in=[ContratoObra.Status.VIGENTE, ContratoObra.Status.SUSPENSO,
                                         ContratoObra.Status.ENCERRADO])
                     .select_related("fornecedor").prefetch_related("itens")):
        saida.append({
            "contrato": contrato.pk, "numero": contrato.numero,
            "fornecedor": getattr(contrato.fornecedor, "razao_social", ""),
            "status": contrato.status,
            "valor": services.valor_contratado(contrato),
            "conta": contrato.pedido_scm_id is None,
        })
    return saida


def aplicado_por_etapa(tenant_id, obra_id) -> dict[int | None, Decimal]:
    """Material que saiu para a obra, a custo, menos o que voltou."""
    from modulosil.models import MovimentacaoEstoque

    saida: dict[int | None, Decimal] = defaultdict(lambda: ZERO)
    for etapa_id, tipo, qtd, custo in MovimentacaoEstoque.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
        tipo__in=(MovimentacaoEstoque.Tipo.SAIDA, MovimentacaoEstoque.Tipo.DEVOLUCAO),
    ).values_list("etapa_id", "tipo", "quantidade", "custo_unitario"):
        valor = abs(qtd or ZERO) * (custo or ZERO)
        saida[etapa_id] += -valor if tipo == MovimentacaoEstoque.Tipo.DEVOLUCAO else valor
    return saida


def medido_por_etapa(tenant_id, obra_id) -> dict[int | None, Decimal]:
    """Serviço medido e aprovado, na etapa do item de contrato (pela atividade
    ou, sem ela, pelo item orçado). Só a do empreiteiro: medir o contrato de
    receita é faturar ao contratante, não incorrer custo."""
    from .models import ItemMedicao, LadoContrato, Medicao

    saida: dict[int | None, Decimal] = defaultdict(lambda: ZERO)
    for etapa_ativ, etapa_item, qtd, preco in ItemMedicao.objects.filter(
        tenant_id=tenant_id, medicao__status=Medicao.Status.APROVADA,
        medicao__contrato__obra_id=obra_id, medicao__contrato__lado=LadoContrato.CUSTO,
    ).values_list("item_contrato__atividade__etapa_id", "item_contrato__item_orcado__etapa_id",
                  "quantidade", "preco_unitario"):
        saida[etapa_ativ or etapa_item] += (qtd or ZERO) * (preco or ZERO)
    return saida


def realizado(tenant_id, obra_id) -> Decimal:
    """Dinheiro que saiu do caixa, pela dimensão de obra do ERP (D.1.4), mais o
    caminho antigo — pedido do SCM cuja conta ainda não tem obra."""
    from moduloerp.financeiro_obra import realizado_por_obra
    from moduloerp.models import ContaPagar
    from moduloscm.models import PedidoCompra

    total = realizado_por_obra(tenant_id, obra_id).get(obra_id, ZERO)
    contas = list(
        PedidoCompra.objects.filter(
            tenant_id=tenant_id, centro_custo__obra_id=obra_id, conta_pagar_ref__isnull=False,
        ).exclude(status=PedidoCompra.Status.CANCELADO).values_list("conta_pagar_ref", flat=True)
    )
    if contas:
        total += ContaPagar.objects.filter(
            tenant_id=tenant_id, pk__in=contas, obra__isnull=True,
        ).exclude(rateios__centro_custo__obra__isnull=False).aggregate(
            t=Coalesce(Sum("valor_pago", output_field=DEC), ZERO, output_field=DEC)
        )["t"]
    return total


# ---------------------------------------------------------------------------
# O plano de referência
# ---------------------------------------------------------------------------


def plano_da_obra(tenant_id, obra_id):
    """O vigente; sem ele, o rascunho mais recente — e a resposta diz qual."""
    from .models import Cronograma

    base = Cronograma.objects.filter(tenant_id=tenant_id, obra_id=obra_id, eh_modelo=False)
    return (base.filter(status=Cronograma.Status.VIGENTE).first()
            or base.exclude(status=Cronograma.Status.SUBSTITUIDO).order_by("-versao").first())


# ---------------------------------------------------------------------------
# Custo da obra
# ---------------------------------------------------------------------------


def _valor_agregado(ont: Decimal, previsto_pct, realizado_pct, cr: Decimal) -> dict:
    if previsto_pct is None or realizado_pct is None or ont <= 0:
        return {"vp": None, "va": None, "cr": _d(cr), "idc": None, "idp": None,
                "a_incorrer": None, "ent": None, "vnt": None}
    vp = ont * Decimal(str(previsto_pct)) / CEM
    va = ont * Decimal(str(realizado_pct)) / CEM
    idc = _razao(va, cr)
    idp = _razao(va, vp)
    a_incorrer = ((ont - va) / idc) if idc else None
    ent = (cr + a_incorrer) if a_incorrer is not None else None
    return {
        "vp": _d(vp), "va": _d(va), "cr": _d(cr),
        "idc": _d(idc, "0.001"), "idp": _d(idp, "0.001"),
        "a_incorrer": _d(a_incorrer), "ent": _d(ent),
        "vnt": _d(ont - ent) if ent is not None else None,
    }


def custo_da_obra(*, obra, tenant_id: int, hoje: date | None = None) -> dict:
    """As colunas da obra, o valor agregado da obra e o de cada etapa."""
    from moduloorcamento.planilha import orcado_por_etapa, orcamento_vigente
    from obras.models import EtapaObra

    from . import services

    hoje = hoje or timezone.localdate()
    obra_id = obra.pk
    vigente = orcamento_vigente(tenant_id, obra_id)
    orcado_etapa = {etapa: v["orcado"] or ZERO
                    for (o, etapa), v in orcado_por_etapa(tenant_id, obra_id).items() if o == obra_id}
    aplicado = aplicado_por_etapa(tenant_id, obra_id)
    medido = medido_por_etapa(tenant_id, obra_id)
    contratos = contratos_comprometidos(tenant_id, obra_id)
    pedidos = comprometido_em_pedidos(tenant_id, obra_id)
    em_contratos = sum((c["valor"] for c in contratos if c["conta"]), ZERO)

    orcado = vigente.custo_direto_total if vigente else None
    total_aplicado = sum(aplicado.values(), ZERO)
    total_medido = sum(medido.values(), ZERO)
    comprometido = pedidos + em_contratos
    incorrido = total_aplicado + total_medido

    plano = plano_da_obra(tenant_id, obra_id)
    avanco = services.avanco_fisico_financeiro(plano, hoje=hoje) if plano else None
    por_etapa_avanco = {}
    if avanco:
        for linha in avanco["linhas"]:
            if linha["etapa"]:
                por_etapa_avanco[linha["etapa"]] = linha

    etapas_ids = ({e for e in orcado_etapa if e} | {e for e in aplicado if e}
                  | {e for e in medido if e} | set(por_etapa_avanco))
    nomes = {e.pk: e for e in EtapaObra.objects.filter(pk__in=etapas_ids)}
    etapas = []
    for etapa_id in sorted(etapas_ids, key=lambda e: (getattr(nomes.get(e), "ordem", 10**6), e)):
        ont = orcado_etapa.get(etapa_id, ZERO)
        cr = aplicado.get(etapa_id, ZERO) + medido.get(etapa_id, ZERO)
        av = por_etapa_avanco.get(etapa_id) or {}
        etapas.append({
            "etapa": etapa_id,
            "etapa_nome": getattr(nomes.get(etapa_id), "nome_etapa", "—"),
            "orcado": _d(ont),
            "aplicado": _d(aplicado.get(etapa_id, ZERO)),
            "medido": _d(medido.get(etapa_id, ZERO)),
            "previsto_pct": av.get("previsto_pct"),
            "realizado_pct": av.get("realizado_pct"),
            **_valor_agregado(ont, av.get("previsto_pct"), av.get("realizado_pct"), cr),
        })

    obra_avanco = (avanco or {}).get("obra") or {}
    sem_etapa = aplicado.get(None, ZERO) + medido.get(None, ZERO)
    return {
        "obra": obra_id,
        "orcamento": vigente.pk if vigente else None,
        "orcamento_versao": vigente.versao if vigente else None,
        "plano": plano.pk if plano else None,
        "plano_status": plano.status if plano else None,
        "colunas": {
            "orcado": _d(orcado),
            "orcado_com_bdi": _d(vigente.valor_total) if vigente else None,
            "comprometido": _d(comprometido),
            "comprometido_pedidos": _d(pedidos),
            "comprometido_contratos": _d(em_contratos),
            "aplicado": _d(total_aplicado),
            "medido": _d(total_medido),
            "realizado": _d(realizado(tenant_id, obra_id)),
            "incorrido": _d(incorrido),
            "saldo": _d(orcado - comprometido) if orcado is not None else None,
            "estourado": bool(orcado is not None and comprometido > orcado),
        },
        "valor_agregado": {
            "previsto_pct": obra_avanco.get("previsto_pct"),
            "realizado_pct": obra_avanco.get("realizado_pct"),
            **_valor_agregado(orcado or ZERO, obra_avanco.get("previsto_pct"),
                              obra_avanco.get("realizado_pct"), incorrido),
        },
        "etapas": etapas,
        "sem_etapa": _d(sem_etapa),
        "contratos": [{**c, "valor": _d(c["valor"])} for c in contratos],
        "nota": (
            "Custo incorrido = material aplicado + serviço medido. Despesa que não passa por "
            "estoque nem por medição (energia do canteiro, por exemplo) está no realizado do ERP, "
            "não no incorrido."
        ),
    }


# ---------------------------------------------------------------------------
# Materiais gastos
# ---------------------------------------------------------------------------


def materiais_da_obra(*, obra, tenant_id: int, hoje: date | None = None) -> dict:
    """Cada insumo: orçado × aplicado, e o aplicado contra o **esperado pelo
    avanço** (orçado × % físico realizado) — o desperdício aparece antes de a
    obra acabar, e não na última nota."""
    from moduloorcamento.models import ItemOrcadoInsumo
    from moduloorcamento.planilha import orcamento_vigente
    from modulosil.models import MovimentacaoEstoque

    from . import services

    obra_id = obra.pk
    vigente = orcamento_vigente(tenant_id, obra_id)
    linhas: dict = {}

    def linha(item_id, descricao, unidade, categoria):
        return linhas.setdefault(item_id or f"sem:{descricao}", {
            "item": item_id, "descricao": descricao, "unidade": unidade, "categoria": categoria,
            "orcado_qtd": ZERO, "orcado_valor": ZERO, "aplicado_qtd": ZERO, "aplicado_valor": ZERO,
        })

    if vigente is not None:
        for r in (ItemOrcadoInsumo.objects
                  .filter(item_orcado__orcamento=vigente)
                  .exclude(categoria__in=[ItemOrcadoInsumo.Categoria.MAO_DE_OBRA,
                                          ItemOrcadoInsumo.Categoria.ENCARGOS_COMPLEMENTARES])
                  .values("item_id", "descricao", "unidade", "categoria")
                  .annotate(
                      q=Coalesce(Sum(F("coeficiente") * F("item_orcado__quantidade"),
                                     output_field=DEC), ZERO, output_field=DEC),
                      v=Coalesce(Sum(F("custo_no_item") * F("item_orcado__quantidade"),
                                     output_field=DEC), ZERO, output_field=DEC),
                  )):
            l = linha(r["item_id"], r["descricao"], r["unidade"], r["categoria"])
            l["orcado_qtd"] += r["q"]
            l["orcado_valor"] += r["v"]

    for item_id, descricao, unidade, tipo, qtd, custo in MovimentacaoEstoque.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
        tipo__in=(MovimentacaoEstoque.Tipo.SAIDA, MovimentacaoEstoque.Tipo.DEVOLUCAO),
    ).values_list("item_id", "item__descricao", "item__unidade", "tipo", "quantidade", "custo_unitario"):
        sinal = -1 if tipo == MovimentacaoEstoque.Tipo.DEVOLUCAO else 1
        alvo = linhas.get(item_id) or linha(item_id, descricao, unidade, "")
        alvo["aplicado_qtd"] += sinal * abs(qtd or ZERO)
        alvo["aplicado_valor"] += sinal * abs(qtd or ZERO) * (custo or ZERO)

    plano = plano_da_obra(tenant_id, obra_id)
    avanco = services.avanco_fisico_financeiro(plano, hoje=hoje) if plano else None
    realizado_pct = ((avanco or {}).get("obra") or {}).get("realizado_pct")
    fator = Decimal(str(realizado_pct)) / CEM if realizado_pct is not None else None

    saida = []
    for l in linhas.values():
        esperado = l["orcado_qtd"] * fator if fator is not None else None
        desvio = (l["aplicado_qtd"] - esperado) if esperado is not None else None
        saida.append({
            "item": l["item"], "descricao": l["descricao"], "unidade": l["unidade"],
            "categoria": l["categoria"],
            "orcado_qtd": _d(l["orcado_qtd"], "0.001"), "orcado_valor": _d(l["orcado_valor"]),
            "aplicado_qtd": _d(l["aplicado_qtd"], "0.001"), "aplicado_valor": _d(l["aplicado_valor"]),
            "consumido_pct": _d(_razao(l["aplicado_qtd"] * CEM, l["orcado_qtd"]), "0.1"),
            "esperado_qtd": _d(esperado, "0.001"),
            "desvio_qtd": _d(desvio, "0.001"),
            "desvio_pct": _d(_razao(desvio * CEM, esperado), "0.1") if desvio is not None and esperado else None,
            "fora_do_orcamento": l["orcado_qtd"] == 0,
        })
    saida.sort(key=lambda l: Decimal(l["aplicado_valor"] or 0) + Decimal(l["orcado_valor"] or 0), reverse=True)
    return {
        "obra": obra_id,
        "orcamento": vigente.pk if vigente else None,
        "realizado_pct": realizado_pct,
        "insumos": saida,
        "totais": {
            "orcado": _d(sum((l["orcado_valor"] for l in linhas.values()), ZERO)),
            "aplicado": _d(sum((l["aplicado_valor"] for l in linhas.values()), ZERO)),
        },
    }
