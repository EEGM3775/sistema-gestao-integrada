# backend/moduloorcamento/reajuste.py
"""Reajuste contratual por **fórmula paramétrica** (ORC.7).

O ORC.5b resolveu *reprecificar*: trocar o preço unitário pela cotação de outra
publicação, item a item. Isso muda a **composição** do custo e é operação de
orçamentista. Reajuste é outra coisa: o contrato já foi assinado, o preço é o
que é, e a cláusula manda corrigir tudo por uma cesta de índices na data de
aniversário. Ninguém reabre composição — multiplica-se::

    R = V × [ a + Σ pᵢ × (Iᵢ,t / Iᵢ,0) ]     com   a + Σ pᵢ = 1

    a   parcela não reajustável (mobilização já paga, materiais já postos)
    pᵢ  peso da parcela i (mão de obra, materiais, equipamentos)
    Iᵢ  número-índice da parcela i, na data de reajuste (t) e na data-base (0)

**Por que a razão de números-índice, e não a soma das variações.** Encadear
variações mês a mês (`1,0042 × 1,0037 × …`) acumula erro de arredondamento a
cada multiplicação; num contrato de milhões a diferença aparece como centavo no
aditivo, e centavo no aditivo é apontamento de auditoria. Dois pontos da série e
uma divisão não têm esse problema — é por isso que `ValorIndice` guarda o
número-índice e não só a variação.

**Duas travas que o domínio impõe:**

1. **A soma tem de fechar em 1.** `a + Σ pᵢ ≠ 1` não é fórmula de reajuste — é
   um redutor (ou um aumento) disfarçado de correção monetária, e passa
   despercebido porque o resultado continua sendo um número plausível.
2. **Aprovado exige revisão.** Reajustar é ato de contrato: em rascunho aplica
   direto, em aprovado passa por `planilha.revisar_orcamento` com tipo
   `reequilibrio`, que é onde o histórico de aditivo mora.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import (
    FormulaReajuste,
    IndiceEconomico,
    ItemOrcado,
    Orcamento,
    ParcelaFormulaReajuste,
    RevisaoOrcamento,
    ValorIndice,
)

SEIS = Decimal("0.000001")
QUATRO = Decimal("0.0001")
DUAS = Decimal("0.01")
UM = Decimal("1")
# Folga na conferência de fechamento: edital publica peso com quatro casas
# (0,3500 + 0,4000 + 0,2500) e o arredondamento da última às vezes deixa a soma
# em 0,9999. Recusar isso seria recusar o edital.
TOLERANCIA_FECHAMENTO = Decimal("0.0005")


class ReajusteInvalido(Exception):
    """Fórmula que não fecha, índice sem série na competência pedida."""


def _primeiro_dia(data) -> object:
    """Competência é sempre o dia 1º — série mensal não tem dia 17."""
    return data.replace(day=1)


def validar_formula(formula: FormulaReajuste) -> Decimal:
    """Confere o fechamento `a + Σ pᵢ = 1` e devolve a soma."""
    pesos = ParcelaFormulaReajuste.objects.filter(formula=formula).values_list("peso", flat=True)
    soma = (formula.parcela_fixa or Decimal("0")) + sum(pesos, Decimal("0"))
    if abs(soma - UM) > TOLERANCIA_FECHAMENTO:
        raise ReajusteInvalido(
            f"A fórmula não fecha: a + Σp = {soma}, e precisa somar 1. "
            "Um peso a menos vira desconto silencioso; um a mais, aumento."
        )
    return soma


def numero_indice(indice: IndiceEconomico, competencia) -> Decimal:
    """O número-índice na competência — ou o erro que diz exatamente o que falta.

    Não interpola nem repete o mês anterior. Um índice ainda não publicado é
    informação ausente, e preencher a lacuna com o vizinho produziria um fator
    que ninguém consegue reconstituir a partir da fonte oficial — que é
    justamente o que a outra parte do contrato vai fazer para conferir.
    """
    alvo = _primeiro_dia(competencia)
    valor = ValorIndice.objects.filter(indice=indice, competencia=alvo).first()
    if valor is None:
        raise ReajusteInvalido(
            f"{indice.codigo} não tem valor publicado para {alvo:%m/%Y}. "
            "Importe a série antes de reajustar."
        )
    return valor.numero_indice


def calcular_fator(formula: FormulaReajuste, competencia) -> dict:
    """O fator de reajuste e a memória de cada parcela.

    A memória é o produto, não um detalhe: reajuste sem demonstração de cálculo
    é número que a fiscalização devolve. Cada parcela sai com os dois índices, a
    razão e a contribuição ao fator, para o aditivo ser conferível linha a linha.
    """
    validar_formula(formula)
    base = _primeiro_dia(formula.data_base)
    alvo = _primeiro_dia(competencia)

    fator = formula.parcela_fixa or Decimal("0")
    parcelas = []
    for parcela in ParcelaFormulaReajuste.objects.filter(formula=formula).select_related("indice"):
        i_zero = numero_indice(parcela.indice, base)
        i_t = numero_indice(parcela.indice, alvo)
        if i_zero == 0:
            raise ReajusteInvalido(f"{parcela.indice.codigo} tem número-índice zero em {base:%m/%Y}.")
        razao = (i_t / i_zero).quantize(SEIS, rounding=ROUND_HALF_UP)
        contribuicao = (parcela.peso * razao).quantize(SEIS, rounding=ROUND_HALF_UP)
        fator += contribuicao
        parcelas.append({
            "parcela": parcela.pk,
            "indice": parcela.indice.codigo,
            "nome_indice": parcela.indice.nome,
            "rotulo": parcela.rotulo or parcela.indice.nome,
            "peso": str(parcela.peso),
            "indice_base": str(i_zero),
            "indice_reajuste": str(i_t),
            "razao": str(razao),
            "variacao_pct": str(((razao - UM) * Decimal("100")).quantize(QUATRO, rounding=ROUND_HALF_UP)),
            "contribuicao": str(contribuicao),
        })

    fator = fator.quantize(SEIS, rounding=ROUND_HALF_UP)
    return {
        "formula": formula.pk,
        "nome": formula.nome,
        "data_base": base.isoformat(),
        "competencia": alvo.isoformat(),
        "parcela_fixa": str(formula.parcela_fixa),
        "parcelas": parcelas,
        "fator": str(fator),
        "variacao_pct": str(((fator - UM) * Decimal("100")).quantize(QUATRO, rounding=ROUND_HALF_UP)),
    }


def previa(orcamento: Orcamento, formula: FormulaReajuste, competencia) -> dict:
    """O que o reajuste faria — sem gravar nada.

    Mesma disciplina da prévia de reprecificação: descobrir depois que o total
    subiu e não saber em que linha é o defeito que a prévia existe para impedir.
    A diferença é que aqui o fator é único, então a prévia serve para conferir a
    **memória do fator** e o efeito no total, não para escolher linha a linha —
    reajuste contratual não é seletivo, ou vale para o contrato ou não vale.
    """
    calculo = calcular_fator(formula, competencia)
    fator = Decimal(calculo["fator"])

    linhas = ItemOrcado.objects.filter(
        orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
    ).order_by("codigo_eap")

    itens, antes_total, depois_total = [], Decimal("0"), Decimal("0")
    for linha in linhas:
        antes = linha.custo_unitario
        depois = (antes * fator).quantize(QUATRO, rounding=ROUND_HALF_UP)
        valor_antes = (antes * linha.quantidade).quantize(DUAS, rounding=ROUND_HALF_UP)
        valor_depois = (depois * linha.quantidade).quantize(DUAS, rounding=ROUND_HALF_UP)
        antes_total += valor_antes
        depois_total += valor_depois
        itens.append({
            "item_orcado": linha.pk,
            "codigo_eap": linha.codigo_eap,
            "descricao": linha.descricao,
            "unidade": linha.unidade,
            "quantidade": str(linha.quantidade),
            "custo_antes": str(antes),
            "custo_depois": str(depois),
            "valor_antes": str(valor_antes),
            "valor_depois": str(valor_depois),
            "delta": str(valor_depois - valor_antes),
        })

    return {
        "orcamento": orcamento.pk,
        "status_orcamento": orcamento.status,
        "exige_revisao": orcamento.status == Orcamento.Status.APROVADO,
        "memoria": calculo,
        "total_antes": str(antes_total),
        "total_depois": str(depois_total),
        "delta": str(depois_total - antes_total),
        "itens": itens,
    }


@transaction.atomic
def aplicar(
    orcamento: Orcamento,
    formula: FormulaReajuste,
    competencia,
    *,
    motivo: str = "",
    usuario_nome: str = "",
) -> dict:
    """Aplica o fator a todas as linhas analíticas.

    Em **rascunho**, escreve no próprio orçamento. Em **aprovado**, cria a
    revisão (tipo `reequilibrio`), aplica na versão nova e devolve ela — a régua
    congelada continua congelada, e a trilha fica em `RevisaoOrcamento`, que é
    onde licitação e contrato procuram.

    O `custo_unitario` é reajustado; `data_base_preco` e `fonte_referencia`
    **não** mudam. É deliberado e é o oposto da reprecificação: o preço continua
    sendo o da SINAPI de março, corrigido por contrato — dizer que virou preço de
    outra publicação seria rastro falso.
    """
    from . import planilha

    calculo = calcular_fator(formula, competencia)
    fator = Decimal(calculo["fator"])
    valor_anterior = orcamento.valor_total
    alvo = orcamento
    revisao = None

    if orcamento.status == Orcamento.Status.APROVADO:
        alvo = planilha.revisar_orcamento(
            orcamento,
            tipo=RevisaoOrcamento.Tipo.REEQUILIBRIO,
            motivo=motivo or (
                f"Reajuste contratual {formula.nome} — competência "
                f"{calculo['competencia'][:7]}, fator {fator}"
            ),
            usuario_nome=usuario_nome,
        )
        revisao = RevisaoOrcamento.objects.filter(orcamento=alvo).order_by("-numero").first()
    else:
        planilha.exigir_editavel(orcamento)

    atualizadas = []
    for linha in ItemOrcado.objects.filter(
        orcamento=alvo, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
    ):
        linha.custo_unitario = (linha.custo_unitario * fator).quantize(
            QUATRO, rounding=ROUND_HALF_UP
        )
        atualizadas.append(linha)
    ItemOrcado.objects.bulk_update(atualizadas, ["custo_unitario"])
    planilha.recalcular_orcamento(alvo)
    alvo.refresh_from_db()

    if revisao is not None:
        revisao.valor_novo = alvo.valor_total
        revisao.save(update_fields=["valor_novo"])

    return {
        "orcamento": alvo.pk,
        "versao": alvo.versao,
        "gerou_revisao": revisao is not None,
        "revisao": revisao.pk if revisao else None,
        "memoria": calculo,
        "linhas_reajustadas": len(atualizadas),
        "valor_anterior": str(valor_anterior),
        "valor_novo": str(alvo.valor_total),
    }


def series_disponiveis(*, apenas_ativos: bool = True) -> list[dict]:
    """Os índices e a janela de série de cada um.

    A janela é o que a tela precisa para não deixar escolher uma competência que
    vai falhar: sem ela o usuário monta a fórmula, escolhe o mês e só descobre no
    submit que o INCC de agosto ainda não saiu.
    """
    consulta = IndiceEconomico.objects.all()
    if apenas_ativos:
        consulta = consulta.filter(ativo=True)

    saida = []
    for indice in consulta:
        valores = ValorIndice.objects.filter(indice=indice).order_by("competencia")
        primeiro = valores.first()
        ultimo = valores.last()
        saida.append({
            "indice": indice.pk,
            "codigo": indice.codigo,
            "nome": indice.nome,
            "fonte": indice.fonte,
            "uf": indice.uf,
            "competencia_inicial": primeiro.competencia.isoformat() if primeiro else None,
            "competencia_final": ultimo.competencia.isoformat() if ultimo else None,
            "valores": valores.count(),
        })
    return saida
