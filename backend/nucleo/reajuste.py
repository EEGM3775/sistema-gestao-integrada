# backend/nucleo/reajuste.py
"""O reajuste por **fórmula paramétrica** — o motor que os contratos usam.

*Decisão do dono, 10/10/2026:* reajuste é ato de **contrato**, não de
orçamento. Ele saiu do Orçamento (que só planeja) e mora aqui, sobre a série
única de `nucleo.ValorIndice`, para servir aos dois lados da obra: a medição do
**empreiteiro** (custo) e a do **contratante** (receita), ambas no PDCA.

    F = a + Σ pᵢ × (Iᵢ,t / Iᵢ,0)        com   a + Σ pᵢ = 1
    R = V × (F − 1)

    a   parcela não reajustável       pᵢ  peso da parcela i
    Iᵢ,0 índice da data-base           Iᵢ,t índice do aniversário vigente

**O aniversário, e não o mês da medição.** Reajuste anual (o padrão da lei)
vale da data-base + 12 meses em diante, com o índice **daquele** mês — e o
seguinte só no próximo aniversário. Entre dois aniversários o fator não muda.

**A razão de números-índice, não a soma das variações.** Com o número-índice
publicado, `Iₜ/I₀` são dois pontos e uma divisão; sem ele, a razão sai do
produto das variações mensais de `(I₀, Iₜ]` — composta, nunca somada.

**Índice ainda não publicado → provisório, e dito.** O IPCA de julho sai em
agosto; a medição de julho não pode esperar. Usa-se o último publicado e a
resposta marca `provisorio` com a competência que valeu — o acerto vem quando o
definitivo sair, e na medição final todos têm de ser definitivos.

**Truncado, não arredondado.** O fator é cortado na casa que o contrato
declara (quatro, no edital comum): é a regra dos modelos de contrato público, e
arredondar daria centavo de diferença no aditivo — apontamento de auditoria.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal

UM = Decimal("1")
CEM = Decimal("100")
SEIS = Decimal("0.000001")
#: Folga na conferência `a + Σp = 1`: edital publica peso com quatro casas e a
#: última às vezes deixa a soma em 0,9999. Recusar seria recusar o edital.
TOLERANCIA_FECHAMENTO = Decimal("0.0005")


class ReajusteInvalido(Exception):
    """Fórmula que não fecha, índice sem série nenhuma."""


def primeiro_do_mes(d: date) -> date:
    return d.replace(day=1)


def somar_meses(d: date, meses: int) -> date:
    total = d.year * 12 + (d.month - 1) + meses
    return date(total // 12, total % 12 + 1, 1)


def meses_entre(de: date, ate: date) -> int:
    return (ate.year - de.year) * 12 + (ate.month - de.month)


@dataclass
class Razao:
    valor: Decimal
    competencia_usada: date
    provisorio: bool
    metodo: str  # "numero_indice" | "variacoes"


def razao_entre(indice, base: date, alvo: date) -> Razao:
    """`I(alvo) / I(base)` na série única — pelo número-índice quando os dois
    pontos existem, pela composição das variações quando não."""
    from .models import ValorIndice

    base, alvo = primeiro_do_mes(base), primeiro_do_mes(alvo)
    if alvo <= base:
        return Razao(UM, alvo, False, "nenhum")
    publicado = (ValorIndice.objects.filter(indice=indice, competencia__lte=alvo)
                 .order_by("-competencia").values_list("competencia", flat=True).first())
    if publicado is None or publicado <= base:
        raise ReajusteInvalido(
            f"{indice.codigo} não tem série publicada depois de {base:%m/%Y}. "
            "Importe a série do índice antes de reajustar."
        )
    usado = min(publicado, alvo)
    provisorio = usado < alvo

    pontos = dict(ValorIndice.objects.filter(
        indice=indice, competencia__in=[base, usado], numero_indice__isnull=False,
    ).values_list("competencia", "numero_indice"))
    if base in pontos and usado in pontos and pontos[base]:
        return Razao((pontos[usado] / pontos[base]).quantize(SEIS), usado, provisorio, "numero_indice")

    fator = UM
    for variacao in (ValorIndice.objects
                     .filter(indice=indice, competencia__gt=base, competencia__lte=usado,
                             variacao_percentual__isnull=False)
                     .order_by("competencia").values_list("variacao_percentual", flat=True)):
        fator *= UM + variacao / CEM
    return Razao(fator.quantize(SEIS), usado, provisorio, "variacoes")


def validar_pesos(parcela_fixa: Decimal, pesos: list[Decimal]) -> Decimal:
    soma = (parcela_fixa or Decimal("0")) + sum(pesos, Decimal("0"))
    if abs(soma - UM) > TOLERANCIA_FECHAMENTO:
        raise ReajusteInvalido(
            f"A fórmula não fecha: a + Σp = {soma}, e precisa somar 1. "
            "Um peso a menos vira desconto silencioso; um a mais, aumento."
        )
    return soma


def ciclos_completos(data_base: date, ate: date, periodicidade_meses: int) -> int:
    """Quantos aniversários já passaram em `ate` (inclusive o do próprio mês)."""
    if not periodicidade_meses or ate < data_base:
        return 0
    meses = meses_entre(primeiro_do_mes(data_base), primeiro_do_mes(ate))
    if ate.day < data_base.day:
        meses -= 1
    return max(meses // periodicidade_meses, 0)


def aniversario(data_base: date, ciclo: int, periodicidade_meses: int) -> date:
    """A data do `ciclo`-ésimo aniversário (o dia da data-base, no mês certo)."""
    mes = somar_meses(primeiro_do_mes(data_base), ciclo * periodicidade_meses)
    try:
        return mes.replace(day=data_base.day)
    except ValueError:  # 31 num mês de 30
        return somar_meses(mes, 1).replace(day=1)


def fator(*, parcela_fixa: Decimal, parcelas: list[tuple], data_base: date, ciclo: int,
          periodicidade_meses: int = 12, casas: int = 4) -> dict:
    """O fator do `ciclo` e a memória de cada parcela — `parcelas` é uma lista
    de `(indice, peso, rotulo)`. Ciclo 0 é o preço original: fator 1."""
    validar_pesos(parcela_fixa, [p for _i, p, _r in parcelas])
    if ciclo <= 0:
        return {"ciclo": 0, "fator": "1", "competencia": None, "provisorio": False, "parcelas": []}
    base = primeiro_do_mes(data_base)
    alvo = somar_meses(base, ciclo * periodicidade_meses)
    total = parcela_fixa or Decimal("0")
    provisorio = False
    memoria = []
    for indice, peso, rotulo in parcelas:
        r = razao_entre(indice, base, alvo)
        contribuicao = (peso * r.valor).quantize(SEIS)
        total += contribuicao
        provisorio = provisorio or r.provisorio
        memoria.append({
            "indice": indice.codigo, "rotulo": rotulo or indice.nome, "peso": str(peso),
            "razao": str(r.valor), "competencia_usada": r.competencia_usada.isoformat(),
            "provisorio": r.provisorio, "metodo": r.metodo, "contribuicao": str(contribuicao),
        })
    passo = Decimal(1).scaleb(-casas)
    return {
        "ciclo": ciclo,
        "competencia": alvo.isoformat(),
        "fator": str(total.quantize(passo, rounding=ROUND_DOWN)),
        "provisorio": provisorio,
        "parcela_fixa": str(parcela_fixa or 0),
        "parcelas": memoria,
    }


def reajuste_do_periodo(*, valor: Decimal, inicio: date, fim: date, parcela_fixa: Decimal,
                        parcelas: list[tuple], data_base: date, periodicidade_meses: int = 12,
                        casas: int = 4) -> dict:
    """Quanto o reajuste acrescenta a `valor` executado entre `inicio` e `fim`.

    O serviço executado **antes** do aniversário vigente está no preço do ciclo
    anterior; o de depois, no novo. Período que atravessa o aniversário divide o
    valor pelos dias corridos de cada lado — a medição não diz em que dia cada
    metro foi feito, e o dia corrido é a régua neutra.
    """
    if not parcelas or valor == 0:
        return {"valor": "0.00", "provisorio": False, "ciclos": []}
    ciclo_fim = ciclos_completos(data_base, fim, periodicidade_meses)
    if ciclo_fim <= 0:
        return {"valor": "0.00", "provisorio": False, "ciclos": [],
                "proximo_aniversario": aniversario(data_base, 1, periodicidade_meses).isoformat()}
    corte = aniversario(data_base, ciclo_fim, periodicidade_meses)
    dias = (fim - inicio).days + 1
    depois = max(min((fim - max(corte, inicio)).days + 1, dias), 0)
    fracoes = [(ciclo_fim, Decimal(depois) / Decimal(dias))]
    if depois < dias:
        fracoes.append((ciclo_fim - 1, Decimal(dias - depois) / Decimal(dias)))

    total = Decimal("0")
    provisorio = False
    ciclos = []
    for ciclo, fracao in fracoes:
        memoria = fator(parcela_fixa=parcela_fixa, parcelas=parcelas, data_base=data_base,
                        ciclo=ciclo, periodicidade_meses=periodicidade_meses, casas=casas)
        acrescimo = valor * fracao * (Decimal(memoria["fator"]) - UM)
        total += acrescimo
        provisorio = provisorio or memoria["provisorio"]
        ciclos.append({**memoria, "fracao_do_periodo": str(fracao.quantize(SEIS)),
                       "acrescimo": str(acrescimo.quantize(Decimal("0.01")))})
    return {"valor": str(total.quantize(Decimal("0.01"))), "provisorio": provisorio, "ciclos": ciclos}
