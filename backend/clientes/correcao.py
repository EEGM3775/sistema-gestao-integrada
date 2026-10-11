"""Correção monetária do contrato: da data-base ao valor que o boleto carrega.

**Como o mercado faz — e por que aqui é igual.** Um contrato de loteamento ou
incorporação dura de 5 a 15 anos. Sem índice, a parcela do último ano é, em poder
de compra, uma fração da do primeiro: o vendedor concede um desconto que nunca
negociou. Por isso todo contrato do setor traz cláusula de reajuste, e os
sistemas de referência (Sienge, UAU, Mega) implementam a mesma mecânica:

1. **A âncora é o contrato, não o boleto.** O reajuste conta da **data-base** — em
   regra a data da compra — e incide no **aniversário** dela. O boleto é o
   portador, não o marco: emitir a cobrança em outro dia não move o reajuste.
   Ancorar na emissão faria o mesmo contrato render valores diferentes conforme o
   dia em que o financeiro rodou a régua de cobrança, que é exatamente o defeito
   que o aniversário existe para evitar.
2. **Anual é o padrão** (a lei só permite reajuste em periodicidade inferior a um
   ano em casos específicos); **mensal** existe para o INCC durante a obra, que é
   prática consolidada em incorporação.
3. **Corrige-se o saldo devedor**, e a parcela sai dele já corrigida. O que já foi
   pago não volta atrás.
4. **O índice usado é o publicado**, e publicação tem defasagem: o IPCA de julho
   sai em agosto. Por isso o fator só compõe as competências que **existem na
   série** — nunca projeta, nunca chuta. Se falta mês, o acumulado é o que dá
   para provar, e o retorno diz até onde foi.

Deflação entra igual: variação negativa reduz o valor. Um motor que só sobe
inventaria correção onde o índice não deu.

Funções puras sobre a série — não gravam nada. Quem persiste é a view.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from nucleo.models import ValorIndice

CEM = Decimal("100")
UM = Decimal("1")
CENTAVO = Decimal("0.01")
# O fator acumula multiplicações mês a mês; arredondar a cada passo empurraria o
# erro para dentro do dinheiro. Oito casas é folga suficiente para 15 anos.
CASAS_FATOR = Decimal("0.00000001")


def primeiro_do_mes(d: date) -> date:
    return date(d.year, d.month, 1)


def meses_entre(inicio: date, fim: date) -> int:
    """Quantos meses cheios separam duas datas (pelo mês-competência)."""
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month)


@dataclass
class Correcao:
    """O resultado, com a memória de cálculo junto.

    `competencias_aplicadas` e `ate_competencia` existem para a conta ser
    auditável: sem elas, o cliente que pergunta "por que minha parcela subiu"
    recebe um número sem origem.
    """
    valor_original: Decimal
    valor_corrigido: Decimal
    fator: Decimal
    indice: str
    data_base: date
    ate_competencia: date | None
    competencias_aplicadas: int
    meses_faltando_na_serie: int

    @property
    def acrescimo(self) -> Decimal:
        return self.valor_corrigido - self.valor_original

    def como_dict(self) -> dict:
        return {
            "valorOriginal": str(self.valor_original),
            "valorCorrigido": str(self.valor_corrigido),
            "acrescimo": str(self.acrescimo),
            "fator": str(self.fator),
            "indice": self.indice,
            "dataBase": self.data_base.isoformat(),
            "ateCompetencia": self.ate_competencia.isoformat() if self.ate_competencia else None,
            "competenciasAplicadas": self.competencias_aplicadas,
            "mesesFaltandoNaSerie": self.meses_faltando_na_serie,
        }


def serie(indice, de: date, ate: date) -> dict[date, Decimal]:
    """As variações publicadas no intervalo `[de, ate]`, por competência.

    Uma consulta só: compor 120 meses com um SELECT por mês transformaria o
    reajuste de uma carteira inteira em milhares de idas ao banco.
    """
    if indice is None or de > ate:
        return {}
    linhas = ValorIndice.objects.filter(
        indice=indice, competencia__gte=primeiro_do_mes(de), competencia__lte=primeiro_do_mes(ate),
        variacao_percentual__isnull=False,
    ).values_list("competencia", "variacao_percentual")
    return {competencia: Decimal(variacao) for competencia, variacao in linhas}


def fator_acumulado(indice, de: date, ate: date) -> tuple[Decimal, int, date | None, int]:
    """Compõe as variações mensais de `de` (inclusive) até `ate` (inclusive).

    Composto, não somado: 1% em dois meses é 2,01%, não 2%. Somar subestima o
    reajuste de contrato longo — e a diferença cresce com o prazo, que é
    justamente onde o contrato dói.

    Devolve `(fator, competências aplicadas, última competência usada, meses
    ausentes da série)`.
    """
    if indice is None:
        return UM, 0, None, 0

    inicio, fim = primeiro_do_mes(de), primeiro_do_mes(ate)
    if inicio > fim:
        return UM, 0, None, 0

    publicadas = serie(indice, inicio, fim)
    esperados = meses_entre(inicio, fim) + 1

    fator = UM
    ultima = None
    for competencia, variacao in sorted(publicadas.items()):
        fator *= UM + variacao / CEM
        ultima = competencia

    return (
        fator.quantize(CASAS_FATOR, rounding=ROUND_HALF_UP),
        len(publicadas),
        ultima,
        esperados - len(publicadas),
    )


def aniversario_vigente(data_base: date, referencia: date) -> date | None:
    """O último aniversário do contrato até `referencia`.

    É o marco do reajuste anual: antes do primeiro aniversário não há correção
    nenhuma, e entre um aniversário e o seguinte o valor fica **parado**. Devolve
    `None` no primeiro ano — o contrato ainda está no valor de assinatura.
    """
    anos = referencia.year - data_base.year
    if (referencia.month, referencia.day) < (data_base.month, data_base.day):
        anos -= 1
    if anos < 1:
        return None
    try:
        return data_base.replace(year=data_base.year + anos)
    except ValueError:
        # 29/02 em ano comum: o aniversário cai em 28/02, como nos contratos.
        return data_base.replace(year=data_base.year + anos, day=28)


def corrigir(
    valor: Decimal,
    *,
    indice,
    data_base: date,
    referencia: date,
    periodicidade: str = "anual",
) -> Correcao:
    """O valor de `valor` trazido da data-base até `referencia`.

    `referencia` é **a data em que o valor vai ser cobrado** — o vencimento da
    parcela ou o dia do lançamento do boleto. É o único papel da data do boleto
    nesta conta: dizer até quando trazer o índice. Ela não vira âncora.

    - **anual**: corrige no aniversário e fica parada até o próximo. O fator vai
      da data-base até o mês **anterior** ao aniversário vigente — é o acumulado
      dos 12 meses do período, que é o que a cláusula manda.
    - **mensal**: acumula até o mês anterior ao da referência. Não se usa o mês
      corrente porque ele ainda não foi publicado.
    """
    valor = Decimal(valor or 0)
    codigo = getattr(indice, "codigo", "") or ""

    if indice is None or valor <= 0:
        return Correcao(
            valor_original=valor, valor_corrigido=valor, fator=UM, indice=codigo,
            data_base=data_base, ate_competencia=None,
            competencias_aplicadas=0, meses_faltando_na_serie=0,
        )

    if periodicidade == "mensal":
        limite = mes_anterior(referencia)
    else:
        aniversario = aniversario_vigente(data_base, referencia)
        if aniversario is None:
            return Correcao(
                valor_original=valor, valor_corrigido=valor, fator=UM, indice=codigo,
                data_base=data_base, ate_competencia=None,
                competencias_aplicadas=0, meses_faltando_na_serie=0,
            )
        limite = mes_anterior(aniversario)

    fator, aplicadas, ultima, faltando = fator_acumulado(indice, data_base, limite)
    corrigido = (valor * fator).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    return Correcao(
        valor_original=valor, valor_corrigido=corrigido, fator=fator, indice=codigo,
        data_base=data_base, ate_competencia=ultima,
        competencias_aplicadas=aplicadas, meses_faltando_na_serie=faltando,
    )


def mes_anterior(d: date) -> date:
    """O dia 1 do mês anterior — o último mês com índice publicado."""
    primeiro = primeiro_do_mes(d)
    if primeiro.month == 1:
        return date(primeiro.year - 1, 12, 1)
    return date(primeiro.year, primeiro.month - 1, 1)


def corrigir_da_aquisicao(aquisicao, valor: Decimal, referencia: date) -> Correcao:
    """O mesmo cálculo, alimentado pelo contrato gravado."""
    return corrigir(
        valor,
        indice=aquisicao.indice_correcao,
        data_base=aquisicao.data_base_efetiva,
        referencia=referencia,
        periodicidade=aquisicao.periodicidade_correcao,
    )
