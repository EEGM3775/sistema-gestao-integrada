"""A DRE por entidade e o consolidado — docs/modulos/entidades.md §6.

**Própria:** receita e despesa dos títulos da entidade, com o intercompany pela
natureza (§3): o a pagar de repasse de despesa **é** despesa dela; o a receber
de repasse de despesa **abate** a despesa de quem pagou — e o simétrico na
receita. Assim a despesa rateada sai de quem pagou e entra em quem consumiu.

**Pelas cotas:** o resultado de cada entidade própria de empreendimento (a SPE,
a SCP…) em que ela participa, vezes a cota.

**Consolidado:** a soma das próprias das entidades alcançadas — o intercompany
entre elas se anula na soma — mais a parte pelas cotas só das entidades que
ficaram de fora (somar a da SPE que já está dentro contaria duas vezes).

Competência = valor do título (pelo vencimento, no período); caixa = o já
baixado. Cancelado não conta.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum

from .models import ContaPagar, ContaReceber, NaturezaIntercompany, StatusConta

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")
DESPESA, RECEITA = NaturezaIntercompany.REPASSE_DESPESA, NaturezaIntercompany.REPASSE_RECEITA


def _q(v) -> Decimal:
    return (v or ZERO).quantize(CENTAVO)


def _somas(modelo, tenant_id, entidade_id, periodo) -> dict[str, tuple[Decimal, Decimal]]:
    """`{natureza: (competência, caixa)}` dos títulos da entidade."""
    qs = modelo.objects.filter(tenant_id=tenant_id, entidade_id=entidade_id).exclude(status=StatusConta.CANCELADO)
    de, ate = periodo
    if de:
        qs = qs.filter(data_vencimento__gte=de)
    if ate:
        qs = qs.filter(data_vencimento__lte=ate)
    linhas = qs.values("natureza").annotate(v=Sum("valor"), p=Sum("valor_pago")).order_by()
    return {l["natureza"]: (l["v"] or ZERO, l["p"] or ZERO) for l in linhas}


def propria(tenant_id, entidade_id, periodo=(None, None)) -> dict:
    cr = _somas(ContaReceber, tenant_id, entidade_id, periodo)
    cp = _somas(ContaPagar, tenant_id, entidade_id, periodo)
    nada = (ZERO, ZERO)

    def lado(i):
        receita_terceiros = cr.get("", nada)[i]
        receita = receita_terceiros + cr.get(RECEITA, nada)[i] - cp.get(RECEITA, nada)[i]
        despesa_terceiros = cp.get("", nada)[i]
        despesa = despesa_terceiros + cp.get(DESPESA, nada)[i] - cr.get(DESPESA, nada)[i]
        return {
            "receita": receita, "despesa": despesa, "resultado": receita - despesa,
            "receita_terceiros": receita_terceiros, "despesa_terceiros": despesa_terceiros,
            "despesa_repassada": cr.get(DESPESA, nada)[i], "despesa_recebida": cp.get(DESPESA, nada)[i],
            "receita_repassada": cp.get(RECEITA, nada)[i], "receita_recebida": cr.get(RECEITA, nada)[i],
        }

    return {"competencia": lado(0), "caixa": lado(1)}


def _cotas(tenant_id, entidade_id) -> list:
    """As entidades próprias de empreendimento em que esta participa, com a cota."""
    from entidades.models import ParticipacaoEmpreendimento

    return list(
        ParticipacaoEmpreendimento.objects.filter(
            tenant_id=tenant_id, entidade_id=entidade_id, empreendimento__entidade_propria__isnull=False,
            empreendimento__entidade_propria__externa=False,
        ).exclude(empreendimento__entidade_propria_id=entidade_id)
        .select_related("empreendimento__entidade_propria")
    )


def _texto(d: dict) -> dict:
    return {k: str(_q(v)) for k, v in d.items()}


def dre(tenant_id, entidades: list, periodo=(None, None)) -> dict:
    """A DRE de cada entidade pedida (própria + cotas) e o consolidado delas."""
    ids = {e.pk for e in entidades}
    cache: dict[int, dict] = {}

    def da(ent_id):
        if ent_id not in cache:
            cache[ent_id] = propria(tenant_id, ent_id, periodo)
        return cache[ent_id]

    saida, consolidado = [], {"competencia": {}, "caixa": {}}
    cotas_de_fora: dict[int, Decimal] = {}
    for entidade in entidades:
        p = da(entidade.pk)
        linhas_cota = []
        for part in _cotas(tenant_id, entidade.pk):
            spe = part.empreendimento.entidade_propria
            fator = part.cota / Decimal("100")
            resultado_spe = da(spe.pk)
            linhas_cota.append({
                "entidade": spe.pk, "nome": str(spe), "empreendimento": part.empreendimento.empreendimento,
                "cota": str(part.cota.normalize()), "administradora": part.administradora,
                "competencia": str(_q(resultado_spe["competencia"]["resultado"] * fator)),
                "caixa": str(_q(resultado_spe["caixa"]["resultado"] * fator)),
            })
            if spe.pk not in ids:
                chave = (spe.pk, entidade.pk)
                cotas_de_fora[chave] = (resultado_spe, fator)
        for regime in ("competencia", "caixa"):
            for k, v in p[regime].items():
                consolidado[regime][k] = consolidado[regime].get(k, ZERO) + v
        saida.append({
            "entidade": entidade.pk, "nome": str(entidade), "papel": entidade.papel,
            "papel_nome": entidade.get_papel_display(), "documento": entidade.documento,
            "competencia": _texto(p["competencia"]), "caixa": _texto(p["caixa"]),
            "cotas": linhas_cota,
            "resultado_com_cotas": {
                regime: str(_q(p[regime]["resultado"] + sum(
                    (Decimal(l[regime]) for l in linhas_cota), ZERO,
                )))
                for regime in ("competencia", "caixa")
            },
        })
    pelas_cotas = {
        regime: sum((r[regime]["resultado"] * f for r, f in cotas_de_fora.values()), ZERO)
        for regime in ("competencia", "caixa")
    }
    return {
        "periodo": {"de": periodo[0].isoformat() if periodo[0] else None,
                    "ate": periodo[1].isoformat() if periodo[1] else None},
        "entidades": saida,
        "consolidado": {
            "competencia": _texto(consolidado["competencia"]) if consolidado["competencia"] else {},
            "caixa": _texto(consolidado["caixa"]) if consolidado["caixa"] else {},
            "pelas_cotas": {k: str(_q(v)) for k, v in pelas_cotas.items()},
            "resultado": {
                regime: str(_q(consolidado[regime].get("resultado", ZERO) + pelas_cotas[regime]))
                for regime in ("competencia", "caixa")
            },
        },
    }


def periodo_da_requisicao(params) -> tuple[date | None, date | None]:
    def ler(chave):
        bruto = params.get(chave)
        return date.fromisoformat(bruto) if bruto else None
    return ler("data_de"), ler("data_ate")
