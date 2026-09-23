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

#: Sentinela de "não me disseram nada". `None` já significa **sem calendário**
#: (o contrato cru), então não pode ser o default de quem quer o calendário.
_PADRAO = object()


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
    """Uma linha do carnê. `tipo` diz o que ela é para o comprador.

    `vencimento` é a data **pagável** — já empurrada para o próximo dia útil
    quando a data do contrato cai em sábado, domingo ou feriado. A data do
    contrato não se perde: fica em `vencimento_contratual`, e `ajuste_motivo`
    diz por que as duas diferem ("domingo", "Nossa Senhora Aparecida"). Guardar
    as duas é o que permite a tela explicar o desvio, em vez de mostrar uma data
    que ninguém digitou.
    """
    numero: int
    tipo: str  # entrada | parcela | balao
    vencimento: date
    valor: Decimal
    juros: Decimal = ZERO
    amortizacao: Decimal = ZERO
    saldo: Decimal = ZERO
    vencimento_contratual: date | None = None
    ajuste_motivo: str = ""

    def __post_init__(self):
        if self.vencimento_contratual is None:
            self.vencimento_contratual = self.vencimento

    @property
    def ajustada(self) -> bool:
        return self.vencimento != self.vencimento_contratual

    def como_dict(self) -> dict:
        return {
            "numero": self.numero,
            "tipo": self.tipo,
            "vencimento": self.vencimento.isoformat(),
            "vencimentoContratual": self.vencimento_contratual.isoformat(),
            "ajusteMotivo": self.ajuste_motivo,
            "valor": str(self.valor),
            "juros": str(self.juros),
            "amortizacao": str(self.amortizacao),
            "saldo": str(self.saldo),
        }


@dataclass
class Plano:
    """A proposta fechada: o resumo em dinheiro e o carnê linha a linha.

    `total` é o **total do carnê** — entrada + parcelas + balões, ou seja, tudo
    que a construtora vai cobrar por título. Maior que o negociado quando há
    juros.

    `fora_do_carne` é o resto: o que o comprador paga, mas não à construtora e
    não por boleto — o saldo que o banco quita no financiamento bancário, o bem
    dado em permuta, a parte que passou na maquininha. **Não é desconto e não é
    dívida esquecida**; é valor liquidado por outro caminho, e ele existe como
    campo para que a soma bata: `total + fora_do_carne` cobre o valor negociado.
    Sem ele essas vendas não tinham como ser registradas — o motor as recusava
    por "sobrou saldo sem parcela", que é a descrição de um erro que não existia.
    """
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
    fora_do_carne: Decimal = ZERO
    condicao: str = "financiamento_direto"
    parcelas: list[Parcela] = field(default_factory=list)

    @property
    def quantidade_parcelas(self) -> int:
        """Quantos títulos o carnê vai criar — entrada + parcelas + balões.

        É o número que a confirmação de "Gerar parcelas" mostra **antes** de
        gerar. Sem ele a tela só sabia dizer "gerar parcelas", e quem clicava
        não tinha como conferir o tamanho do que estava criando.
        """
        return len(self.parcelas)

    @property
    def parcelas_ajustadas(self) -> int:
        """Quantas caíam em dia não útil e foram empurradas para a frente."""
        return sum(1 for p in self.parcelas if p.ajustada)

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
            "foraDoCarne": str(self.fora_do_carne),
            "condicao": self.condicao,
            "quantidadeParcelas": self.quantidade_parcelas,
            "parcelasAjustadas": self.parcelas_ajustadas,
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


# ─── O calendário, quando ele é injetado ──────────────────────────────────────

def _normalizar_ajuste(ajustar):
    """Aceita `None`, uma função `date -> date` ou um objeto com `explicar()`.

    O objeto é o caminho bom — ele sabe **por que** empurrou a data, e é esse
    porquê que a tela mostra. A função crua existe para teste e para quem só
    quer a data. `None` é o contrato cru, sem calendário nenhum.
    """
    if ajustar is None:
        return None
    if hasattr(ajustar, "explicar"):
        return ajustar.explicar
    return lambda dia: (ajustar(dia), "")


def _com_ajuste(parcela: Parcela, ajustar) -> Parcela:
    """Aplica o calendário à parcela recém-montada, preservando a data do contrato."""
    if ajustar is None:
        return parcela
    ajustado, motivo = ajustar(parcela.vencimento)
    parcela.vencimento_contratual = parcela.vencimento
    parcela.vencimento = ajustado
    parcela.ajuste_motivo = motivo
    return parcela


# ─── As condições de pagamento, e o que cada uma comporta ─────────────────────
# A condição é a **primeira** pergunta da venda porque é ela que diz quais campos
# existem. Perguntar juros e prazo numa venda à vista não é só ruído: é convidar
# o vendedor a preencher um parcelamento que o contrato não tem, e depois ninguém
# sabe se o que está gravado é o que foi combinado.
#
# A regra mora **aqui**, e não no formulário, pela mesma razão que "à vista" já
# morava: se a tela decidisse sozinha o que cada condição comporta, a proposta
# exibida e o título emitido poderiam divergir — e divergiriam no dia em que
# alguém gravasse pela API, pela importação ou pelo admin.
#
# `quita_fora` é o campo que faltava, e a ausência dele era um defeito com
# sintoma claro: numa **permuta** a construtora não recebe parcela nenhuma, e
# num **financiamento bancário** ela recebe só o sinal — o resto o banco quita.
# Como o motor exigia que todo saldo tivesse parcela, essas vendas eram recusadas
# com "Sobrou saldo a financiar e nenhuma parcela foi informada", que é
# verdadeiro e inútil: o saldo não é para financiar, é para receber por fora.
# Com `quita_fora`, o que sobra vira `fora_do_carne` — um número declarado, que
# a tela mostra, em vez de um erro que trava a venda.


@dataclass(frozen=True)
class Condicao:
    """Uma forma de pagamento e o plano que ela admite."""
    codigo: str
    rotulo: str
    entrada: bool
    parcelas: bool
    baloes: bool
    quita_fora: bool
    nota: str

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "rotulo": self.rotulo,
            "entrada": self.entrada,
            "parcelas": self.parcelas,
            "baloes": self.baloes,
            "quitaFora": self.quita_fora,
            "nota": self.nota,
        }


CONDICOES: dict[str, Condicao] = {
    c.codigo: c for c in (
        Condicao(
            codigo="financiamento_direto", rotulo="Financiamento direto com a construtora",
            entrada=True, parcelas=True, baloes=True, quita_fora=False,
            nota="A construtora financia: entrada, saldo em parcelas e as anuais. "
                 "Tudo o que o comprador deve passa pelo carnê.",
        ),
        Condicao(
            codigo="a_vista", rotulo="À vista",
            entrada=False, parcelas=False, baloes=False, quita_fora=False,
            nota="Pagamento único na data da compra — o valor negociado, sem prazo nem juros.",
        ),
        Condicao(
            codigo="financiamento_bancario", rotulo="Financiamento bancário",
            entrada=True, parcelas=False, baloes=False, quita_fora=True,
            nota="O banco quita o saldo direto com a construtora. No carnê entra só o "
                 "sinal pago à construtora; o restante aparece como quitado fora.",
        ),
        Condicao(
            codigo="permuta", rotulo="Permuta",
            entrada=False, parcelas=False, baloes=False, quita_fora=True,
            nota="Troca por bem ou serviço: não há carnê. Descreva o que foi permutado "
                 "nas observações do contrato.",
        ),
        Condicao(
            codigo="cartao", rotulo="Cartão de crédito/débito",
            entrada=True, parcelas=False, baloes=False, quita_fora=True,
            nota="O parcelamento é da operadora, não do contrato: lance o valor cobrado "
                 "no cartão; o que não passou no cartão fica declarado à parte.",
        ),
        Condicao(
            codigo="outro", rotulo="Outro",
            entrada=True, parcelas=True, baloes=True, quita_fora=True,
            nota="Condição fora do padrão: todos os campos ficam disponíveis, e o que "
                 "sobrar do valor negociado é declarado como quitado fora do carnê.",
        ),
    )
}

#: O que vale quando ninguém disse a condição — chamada crua do motor, código
#: fora do catálogo, dado antigo. É o **financiamento direto**, e a escolha é
#: pela severidade: ele admite todos os campos (nada é apagado por engano) e
#: **não** quita por fora, então um saldo sem parcela continua sendo recusado.
#: Cair no permissivo aqui transformaria um plano incompleto — o erro que este
#: motor existe para pegar — num "pago por fora" silencioso de R$ 40 mil.
CONDICAO_PADRAO = CONDICOES["financiamento_direto"]


def condicao_de(codigo: str | None) -> Condicao:
    return CONDICOES.get(codigo or "", CONDICAO_PADRAO)


def normalizar_por_condicao(codigo: str | None, dados: dict) -> dict:
    """Apaga do plano o que a condição escolhida não comporta.

    Sem isto, mudar uma venda de "financiamento direto" para "à vista" deixaria
    60 parcelas gravadas num contrato que a tela mostra como pagamento único — e
    o carnê sairia com elas. Devolve só o que mudou, para o chamador aplicar.
    """
    condicao = condicao_de(codigo)
    mudancas: dict = {}
    if not condicao.entrada and codigo != "a_vista":
        mudancas.update(entrada_valor=ZERO, entrada_parcelas=1, entrada_primeiro_vencimento=None)
    if not condicao.parcelas:
        mudancas.update(num_parcelas=0, juros_mensal=ZERO, primeiro_vencimento=None)
    if not condicao.baloes:
        mudancas.update(balao_valor=ZERO, balao_quantidade=0, balao_primeiro_vencimento=None)
    return {campo: valor for campo, valor in mudancas.items() if dados.get(campo) != valor}


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
    condicoes_pagamento: str | None = None,
    ajustar_vencimento=None,
) -> Plano:
    """A proposta da assinatura: resumo + carnê linha a linha.

    Erros de entrada viram `ValueError` — a tela precisa dizer "a entrada é maior
    que o valor negociado" em vez de gerar um carnê negativo.

    ``condicoes_pagamento`` não é um sétimo parâmetro de plano: é o que diz
    **quais** parâmetros existem. "À vista" não tem prazo — o valor negociado
    inteiro vence numa parcela, na data da compra; permuta não tem carnê;
    financiamento bancário só tem o sinal. O catálogo está em ``CONDICOES``, e
    fica aqui e não na tela porque é a mesma regra que o carnê grava: se a tela
    decidisse sozinha o que cada condição comporta, a proposta exibida e o título
    emitido poderiam divergir — e divergiriam no primeiro POST feito fora dela.

    Quando a condição **quita fora** (banco, permuta, cartão), o que sobra do
    valor negociado depois de entrada e balões não é erro: é ``fora_do_carne``.
    Só a condição que promete financiar tudo — financiamento direto — continua
    recusando saldo sem parcela, porque aí a falta é real.

    ``ajustar_vencimento`` é o **calendário bancário injetado**: uma função
    ``date -> date`` (na prática, ``modulocalendar.dias_uteis.AjusteDeVencimento``)
    que empurra para o próximo dia útil a parcela que cai em sábado, domingo ou
    feriado. Entra por parâmetro, e não por import, para este módulo continuar
    puro — ele faz a conta, quem sabe onde fica o imóvel é ``clientes.vencimento``.
    Sem ele, o cálculo é o do contrato cru, que é o que os testes de matemática
    querem.

    **O ajuste é só da data, nunca do valor.** Juros correm por parcela, não por
    dia corrido: empurrar o vencimento de 13/04 para 14/04 não acrescenta um dia
    de juro — se acrescentasse, o carnê exibido na venda não fecharia com o
    carnê emitido, e a diferença apareceria como centavos inexplicáveis.
    """
    valor_tabela = centavos(Decimal(valor_tabela or 0))
    hoje = data_compra or date.today()
    condicao = condicao_de(condicoes_pagamento)

    desconto = centavos(
        Decimal(desconto_valor or 0) + valor_tabela * Decimal(desconto_percentual or 0) / 100
    )
    if desconto > valor_tabela:
        raise ValueError("O desconto não pode ser maior que o valor de tabela.")
    valor_negociado = centavos(valor_tabela - desconto)

    if condicao.codigo == "a_vista":
        entrada_valor = valor_negociado
        entrada_parcelas = 1
        entrada_primeiro_vencimento = entrada_primeiro_vencimento or hoje
        num_parcelas = 0
        juros_mensal = ZERO
        balao_valor = ZERO
        balao_quantidade = 0
    else:
        # O que a condição não comporta não entra na conta, venha de onde vier
        # (formulário antigo, PATCH parcial, importação). É a mesma limpeza que a
        # tela faz ao trocar a condição — feita de novo aqui porque a tela não é
        # a única porta.
        if not condicao.entrada:
            entrada_valor, entrada_parcelas = ZERO, 1
        if not condicao.parcelas:
            num_parcelas, juros_mensal = 0, ZERO
        if not condicao.baloes:
            balao_valor, balao_quantidade = ZERO, 0

    entrada = centavos(Decimal(entrada_valor or 0))
    baloes_total = centavos(Decimal(balao_valor or 0) * int(balao_quantidade or 0))
    if entrada + baloes_total > valor_negociado:
        raise ValueError("Entrada e balões somados passam do valor negociado.")

    saldo = centavos(valor_negociado - entrada - baloes_total)
    fora_do_carne = ZERO
    if saldo > 0 and num_parcelas <= 0:
        if not condicao.quita_fora:
            raise ValueError("Sobrou saldo a financiar e nenhuma parcela foi informada.")
        # Pago por fora: o banco, a permuta, a operadora do cartão. Sai do saldo
        # a financiar e vira um número declarado — nem título, nem desconto.
        fora_do_carne, saldo = saldo, ZERO

    parcelas: list[Parcela] = []
    ajustar = _normalizar_ajuste(ajustar_vencimento)

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
            parcelas.append(_com_ajuste(
                Parcela(
                    numero=i + 1, tipo="entrada", vencimento=somar_meses(primeira, i), valor=valor,
                    amortizacao=valor,
                ),
                ajustar,
            ))

    # Saldo financiado.
    calcular = SISTEMAS.get(sistema)
    if calcular is None:
        raise ValueError(f"Sistema de amortização desconhecido: {sistema}")
    taxa = Decimal(juros_mensal or 0) / 100
    if saldo > 0:
        inicio = primeiro_vencimento or somar_meses(hoje, 1)
        for i, (valor, juros, amortizacao, restante) in enumerate(calcular(saldo, taxa, int(num_parcelas))):
            parcelas.append(_com_ajuste(
                Parcela(
                    numero=i + 1, tipo="parcela", vencimento=somar_meses(inicio, i),
                    valor=valor, juros=juros, amortizacao=amortizacao, saldo=restante,
                ),
                ajustar,
            ))

    # Balões: valor fixo, sem juros (já abateram saldo), a cada 6 ou 12 meses.
    if baloes_total > 0:
        passo = 6 if balao_periodicidade == "semestral" else 12
        inicio_balao = balao_primeiro_vencimento or somar_meses(hoje, passo)
        valor_balao = centavos(Decimal(balao_valor))
        for i in range(int(balao_quantidade)):
            parcelas.append(_com_ajuste(
                Parcela(
                    numero=i + 1, tipo="balao", vencimento=somar_meses(inicio_balao, i * passo),
                    valor=valor_balao, amortizacao=valor_balao,
                ),
                ajustar,
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
        fora_do_carne=fora_do_carne,
        condicao=condicao.codigo,
        parcelas=parcelas,
    )


def montar_da_aquisicao(aquisicao, *, ajustar_vencimento=_PADRAO) -> Plano:
    """O mesmo cálculo, alimentado pelos campos gravados na aquisição.

    O calendário bancário entra por padrão, resolvido pela praça do imóvel
    (`clientes.vencimento`): é o carnê que o comprador vai receber, e nele não
    existe boleto vencendo no domingo. Passar `ajustar_vencimento=None` devolve
    o contrato cru — o caminho de quem testa a matemática, não a emissão.
    """
    if ajustar_vencimento is _PADRAO:
        from .vencimento import ajuste_da_aquisicao

        ajustar_vencimento = ajuste_da_aquisicao(aquisicao)
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
        condicoes_pagamento=aquisicao.condicoes_pagamento,
        ajustar_vencimento=ajustar_vencimento,
    )


def descricao_da_parcela(parcela: Parcela, total_do_tipo: int) -> str:
    """O que a parcela é: "Parcela 32/36", "Entrada 2/3", "Balão 1/5"."""
    if parcela.tipo == "entrada":
        return f"Entrada {parcela.numero}/{total_do_tipo}"
    if parcela.tipo == "balao":
        return f"Balão {parcela.numero}/{total_do_tipo}"
    return f"Parcela {parcela.numero}/{total_do_tipo}"


def descricao_do_titulo(parcela: Parcela, total_do_tipo: int, aquisicao) -> str:
    """O texto que o comprador lê no extrato e **no boleto**.

    Sai daqui — e não do laço de quem gera — porque são três chamadores (a
    geração do carnê, o semeador da demo e qualquer recomposição futura) e o
    texto tem de ser o mesmo nos três: é o que o cliente confere no banco.

    **O empreendimento vem antes da unidade.** "Parcela 32/36 — QD 4 · LT 06"
    identifica o lote para quem já sabe de que loteamento se fala; quem recebe o
    boleto pode ter comprado em dois, e a quadra 4 existe em ambos. Com o nome do
    empreendimento na frente, o título se explica sozinho — que é o único jeito
    de um boleto se explicar, porque ele chega sem a tela em volta.
    """
    partes = [descricao_da_parcela(parcela, total_do_tipo), "—"]
    empreendimento = getattr(aquisicao, "empreendimento", None)
    nome = getattr(empreendimento, "empreendimento", "") or ""
    rotulo = aquisicao.unidade.rotulo
    partes.append(f"{nome} · {rotulo}" if nome else rotulo)
    return " ".join(partes)
