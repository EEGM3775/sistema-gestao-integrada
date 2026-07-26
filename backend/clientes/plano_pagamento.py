"""O motor da proposta: do preço de tabela ao carnê do comprador.

Como o mercado monta uma venda de unidade (loteadora e incorporadora vendendo
direto, sem banco no meio):

    valor de tabela
      − desconto (% ou R$)                    → valor negociado (o "à vista")
      − entrada / ATO (parcelável, sem juros) → saldo a financiar
      → N parcelas mensais com juros a.m., por **Price** (parcela fixa) ou
        **SAC** (amortização constante, parcela decrescente)
      + balões/intercaladas (anuais ou semestrais), que **somam** à mensal do mês

Três decisões que este módulo assume, e por quê:

- **A entrada não rende juros.** Ela é sinal, não financiamento — o dinheiro
  entra antes da entrega. Cobrar juros sobre entrada é o erro que faz a proposta
  do sistema não bater com a que o corretor fez na mão.
- **O balão abate saldo antes do parcelamento.** O saldo financiado é o que
  sobra depois da entrada *e* dos balões; senão o cliente pagaria juros sobre um
  valor que ele já se comprometeu a quitar à parte, e o total estouraria.
- **Juros correm a partir da 1ª parcela do saldo**, não da data da venda. É a
  configuração que os sistemas do setor chamam de "juros inicia na 1ª parcela",
  e a que o comprador entende: durante a entrada não corre juro.

Sem correção monetária (INCC/IGP-M/IPCA). Reajuste anual é contrato vivo — muda
parcela já emitida, mexe em boleto e exige índice publicado; entra depois, com
lugar próprio. O que este módulo devolve é o **plano na data da assinatura**.

Funções puras: recebem números, devolvem números. Não tocam banco — é o que
permite simular na tela a cada tecla sem gravar nada.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
ZERO = Decimal("0")


def centavos(valor: Decimal) -> Decimal:
    """Dinheiro tem duas casas. Arredondamento bancário meio-para-cima, o mesmo
    que o comprador faz na calculadora."""
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def somar_meses(base: date, meses: int) -> date:
    """Mesmo dia, N meses à frente — com o dia 31 caindo no último dia do mês
    curto (o vencimento 31/01 vira 28/02, não 03/03)."""
    total = base.month - 1 + meses
    ano = base.year + total // 12
    mes = total % 12 + 1
    return date(ano, mes, min(base.day, calendar.monthrange(ano, mes)[1]))


@dataclass
class Parcela:
    """Uma linha do carnê. `tipo` diz o que ela é para o comprador."""
    numero: int
    tipo: str  # entrada | parcela | balao
    vencimento: date
    valor: Decimal
    juros: Decimal = ZERO
    amortizacao: Decimal = ZERO
    saldo: Decimal = ZERO

    def como_dict(self) -> dict:
        return {
            "numero": self.numero,
            "tipo": self.tipo,
            "vencimento": self.vencimento.isoformat(),
            "valor": str(self.valor),
            "juros": str(self.juros),
            "amortizacao": str(self.amortizacao),
            "saldo": str(self.saldo),
        }


@dataclass
class Plano:
    valor_tabela: Decimal
    desconto: Decimal
    valor_negociado: Decimal
    entrada: Decimal
    baloes: Decimal
    saldo_financiado: Decimal
    total_juros: Decimal
    total: Decimal
    primeira_parcela: Decimal
    ultima_parcela: Decimal
    parcelas: list[Parcela] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "valorTabela": str(self.valor_tabela),
            "desconto": str(self.desconto),
            "valorNegociado": str(self.valor_negociado),
            "entrada": str(self.entrada),
            "baloes": str(self.baloes),
            "saldoFinanciado": str(self.saldo_financiado),
            "totalJuros": str(self.total_juros),
            "total": str(self.total),
            "primeiraParcela": str(self.primeira_parcela),
            "ultimaParcela": str(self.ultima_parcela),
            "parcelas": [p.como_dict() for p in self.parcelas],
        }


# ─── Os dois sistemas de amortização ──────────────────────────────────────────

def price(saldo: Decimal, taxa: Decimal, n: int) -> list[tuple[Decimal, Decimal, Decimal, Decimal]]:
    """Parcela fixa: PMT = PV · i / (1 − (1+i)^−n).

    Devolve (valor, juros, amortização, saldo) por parcela. Com taxa zero
    degenera em saldo ÷ n, que é exatamente a venda "sem juros" — não precisa de
    um terceiro sistema para isso.

    A última parcela absorve a sobra de centavos do arredondamento: sem isso o
    saldo final fica em R$ 0,03 e o título nunca quita.
    """
    if n <= 0:
        return []
    if taxa == 0:
        base = centavos(saldo / n)
        linhas = []
        restante = saldo
        for i in range(n):
            valor = base if i < n - 1 else centavos(restante)
            restante -= valor
            linhas.append((valor, ZERO, valor, centavos(max(restante, ZERO))))
        return linhas

    fator = (1 + taxa) ** n
    pmt = centavos(saldo * taxa * fator / (fator - 1))
    linhas = []
    restante = saldo
    for i in range(n):
        juros = centavos(restante * taxa)
        if i == n - 1:
            # Fecha na última: parcela = saldo + juros do mês, e o saldo zera.
            valor = centavos(restante + juros)
            amortizacao = centavos(restante)
            restante = ZERO
        else:
            valor = pmt
            amortizacao = centavos(valor - juros)
            restante = centavos(restante - amortizacao)
        linhas.append((valor, juros, amortizacao, restante))
    return linhas


def sac(saldo: Decimal, taxa: Decimal, n: int) -> list[tuple[Decimal, Decimal, Decimal, Decimal]]:
    """Amortização constante: a parcela começa maior e cai a cada mês.

    Amortização = saldo ÷ n em todas; os juros incidem sobre o saldo, que
    decresce em linha reta. Paga-se menos juros no total que no Price, à custa
    de uma primeira parcela mais pesada.
    """
    if n <= 0:
        return []
    amortizacao = centavos(saldo / n)
    linhas = []
    restante = saldo
    for i in range(n):
        juros = centavos(restante * taxa)
        if i == n - 1:
            amortizacao_mes = centavos(restante)
        else:
            amortizacao_mes = amortizacao
        valor = centavos(amortizacao_mes + juros)
        restante = centavos(restante - amortizacao_mes)
        linhas.append((valor, juros, amortizacao_mes, max(restante, ZERO)))
    return linhas


SISTEMAS = {"price": price, "sac": sac}


# ─── A proposta inteira ───────────────────────────────────────────────────────

def montar(
    *,
    valor_tabela: Decimal,
    desconto_percentual: Decimal = ZERO,
    desconto_valor: Decimal = ZERO,
    entrada_valor: Decimal = ZERO,
    entrada_parcelas: int = 1,
    entrada_primeiro_vencimento: date | None = None,
    sistema: str = "price",
    juros_mensal: Decimal = ZERO,
    num_parcelas: int = 0,
    primeiro_vencimento: date | None = None,
    balao_valor: Decimal = ZERO,
    balao_quantidade: int = 0,
    balao_periodicidade: str = "anual",
    balao_primeiro_vencimento: date | None = None,
    data_compra: date | None = None,
    a_vista: bool = False,
) -> Plano:
    """A proposta da assinatura: resumo + carnê linha a linha.

    Erros de entrada viram `ValueError` — a tela precisa dizer "a entrada é maior
    que o valor negociado" em vez de gerar um carnê negativo.

    ``a_vista`` não é um sétimo parâmetro de plano: é a **condição de pagamento**
    dizendo que não há plano nenhum. O valor negociado inteiro vence numa
    parcela, na data da compra, e prazo/juros/balões deixam de existir. Fica aqui
    e não na tela porque é a mesma regra que o carnê grava — se a tela decidisse
    sozinha o que é "à vista", a proposta exibida e o título emitido poderiam
    divergir.
    """
    valor_tabela = centavos(Decimal(valor_tabela or 0))
    hoje = data_compra or date.today()

    desconto = centavos(
        Decimal(desconto_valor or 0) + valor_tabela * Decimal(desconto_percentual or 0) / 100
    )
    if desconto > valor_tabela:
        raise ValueError("O desconto não pode ser maior que o valor de tabela.")
    valor_negociado = centavos(valor_tabela - desconto)

    if a_vista:
        entrada_valor = valor_negociado
        entrada_parcelas = 1
        num_parcelas = 0
        juros_mensal = ZERO
        balao_valor = ZERO
        balao_quantidade = 0

    entrada = centavos(Decimal(entrada_valor or 0))
    baloes_total = centavos(Decimal(balao_valor or 0) * int(balao_quantidade or 0))
    if entrada + baloes_total > valor_negociado:
        raise ValueError("Entrada e balões somados passam do valor negociado.")

    saldo = centavos(valor_negociado - entrada - baloes_total)
    if saldo > 0 and num_parcelas <= 0:
        raise ValueError("Sobrou saldo a financiar e nenhuma parcela foi informada.")

    parcelas: list[Parcela] = []

    # Entrada: sem juros, dividida em partes iguais. A sobra de centavos vai na
    # primeira — quem paga o sinal prefere a diferença no ato à surpresa no fim.
    if entrada > 0:
        n_entrada = max(1, int(entrada_parcelas or 1))
        base_entrada = centavos(entrada / n_entrada)
        primeira = entrada_primeiro_vencimento or hoje
        acumulado = ZERO
        for i in range(n_entrada):
            valor = base_entrada if i > 0 else centavos(entrada - base_entrada * (n_entrada - 1))
            acumulado += valor
            parcelas.append(Parcela(
                numero=i + 1, tipo="entrada", vencimento=somar_meses(primeira, i), valor=valor,
                amortizacao=valor,
            ))

    # Saldo financiado.
    calcular = SISTEMAS.get(sistema)
    if calcular is None:
        raise ValueError(f"Sistema de amortização desconhecido: {sistema}")
    taxa = Decimal(juros_mensal or 0) / 100
    if saldo > 0:
        inicio = primeiro_vencimento or somar_meses(hoje, 1)
        for i, (valor, juros, amortizacao, restante) in enumerate(calcular(saldo, taxa, int(num_parcelas))):
            parcelas.append(Parcela(
                numero=i + 1, tipo="parcela", vencimento=somar_meses(inicio, i),
                valor=valor, juros=juros, amortizacao=amortizacao, saldo=restante,
            ))

    # Balões: valor fixo, sem juros (já abateram saldo), a cada 6 ou 12 meses.
    if baloes_total > 0:
        passo = 6 if balao_periodicidade == "semestral" else 12
        inicio_balao = balao_primeiro_vencimento or somar_meses(hoje, passo)
        valor_balao = centavos(Decimal(balao_valor))
        for i in range(int(balao_quantidade)):
            parcelas.append(Parcela(
                numero=i + 1, tipo="balao", vencimento=somar_meses(inicio_balao, i * passo),
                valor=valor_balao, amortizacao=valor_balao,
            ))

    parcelas.sort(key=lambda p: (p.vencimento, p.tipo))
    mensais = [p for p in parcelas if p.tipo == "parcela"]
    total = centavos(sum((p.valor for p in parcelas), ZERO))

    return Plano(
        valor_tabela=valor_tabela,
        desconto=desconto,
        valor_negociado=valor_negociado,
        entrada=entrada,
        baloes=baloes_total,
        saldo_financiado=saldo,
        total_juros=centavos(sum((p.juros for p in parcelas), ZERO)),
        total=total,
        primeira_parcela=mensais[0].valor if mensais else ZERO,
        ultima_parcela=mensais[-1].valor if mensais else ZERO,
        parcelas=parcelas,
    )


def montar_da_aquisicao(aquisicao) -> Plano:
    """O mesmo cálculo, alimentado pelos campos gravados na aquisição."""
    return montar(
        valor_tabela=aquisicao.valor_tabela,
        desconto_percentual=aquisicao.desconto_percentual,
        desconto_valor=aquisicao.desconto_valor,
        entrada_valor=aquisicao.entrada_valor,
        entrada_parcelas=aquisicao.entrada_parcelas,
        entrada_primeiro_vencimento=aquisicao.entrada_primeiro_vencimento,
        sistema=aquisicao.sistema_amortizacao,
        juros_mensal=aquisicao.juros_mensal,
        num_parcelas=aquisicao.num_parcelas,
        primeiro_vencimento=aquisicao.primeiro_vencimento,
        balao_valor=aquisicao.balao_valor,
        balao_quantidade=aquisicao.balao_quantidade,
        balao_periodicidade=aquisicao.balao_periodicidade,
        balao_primeiro_vencimento=aquisicao.balao_primeiro_vencimento,
        data_compra=aquisicao.data_compra,
        a_vista=aquisicao.condicoes_pagamento == "a_vista",
    )


def descricao_da_parcela(parcela: Parcela, total_do_tipo: int) -> str:
    """O texto que o comprador vê no extrato e no boleto."""
    if parcela.tipo == "entrada":
        return f"Entrada {parcela.numero}/{total_do_tipo}"
    if parcela.tipo == "balao":
        return f"Balão {parcela.numero}/{total_do_tipo}"
    return f"Parcela {parcela.numero}/{total_do_tipo}"
