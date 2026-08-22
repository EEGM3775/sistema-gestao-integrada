# backend/moduloorcamento/quantitativos.py
"""A **memória de cálculo do quantitativo** (ORC.7).

Antes desta fatia o orçamento era auditável de um lado só. O preço da linha
abria em insumos (`ItemOrcadoInsumo`) e respondia "por que este m³ custa
R$ 412,80?"; a quantidade era um Decimal digitado e não respondia a nada. Numa
conferência de proposta é a quantidade que se questiona primeiro — o preço vem
de tabela pública, a quantidade vem do projeto de quem orçou.

Aqui ela vira soma de parciais, no formato que Arquimedes e ORSE mantêm e que o
setor usa desde a prancheta::

    descrição        n      a       b      c       total
    Parede eixo B    2  ×  3,50 ×  2,80         =  19,6000
    (−) Vão de porta 1  ×  0,80 ×  2,10         =  −1,6800
                                          total =  17,9200

Três decisões que a conta esconde:

1. **Dimensão ausente não é zero, é ausência.** Multiplicar por `b = None` como
   se fosse 0 zeraria toda linha de contagem (`n = 12 unidades`) — o erro
   silencioso mais caro que existe numa planilha, porque o total continua sendo
   um número plausível.
2. **A subtração é sinal, não número negativo.** O usuário digita `0,80 × 2,10`
   e marca "(−)"; guardar `-0,80` faria a conferência ler uma parede de
   comprimento negativo. O sinal entra só no total.
3. **Quem tem medição tem quantidade derivada.** A linha-pai deixa de aceitar
   quantidade digitada no momento em que ganha a primeira parcial. Deixar as
   duas pontas graváveis é garantia de divergência — a mesma armadilha que a
   planta já registrou para o `EtapaObra.orcamento_previsto`.
"""
import ast
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Sum

from payment.planos import (
    ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA,
    ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM,
)

from .models import ItemOrcado, LinhaMedicao

QUATRO = Decimal("0.0001")


class FormulaInvalida(Exception):
    """Expressão que a avaliação restrita recusa."""


class MedicaoInvalida(Exception):
    """Parcial que não pode ser gravada — teto de linhas, item sintético."""


# ---------------------------------------------------------------------------
# Avaliação da fórmula
# ---------------------------------------------------------------------------

# O que a expressão pode conter. A lista é de **nós de AST**, não de caracteres:
# filtrar por regex deixaria passar `__import__` escrito de formas criativas, e
# recusaria expressões válidas. Aqui só existe aritmética — não há nó de nome,
# de atributo nem de chamada na lista, então não há o que resolver nem o que
# invocar, e a avaliação não precisa de sandbox.
_NOS_PERMITIDOS = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
)


def _profundidade(no: ast.AST, nivel: int = 0) -> int:
    filhos = list(ast.iter_child_nodes(no))
    if not filhos:
        return nivel
    return max(_profundidade(filho, nivel + 1) for filho in filhos)


def avaliar_formula(texto: str) -> Decimal:
    """Avalia aritmética simples e devolve `Decimal`.

    Aceita `+ - * / ( )`, decimal com ponto **ou vírgula** (quem digita numa
    planilha brasileira escreve `3,50`, e recusar isso seria exigir que o
    orçamentista mudasse de teclado no meio da linha).

    A conta corre em `Decimal`, não em `float`: `0.1 + 0.2` em ponto flutuante
    é `0.30000000000000004`, e numa planilha de quantidade essa cauda vira
    centavo de diferença no total do orçamento.
    """
    limpo = (texto or "").strip().replace(",", ".")
    if not limpo:
        raise FormulaInvalida("Fórmula vazia.")

    try:
        arvore = ast.parse(limpo, mode="eval")
    except SyntaxError as erro:
        raise FormulaInvalida(f"Não é uma expressão aritmética válida: {erro.msg}.") from erro

    if _profundidade(arvore) > ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA:
        raise FormulaInvalida(
            f"Fórmula aninhada demais (limite de {ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA} níveis)."
        )

    for no in ast.walk(arvore):
        if not isinstance(no, _NOS_PERMITIDOS):
            raise FormulaInvalida(
                "A fórmula só aceita números e as operações + − × ÷ com parênteses."
            )
        if isinstance(no, ast.Constant) and not isinstance(no.value, (int, float)):
            raise FormulaInvalida("A fórmula só aceita números.")

    return _avaliar(arvore.body)


def _avaliar(no: ast.AST) -> Decimal:
    if isinstance(no, ast.Constant):
        return Decimal(str(no.value))
    if isinstance(no, ast.UnaryOp):
        valor = _avaliar(no.operand)
        return -valor if isinstance(no.op, ast.USub) else valor
    if isinstance(no, ast.BinOp):
        esquerda, direita = _avaliar(no.left), _avaliar(no.right)
        if isinstance(no.op, ast.Add):
            return esquerda + direita
        if isinstance(no.op, ast.Sub):
            return esquerda - direita
        if isinstance(no.op, ast.Mult):
            return esquerda * direita
        if isinstance(no.op, ast.Div):
            if direita == 0:
                raise FormulaInvalida("Divisão por zero.")
            return esquerda / direita
    raise FormulaInvalida("Operação não suportada na fórmula.")


# ---------------------------------------------------------------------------
# A parcial
# ---------------------------------------------------------------------------


def calcular_linha(linha: LinhaMedicao) -> Decimal:
    """Total da parcial, já com o sinal. Não grava.

    Com `formula` preenchida é ela que manda — as três dimensões viram apenas
    documentação da linha, e é assim que uma seção variável ou um arco entram
    sem inventar um quarto campo.
    """
    if linha.formula:
        try:
            bruto = avaliar_formula(linha.formula)
        except InvalidOperation as erro:  # número absurdo dentro da expressão
            raise FormulaInvalida("Número fora de faixa na fórmula.") from erro
    else:
        bruto = linha.repeticoes if linha.repeticoes is not None else Decimal("1")
        for dimensao in (linha.comprimento, linha.largura, linha.altura):
            if dimensao is not None:
                bruto *= dimensao

    sinal = Decimal(linha.sinal if linha.sinal in (1, -1) else 1)
    return (bruto * sinal).quantize(QUATRO, rounding=ROUND_HALF_UP)


@transaction.atomic
def salvar_linha(linha: LinhaMedicao, *, sincronizar: bool = True) -> LinhaMedicao:
    """Calcula o total, grava e reflete a soma na quantidade da linha-pai."""
    if linha.item_orcado.tipo_linha == ItemOrcado.TipoLinha.SINTETICO:
        raise MedicaoInvalida(
            "Linha sintética é agrupador — ela soma os filhos e não tem quantidade própria."
        )

    existentes = LinhaMedicao.objects.filter(item_orcado=linha.item_orcado)
    if linha.pk:
        existentes = existentes.exclude(pk=linha.pk)
    if existentes.count() >= ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM:
        raise MedicaoInvalida(
            f"Uma linha orçada aceita até {ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM} parciais."
        )

    linha.total = calcular_linha(linha)
    linha.save()
    if sincronizar:
        sincronizar_quantidade(linha.item_orcado)
    return linha


@transaction.atomic
def recalcular_linhas(item_orcado: ItemOrcado) -> list[LinhaMedicao]:
    """Refaz o total de todas as parciais de uma linha e sincroniza o pai.

    Serve ao caminho de escrita em lote — colar um bloco do Excel na aba de
    medição grava dezenas de parciais de uma vez, e recalcular uma a uma faria
    a soma do pai ser reescrita dezenas de vezes.
    """
    linhas = list(LinhaMedicao.objects.filter(item_orcado=item_orcado))
    for linha in linhas:
        total = calcular_linha(linha)
        if linha.total != total:
            linha.total = total
            linha.save(update_fields=["total"])
    sincronizar_quantidade(item_orcado)
    return linhas


@transaction.atomic
def sincronizar_quantidade(item_orcado: ItemOrcado) -> ItemOrcado:
    """A soma das parciais vira a quantidade da linha — e recalcula o orçamento.

    Sem parcial nenhuma a quantidade **não é zerada**: apagar a última parcial
    de uma linha devolve a ela a quantidade digitada que tinha antes, em vez de
    transformar o item em zero e sumir com ele do total. Zerar seria destruir
    dado a partir de uma remoção que o usuário leu como "desisti da memória",
    não como "este serviço não existe mais".
    """
    from . import planilha  # tardio: planilha importa models, não este módulo

    agregado = LinhaMedicao.objects.filter(item_orcado=item_orcado).aggregate(
        soma=Sum("total"), linhas=Count("pk"),
    )
    if not agregado["linhas"]:
        return item_orcado

    soma = agregado["soma"] or Decimal("0")
    if item_orcado.quantidade != soma:
        item_orcado.quantidade = soma
        item_orcado.save(update_fields=["quantidade"])
    planilha.recalcular_orcamento(item_orcado.orcamento)
    return item_orcado


def tem_medicao(item_orcado: ItemOrcado) -> bool:
    """Se a quantidade da linha é derivada — a grade a mostra bloqueada."""
    return LinhaMedicao.objects.filter(item_orcado=item_orcado).exists()


def memoria_do_quantitativo(item_orcado: ItemOrcado) -> dict:
    """As parciais da linha, com o total conferido e o resumo por sinal.

    O par somado × subtraído existe porque é o que a conferência olha: uma
    parede bruta de 120 m² com 40 m² de vãos é uma planilha bem levantada; a
    mesma parede com 0 m² de vão é uma que esqueceu as portas.
    """
    linhas = list(LinhaMedicao.objects.filter(item_orcado=item_orcado))
    somado = sum((linha.total for linha in linhas if linha.total > 0), Decimal("0"))
    subtraido = sum((linha.total for linha in linhas if linha.total < 0), Decimal("0"))

    return {
        "item_orcado": item_orcado.pk,
        "descricao": item_orcado.descricao,
        "unidade": item_orcado.unidade,
        "quantidade": str(item_orcado.quantidade),
        "derivada": bool(linhas),
        "total_somado": str(somado),
        "total_subtraido": str(subtraido),
        "total": str(somado + subtraido),
        "confere": (somado + subtraido) == item_orcado.quantidade if linhas else True,
        "linhas": [
            {
                "medicao": linha.pk,
                "ordem": linha.ordem,
                "descricao": linha.descricao,
                "sinal": linha.sinal,
                "repeticoes": str(linha.repeticoes),
                "comprimento": str(linha.comprimento) if linha.comprimento is not None else None,
                "largura": str(linha.largura) if linha.largura is not None else None,
                "altura": str(linha.altura) if linha.altura is not None else None,
                "formula": linha.formula,
                "total": str(linha.total),
                "referencia_projeto": linha.referencia_projeto,
            }
            for linha in linhas
        ],
    }


def cobertura_do_orcamento(orcamento) -> dict:
    """Quanto do orçamento tem quantidade com memória — a honestidade do número.

    Mesma disciplina do `cobertura_pct` da composição por natureza: uma planilha
    com 8% das linhas medidas e 92% digitadas não pode se apresentar como
    "quantitativo rastreável". A cobertura é ponderada por **valor**, não por
    contagem de linhas — dez itens de baixo peso medidos não cobrem o item que
    concentra o custo.
    """
    analiticas = ItemOrcado.objects.filter(
        orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
    )
    total = analiticas.aggregate(soma=Sum("total_custo_direto"))["soma"] or Decimal("0")
    com_memoria = analiticas.filter(linhas_medicao__isnull=False).distinct().aggregate(
        soma=Sum("total_custo_direto")
    )["soma"] or Decimal("0")

    return {
        "orcamento": orcamento.pk,
        "custo_direto_total": str(total),
        "custo_com_memoria": str(com_memoria),
        "cobertura_pct": str(
            (com_memoria / total * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ) if total > 0 else "0",
        "linhas_totais": analiticas.count(),
        "linhas_com_memoria": analiticas.filter(linhas_medicao__isnull=False).distinct().count(),
    }
