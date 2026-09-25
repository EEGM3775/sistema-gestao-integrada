"""O motor da proposta: do preço de tabela ao carnê do comprador.

Como o mercado monta uma venda de unidade:

    valor de tabela
      − desconto (% ou R$)                    → valor negociado (o "à vista")
      = soma dos **meios de pagamento**, cada um com o seu plano:
          entrada / ATO (parcelável; sem juros, salvo se o contrato cobrar)
          financiamento direto: N mensais com juros a.m., **Price** ou **SAC**
          anuais/intercaladas (a cada 6 ou 12 meses), que **somam** à mensal
          à vista, cartão
          financiamento bancário, FGTS, permuta, outro — quitados fora do carnê

A venda não tem mais **uma** condição de pagamento: tem uma lista livre de meios,
e a conta só fecha quando a soma deles é o valor negociado — nem um centavo a
mais, nem a menos. Uma venda real de incorporadora é quase sempre combinada
(sinal + mensais + anuais + banco na entrega), e uma condição única obrigava o
vendedor a escolher uma e deixar o resto como "quitado fora do carnê".

Três decisões que este módulo assume, e por quê:

- **A entrada, por padrão, não rende juros.** Ela é sinal, não financiamento — o
  dinheiro entra antes da entrega, e a entrada curta (ato + poucas vezes) é
  vendida sem juros no mercado. A entrada **longa** às vezes cobra: por isso o
  meio "entrada" aceita uma taxa opcional, que parte de zero.
- **Cada meio carrega só o seu principal.** As anuais não pagam os juros do
  financiamento direto, porque são outro meio, com o seu valor; o comprador não
  paga juros sobre o que se comprometeu a quitar à parte.
- **Juros correm a partir da 1ª parcela do meio**, não da data da venda. É a
  configuração que os sistemas do setor chamam de "juros inicia na 1ª parcela",
  e a que o comprador entende.

A correção monetária (INCC/IGP-M/IPCA) é contrato vivo e mora em
``clientes.correcao``: o que este módulo devolve é o **plano na data da
assinatura**.

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
    tipo: str  # a_vista | entrada | parcela | balao | cartao
    vencimento: date
    valor: Decimal
    juros: Decimal = ZERO
    amortizacao: Decimal = ZERO
    saldo: Decimal = ZERO
    vencimento_contratual: date | None = None
    ajuste_motivo: str = ""
    #: A ordem (1, 2, 3…) do meio de pagamento que gerou a linha. É o que
    #: separa as duas séries de "Parcela 1/24" quando a venda tem dois
    #: financiamentos diretos.
    meio: int = 1

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
            "meio": self.meio,
        }


@dataclass
class Plano:
    """A proposta fechada: o resumo em dinheiro e o carnê linha a linha.

    `total` é o **total a receber pela construtora** — a soma dos títulos que
    os meios dela geram (à vista, entrada, mensais, anuais, cartão). Maior que
    o negociado quando há juros.

    `fora_do_carne` é a soma dos meios que **não** viram título: o que o banco
    quita, o FGTS, o bem da permuta, o "outro" explicado em texto. Não é desconto
    nem dívida esquecida — `total − total_juros + fora_do_carne` é o valor
    negociado. A tela não mostra este número com esse nome: mostra **cada meio**
    com o nome dele (`meios`), porque "quitado fora do carnê" não diz ao
    comprador se o dinheiro é do banco ou do carro que ele deu na troca.
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
    meios: list["ResumoDoMeio"] = field(default_factory=list)

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
            "meios": [m.como_dict() for m in self.meios],
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




# ─── Os meios de pagamento, e o que cada um comporta ──────────────────────────
# A venda é uma **lista livre** de meios: o vendedor acrescenta quantos a
# negociação tiver ("+ Adicionar meio de pagamento"), e cada um traz só os campos
# que ele comporta. Perguntar juros num FGTS ou prazo numa permuta não é só
# ruído: é convidar o vendedor a preencher um parcelamento que o contrato não
# tem, e depois ninguém sabe se o que está gravado é o que foi combinado.
#
# A regra mora **aqui**, e não no formulário: se a tela decidisse sozinha o que
# cada meio comporta, a proposta exibida e o título emitido poderiam divergir —
# e divergiriam no dia em que alguém gravasse pela API, pela importação ou pelo
# admin. A tela lê este catálogo em `GET /api/clientes-empreendimentos/condicoes/`.
#
# `no_carne` separa os meios que viram título a receber da construtora dos que
# são quitados por outro caminho (banco, FGTS, permuta, outro). Os segundos
# existem como meio — com valor e nome — para a conta fechar sem esconder de
# onde vem o dinheiro: antes eles eram um resto sem nome, "quitado fora do
# carnê", calculado por diferença.


@dataclass(frozen=True)
class TipoDeMeio:
    """Uma forma de pagamento e os campos que ela admite."""
    codigo: str
    #: Como aparece no seletor.
    rotulo: str
    #: Como aparece no resumo da proposta — o nome do dinheiro, não do campo:
    #: "Financiado pelo banco", e não "Quitado fora do carnê".
    rotulo_resumo: str
    #: Gera título a receber da construtora (entra no financeiro)?
    no_carne: bool
    #: Tipo das linhas do carnê (`Parcela.tipo`); vazio quando não há carnê.
    tipo_parcela: str
    #: A condição da carteira a que o meio pertence — é por ela que a venda
    #: inteira ganha um rótulo (ver `condicao_da_venda`).
    condicao: str
    nota: str
    parcelas: bool = False
    rotulo_parcelas: str = ""
    juros: bool = False
    sistema: bool = False
    periodicidade: bool = False
    vencimento: bool = False
    rotulo_vencimento: str = ""
    #: "obrigatoria", "opcional" ou "" (o meio não tem descrição).
    descricao: str = "opcional"
    rotulo_descricao: str = "Observação"

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "rotulo": self.rotulo,
            "rotuloResumo": self.rotulo_resumo,
            "noCarne": self.no_carne,
            "condicao": self.condicao,
            "nota": self.nota,
            "parcelas": self.parcelas,
            "rotuloParcelas": self.rotulo_parcelas,
            "juros": self.juros,
            "sistema": self.sistema,
            "periodicidade": self.periodicidade,
            "vencimento": self.vencimento,
            "rotuloVencimento": self.rotulo_vencimento,
            "descricao": self.descricao,
            "rotuloDescricao": self.rotulo_descricao,
        }


TIPOS_DE_MEIO: dict[str, TipoDeMeio] = {
    t.codigo: t for t in (
        TipoDeMeio(
            codigo="a_vista", descricao="", rotulo="À vista", rotulo_resumo="À vista",
            no_carne=True, tipo_parcela="a_vista", condicao="a_vista",
            vencimento=True, rotulo_vencimento="Data do pagamento",
            nota="Pagamento único à construtora, sem prazo nem juros.",
        ),
        TipoDeMeio(
            codigo="entrada", descricao="", rotulo="Entrada / sinal (ATO)", rotulo_resumo="Entrada",
            no_carne=True, tipo_parcela="entrada", condicao="financiamento_direto",
            parcelas=True, rotulo_parcelas="Em quantas vezes", juros=True,
            vencimento=True, rotulo_vencimento="1º vencimento",
            nota="Sinal pago à construtora. Sem juros por padrão — a entrada curta é "
                 "vendida assim; preencha a taxa só se o contrato cobrar juros da "
                 "entrada parcelada.",
        ),
        TipoDeMeio(
            codigo="financiamento_direto", descricao="", rotulo="Financiamento direto (construtora)",
            rotulo_resumo="Financiado pela construtora",
            no_carne=True, tipo_parcela="parcela", condicao="financiamento_direto",
            parcelas=True, rotulo_parcelas="Nº de parcelas", juros=True, sistema=True,
            vencimento=True, rotulo_vencimento="1º vencimento",
            nota="A construtora financia este valor em parcelas mensais, pelo Price "
                 "(parcela fixa) ou SAC (decrescente).",
        ),
        TipoDeMeio(
            codigo="anuais", descricao="", rotulo="Parcelas anuais (intercaladas)",
            rotulo_resumo="Anuais / intercaladas",
            no_carne=True, tipo_parcela="balao", condicao="financiamento_direto",
            parcelas=True, rotulo_parcelas="Quantas", periodicidade=True,
            vencimento=True, rotulo_vencimento="1º vencimento",
            nota="Reforços periódicos que somam à mensal do mês em que caem. Não pagam "
                 "juros: são um meio à parte, com o seu próprio valor.",
        ),
        TipoDeMeio(
            codigo="financiamento_bancario", rotulo="Financiamento bancário",
            rotulo_resumo="Financiado pelo banco",
            no_carne=False, tipo_parcela="", condicao="financiamento_bancario",
            rotulo_descricao="Banco",
            nota="O banco quita este valor direto com a construtora — não gera boleto.",
        ),
        TipoDeMeio(
            codigo="fgts", descricao="", rotulo="FGTS", rotulo_resumo="Pago com FGTS",
            no_carne=False, tipo_parcela="", condicao="financiamento_bancario",
            nota="Saque do FGTS liberado pela Caixa para a construtora — não gera boleto.",
        ),
        TipoDeMeio(
            codigo="permuta", rotulo="Permuta", rotulo_resumo="Pago em permuta",
            no_carne=False, tipo_parcela="", condicao="permuta",
            descricao="obrigatoria", rotulo_descricao="O que foi dado em permuta",
            nota="Bem ou serviço aceito como pagamento, pelo valor de avaliação.",
        ),
        TipoDeMeio(
            codigo="cartao", descricao="", rotulo="Cartão de crédito/débito", rotulo_resumo="Pago no cartão",
            no_carne=True, tipo_parcela="cartao", condicao="cartao",
            parcelas=True, rotulo_parcelas="Vezes na operadora",
            vencimento=True, rotulo_vencimento="Data da cobrança",
            nota="Um título a receber da operadora. O parcelamento do comprador é da "
                 "operadora, não do contrato — o número de vezes fica só registrado.",
        ),
        TipoDeMeio(
            codigo="outro", rotulo="Outro", rotulo_resumo="Outro",
            no_carne=False, tipo_parcela="", condicao="outro",
            descricao="obrigatoria", rotulo_descricao="Explique a condição",
            nota="Condição fora do padrão: descreva por extenso como este valor é pago. "
                 "Não gera boleto.",
        ),
    )
}



@dataclass
class Meio:
    """Um meio de pagamento da proposta, já com os tipos do Python.

    Os campos são os mesmos do modelo `MeioPagamento`, para o mesmo `meio_de()`
    ler do payload da simulação e do registro gravado.
    """
    tipo: str
    valor: Decimal
    descricao: str = ""
    parcelas: int = 1
    primeiro_vencimento: date | None = None
    juros_mensal: Decimal = ZERO
    sistema_amortizacao: str = "price"
    periodicidade: str = "anual"

    @property
    def catalogo(self) -> TipoDeMeio:
        return TIPOS_DE_MEIO[self.tipo]


def _ler(origem, campo, padrao=None):
    if isinstance(origem, dict):
        valor = origem.get(campo, padrao)
    else:
        valor = getattr(origem, campo, padrao)
    return padrao if valor in (None, "") else valor


def _data(valor) -> date | None:
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ValueError(f"Data inválida: {valor}.") from None


def meio_de(origem, ordem: int = 1) -> Meio:
    """Lê um meio do payload (dict) ou do registro (modelo) e **apaga o que o
    tipo não comporta**.

    A limpeza é aqui, e não só na tela, porque a tela não é a única porta: um
    FGTS que chegue pela API com 60 parcelas e juros de 2% não pode sair do
    registro com eles — o carnê não os usaria, mas a ficha os mostraria.
    """
    tipo = _ler(origem, "tipo", "")
    catalogo = TIPOS_DE_MEIO.get(tipo)
    if catalogo is None:
        raise ValueError(f"Meio {ordem}: forma de pagamento desconhecida ({tipo or 'vazia'}).")
    try:
        valor = centavos(Decimal(str(_ler(origem, "valor", 0))))
        parcelas = int(_ler(origem, "parcelas", 1))
        juros = Decimal(str(_ler(origem, "juros_mensal", 0)))
    except (ArithmeticError, ValueError, TypeError):
        raise ValueError(f"{_nome(catalogo, ordem)}: número inválido.") from None
    return Meio(
        tipo=tipo,
        valor=valor,
        descricao=str(_ler(origem, "descricao", "")).strip() if catalogo.descricao else "",
        parcelas=parcelas if catalogo.parcelas else 1,
        primeiro_vencimento=_data(_ler(origem, "primeiro_vencimento")) if catalogo.vencimento else None,
        # Entrada em 1x não tem prazo sobre o qual correr juro.
        juros_mensal=juros if catalogo.juros and not (tipo == "entrada" and parcelas <= 1) else ZERO,
        sistema_amortizacao=(
            _ler(origem, "sistema_amortizacao", "price") if catalogo.sistema else "price"
        ),
        periodicidade=(
            _ler(origem, "periodicidade", "anual") if catalogo.periodicidade else "anual"
        ),
    )


def condicao_da_venda(meios: list[Meio]) -> str:
    """Como a venda inteira aparece na carteira, nos filtros e na ficha.

    É a condição que responde pela **maior parte do valor**. Entrada, mensais e
    anuais somam juntas — são as três partes do mesmo financiamento direto —, e
    por isso "sinal de 30 mil + banco de 270 mil" é financiamento bancário, que
    é como o mercado chama essa venda. Um rótulo "combinado" seria verdadeiro e
    inútil: quase toda venda de incorporadora é combinada, e o filtro da
    carteira por "financiamento bancário" deixaria de achar as vendas pelo banco.
    Empate fica com o meio que veio primeiro.
    """
    peso: dict[str, Decimal] = {}
    for m in meios:
        peso[m.catalogo.condicao] = peso.get(m.catalogo.condicao, ZERO) + m.valor
    if not peso:
        return "financiamento_direto"
    return max(peso, key=lambda c: peso[c])  # `max` devolve o primeiro no empate


def brl(valor: Decimal) -> str:
    """R$ 1.234,56 — as mensagens de erro são lidas pelo vendedor, não pelo dev."""
    texto = f"{centavos(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def _nome(meio_ou_tipo, ordem: int) -> str:
    """ "Meio 2 (Financiamento direto)" — o rótulo do seletor sem o parêntese
    dele, para a mensagem não virar "(Entrada / sinal (ATO))"."""
    catalogo = getattr(meio_ou_tipo, "catalogo", meio_ou_tipo)
    return f"Meio {ordem} ({catalogo.rotulo.split(' (')[0]})"


def _validar_meio(meio: Meio, ordem: int) -> None:
    nome = _nome(meio, ordem)
    if meio.valor <= 0:
        raise ValueError(f"{nome}: informe o valor.")
    if meio.catalogo.parcelas and meio.parcelas < 1:
        raise ValueError(f"{nome}: informe em quantas vezes.")
    if meio.juros_mensal < 0:
        raise ValueError(f"{nome}: a taxa de juros não pode ser negativa.")
    if meio.sistema_amortizacao not in SISTEMAS:
        raise ValueError(f"{nome}: sistema de amortização desconhecido.")
    if meio.periodicidade not in ("anual", "semestral"):
        raise ValueError(f"{nome}: periodicidade desconhecida.")
    if meio.catalogo.descricao == "obrigatoria" and not meio.descricao:
        raise ValueError(f"{nome}: {meio.catalogo.rotulo_descricao.lower()} — é obrigatório.")


# ─── O resumo de cada meio ────────────────────────────────────────────────────

@dataclass
class ResumoDoMeio:
    """Uma linha do resumo da proposta: o meio, pelo nome do dinheiro."""
    ordem: int
    tipo: str
    rotulo: str
    detalhe: str
    descricao: str
    valor: Decimal
    no_carne: bool
    juros: Decimal
    total: Decimal
    quantidade: int
    primeira_parcela: Decimal
    ultima_parcela: Decimal

    def como_dict(self) -> dict:
        return {
            "ordem": self.ordem,
            "tipo": self.tipo,
            "rotulo": self.rotulo,
            "detalhe": self.detalhe,
            "descricao": self.descricao,
            "valor": str(self.valor),
            "noCarne": self.no_carne,
            "juros": str(self.juros),
            "total": str(self.total),
            "quantidade": self.quantidade,
            "primeiraParcela": str(self.primeira_parcela),
            "ultimaParcela": str(self.ultima_parcela),
        }


def _taxa_legivel(juros: Decimal) -> str:
    return f"{juros.normalize():f}".replace(".", ",") + "% a.m."


def _detalhe(meio: Meio, linhas: list[Parcela]) -> str:
    """O "como" do meio em meia linha: "60x Price, 1% a.m.", "3x sem juros"."""
    t = meio.tipo
    if t == "financiamento_direto":
        sistema = "SAC" if meio.sistema_amortizacao == "sac" else "Price"
        juros = _taxa_legivel(meio.juros_mensal) if meio.juros_mensal > 0 else "sem juros"
        return f"{meio.parcelas}x {sistema}, {juros}"
    if t == "entrada":
        if meio.parcelas == 1:
            return "no ato"
        juros = _taxa_legivel(meio.juros_mensal) if meio.juros_mensal > 0 else "sem juros"
        return f"{meio.parcelas}x {juros}"
    if t == "anuais":
        passo = "semestrais" if meio.periodicidade == "semestral" else "anuais"
        return f"{meio.parcelas} {passo} de {brl(linhas[-1].valor) if linhas else brl(ZERO)}"
    if t == "cartao":
        return f"{meio.parcelas}x na operadora" if meio.parcelas > 1 else "à vista na operadora"
    return ""


def _rotulo(meio: Meio) -> str:
    """"Financiado pelo banco — Caixa", "Pago em permuta — Gol 2019", "Outro —
    3 cheques pré-datados". A descrição vem junto quando ela é o que diz o que
    o meio é; no resto, ela fica em `descricao` para quem quiser mostrar."""
    base = meio.catalogo.rotulo_resumo
    if meio.descricao and meio.tipo in ("financiamento_bancario", "permuta", "outro"):
        return f"{base} — {meio.descricao}"
    return base


# ─── A proposta inteira ───────────────────────────────────────────────────────

def _linhas_do_meio(meio: Meio, ordem: int, hoje: date) -> list[Parcela]:
    """O carnê de um meio só, na data do contrato (sem calendário)."""
    t = meio.tipo
    tipo = meio.catalogo.tipo_parcela
    if not meio.catalogo.no_carne:
        return []
    if t in ("a_vista", "cartao"):
        return [Parcela(
            numero=1, tipo=tipo, vencimento=meio.primeiro_vencimento or hoje,
            valor=meio.valor, amortizacao=meio.valor, meio=ordem,
        )]

    if t == "financiamento_direto" or (t == "entrada" and meio.juros_mensal > 0):
        # A entrada com juros é um pequeno Price: mesma conta, outro nome no carnê.
        calcular = SISTEMAS[meio.sistema_amortizacao]
        taxa = meio.juros_mensal / 100
        inicio = meio.primeiro_vencimento or (somar_meses(hoje, 1) if t == "financiamento_direto" else hoje)
        return [
            Parcela(
                numero=i + 1, tipo=tipo, vencimento=somar_meses(inicio, i),
                valor=valor, juros=juros, amortizacao=amortizacao, saldo=restante, meio=ordem,
            )
            for i, (valor, juros, amortizacao, restante)
            in enumerate(calcular(meio.valor, taxa, meio.parcelas))
        ]

    # Entrada sem juros e anuais: partes iguais, sem juros. A sobra de centavos
    # vai na primeira — quem paga o sinal prefere a diferença no ato à surpresa
    # no fim.
    n = max(1, meio.parcelas)
    passo = 1
    inicio = meio.primeiro_vencimento or hoje
    if t == "anuais":
        passo = 6 if meio.periodicidade == "semestral" else 12
        inicio = meio.primeiro_vencimento or somar_meses(hoje, passo)
    base = centavos(meio.valor / n)
    linhas = []
    for i in range(n):
        valor = base if i > 0 else centavos(meio.valor - base * (n - 1))
        linhas.append(Parcela(
            numero=i + 1, tipo=tipo, vencimento=somar_meses(inicio, i * passo),
            valor=valor, amortizacao=valor, meio=ordem,
        ))
    return linhas


def negociar(valor_tabela, desconto_percentual=ZERO, desconto_valor=ZERO) -> tuple[Decimal, Decimal, Decimal]:
    """Tabela, desconto e valor negociado — a conta que os meios têm de fechar.

    À parte de `montar()` porque a simulação precisa do negociado **também
    quando os meios ainda não fecham**: é ele que deixa a tela dizer "faltam
    R$ 10.000" e oferecer "usar o restante" sem refazer a conta do desconto no
    navegador.
    """
    valor_tabela = centavos(Decimal(valor_tabela or 0))
    desconto = centavos(
        Decimal(desconto_valor or 0) + valor_tabela * Decimal(desconto_percentual or 0) / 100
    )
    if desconto > valor_tabela:
        raise ValueError("O desconto não pode ser maior que o valor de tabela.")
    return valor_tabela, desconto, centavos(valor_tabela - desconto)


def montar(
    *,
    valor_tabela: Decimal,
    desconto_percentual: Decimal = ZERO,
    desconto_valor: Decimal = ZERO,
    meios: list | None = None,
    data_compra: date | None = None,
    ajustar_vencimento=None,
) -> Plano:
    """A proposta da assinatura: resumo, meio a meio, e o carnê linha a linha.

    ``meios`` é a lista livre da venda — dicts do payload, registros
    ``MeioPagamento`` ou ``Meio`` já lidos. A conta só fecha quando **a soma dos
    meios é o valor negociado**: faltar é saldo sem dono (a venda ficaria
    devendo a si mesma), sobrar é cobrar do comprador mais do que ele negociou.
    O erro diz quanto falta ou quanto passa, em reais.

    Erros de entrada viram `ValueError` — a tela precisa dizer "falta R$ 10.000"
    em vez de gerar um carnê que não fecha.

    ``ajustar_vencimento`` é o **calendário bancário injetado**: uma função
    ``date -> date`` (na prática, ``modulocalendar.dias_uteis.AjusteDeVencimento``)
    que empurra para o próximo dia útil a parcela que cai em sábado, domingo ou
    feriado. Entra por parâmetro, e não por import, para este módulo continuar
    puro. Sem ele, o cálculo é o do contrato cru, que é o que os testes de
    matemática querem.

    **O ajuste é só da data, nunca do valor.** Juros correm por parcela, não por
    dia corrido: empurrar o vencimento de 13/04 para 14/04 não acrescenta um dia
    de juro — se acrescentasse, o carnê exibido na venda não fecharia com o
    carnê emitido, e a diferença apareceria como centavos inexplicáveis.
    """
    from payment.planos import VENDA_TETO_MEIOS_DE_PAGAMENTO

    valor_tabela, desconto, valor_negociado = negociar(
        valor_tabela, desconto_percentual, desconto_valor,
    )
    hoje = data_compra or date.today()

    origem = list(meios or [])
    if len(origem) > VENDA_TETO_MEIOS_DE_PAGAMENTO:
        raise ValueError(
            f"Uma venda comporta até {VENDA_TETO_MEIOS_DE_PAGAMENTO} meios de pagamento."
        )
    lidos = [m if isinstance(m, Meio) else meio_de(m, i) for i, m in enumerate(origem, start=1)]
    if not lidos and valor_negociado > 0:
        raise ValueError("Adicione ao menos um meio de pagamento.")
    for i, meio in enumerate(lidos, start=1):
        _validar_meio(meio, i)

    soma = centavos(sum((m.valor for m in lidos), ZERO))
    if soma < valor_negociado:
        raise ValueError(
            f"Faltam {brl(valor_negociado - soma)} para os meios de pagamento fecharem "
            f"o valor negociado ({brl(valor_negociado)})."
        )
    if soma > valor_negociado:
        raise ValueError(
            f"Os meios de pagamento passam {brl(soma - valor_negociado)} do valor "
            f"negociado ({brl(valor_negociado)})."
        )

    ajustar = _normalizar_ajuste(ajustar_vencimento)
    parcelas: list[Parcela] = []
    resumos: list[ResumoDoMeio] = []
    for ordem, meio in enumerate(lidos, start=1):
        linhas = _linhas_do_meio(meio, ordem, hoje)
        resumos.append(ResumoDoMeio(
            ordem=ordem, tipo=meio.tipo, rotulo=_rotulo(meio), detalhe=_detalhe(meio, linhas),
            descricao=meio.descricao, valor=meio.valor, no_carne=meio.catalogo.no_carne,
            juros=centavos(sum((p.juros for p in linhas), ZERO)),
            total=centavos(sum((p.valor for p in linhas), ZERO)) if linhas else meio.valor,
            quantidade=len(linhas),
            primeira_parcela=linhas[0].valor if linhas else ZERO,
            ultima_parcela=linhas[-1].valor if linhas else ZERO,
        ))
        parcelas.extend(_com_ajuste(p, ajustar) for p in linhas)

    parcelas.sort(key=lambda p: (p.vencimento, p.meio, p.numero))
    mensais = [p for p in parcelas if p.tipo == "parcela"]

    def soma_do(tipo: str) -> Decimal:
        return centavos(sum((m.valor for m in lidos if m.tipo == tipo), ZERO))

    return Plano(
        valor_tabela=valor_tabela,
        desconto=desconto,
        valor_negociado=valor_negociado,
        entrada=soma_do("entrada"),
        baloes=soma_do("anuais"),
        saldo_financiado=soma_do("financiamento_direto"),
        total_juros=centavos(sum((p.juros for p in parcelas), ZERO)),
        total=centavos(sum((p.valor for p in parcelas), ZERO)),
        primeira_parcela=mensais[0].valor if mensais else ZERO,
        ultima_parcela=mensais[-1].valor if mensais else ZERO,
        fora_do_carne=centavos(sum((m.valor for m in lidos if not m.catalogo.no_carne), ZERO)),
        condicao=condicao_da_venda(lidos),
        parcelas=parcelas,
        meios=resumos,
    )


def montar_da_aquisicao(aquisicao, *, ajustar_vencimento=_PADRAO) -> Plano:
    """O mesmo cálculo, alimentado pelo que está gravado na aquisição.

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
        # `.all()` e não `order_by()`: respeita o `prefetch_related('meios')` de
        # quem monta em lote (a lista da carteira, o semeador). A ordem é a do
        # `Meta.ordering` do modelo.
        meios=list(aquisicao.meios.all()),
        data_compra=aquisicao.data_compra,
        ajustar_vencimento=ajustar_vencimento,
    )


# ─── O texto do título ────────────────────────────────────────────────────────

_NOME_DA_LINHA = {
    "entrada": "Entrada", "parcela": "Parcela", "balao": "Balão",
}


def descricoes_do_carne(plano: Plano, aquisicao) -> list[str]:
    """O texto de cada título do carnê, na ordem de ``plano.parcelas``.

    Sai daqui — e não do laço de quem gera — porque são três chamadores (a
    geração do carnê, o semeador da demo e qualquer recomposição futura) e o
    texto tem de ser o mesmo nos três: é o que o cliente confere no banco.

    A contagem ("Parcela 32/36") é **por meio**, não por tipo: numa venda com
    dois financiamentos diretos, a série de 24 e a de 60 não podem virar uma
    "Parcela 1/84" que não existe em contrato nenhum. Quando o mesmo tipo
    aparece em dois meios, a série vai dita: "Parcela 3/24 (2ª série)".
    """
    por_meio: dict[int, int] = {}
    for p in plano.parcelas:
        por_meio[p.meio] = por_meio.get(p.meio, 0) + 1
    series_do_tipo: dict[str, list[int]] = {}
    for m in plano.meios:
        series_do_tipo.setdefault(m.tipo, []).append(m.ordem)
    tipo_do_meio = {m.ordem: m.tipo for m in plano.meios}

    textos = []
    for p in plano.parcelas:
        series = series_do_tipo.get(tipo_do_meio.get(p.meio, ""), [p.meio])
        serie = series.index(p.meio) + 1 if len(series) > 1 else None
        textos.append(descricao_do_titulo(p, por_meio[p.meio], aquisicao, serie=serie))
    return textos


def descricao_da_parcela(parcela: Parcela, total_da_serie: int, serie: int | None = None) -> str:
    """O que a parcela é: "Parcela 32/36", "Entrada 2/3", "Balão 1/5",
    "Pagamento à vista", "Cartão"."""
    if parcela.tipo == "a_vista":
        texto = "Pagamento à vista"
    elif parcela.tipo == "cartao":
        texto = "Cartão"
    else:
        nome = _NOME_DA_LINHA.get(parcela.tipo, "Parcela")
        texto = f"{nome} {parcela.numero}/{total_da_serie}"
    return f"{texto} ({serie}ª série)" if serie else texto


def descricao_do_titulo(parcela: Parcela, total_da_serie: int, aquisicao, *, serie: int | None = None) -> str:
    """O texto que o comprador lê no extrato e **no boleto**.

    **O empreendimento vem antes da unidade.** "Parcela 32/36 — QD 4 · LT 06"
    identifica o lote para quem já sabe de que loteamento se fala; quem recebe o
    boleto pode ter comprado em dois, e a quadra 4 existe em ambos. Com o nome do
    empreendimento na frente, o título se explica sozinho — que é o único jeito
    de um boleto se explicar, porque ele chega sem a tela em volta.
    """
    partes = [descricao_da_parcela(parcela, total_da_serie, serie), "—"]
    empreendimento = getattr(aquisicao, "empreendimento", None)
    nome = getattr(empreendimento, "empreendimento", "") or ""
    rotulo = aquisicao.unidade.rotulo
    partes.append(f"{nome} · {rotulo}" if nome else rotulo)
    return " ".join(partes)
