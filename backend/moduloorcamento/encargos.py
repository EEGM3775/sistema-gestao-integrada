# backend/moduloorcamento/encargos.py
"""Encargos sociais **analíticos** — o quadro que edital pede (ORC.7).

Até o ORC.6 os encargos eram um percentual digitado no cabeçalho do orçamento.
O número entrava certo na conta e reprovava na conferência: análise de proposta
não pergunta *quanto*, pergunta **de onde** — grupo A, grupo B, grupo C e as
reincidências do grupo D, cada rubrica com sua alíquota. É a mesma exigência que
já valia para o BDI (composição analítica, `precificacao.calcular_bdi`), agora
do lado da folha.

A aritmética que o quadro guarda, e por que ela não é uma soma qualquer:

    Encargos totais = A + B + C + D

    A  obrigações sociais sobre a folha (INSS/CPP, sistema S, FGTS, RAT)
    B  encargos que RECEBEM a incidência de A (repouso, feriado, 13º, férias)
    C  encargos que NÃO recebem a incidência de A, por serem indenizatórios
    D  reincidências:  A×B/100  +  FGTS×aviso prévio/100

O grupo D é a razão de o quadro existir em vez de um campo. Ele não é digitado:
sai de A, B e das rubricas marcadas (`e_fgts`, `e_aviso_previo`). Quem digita D
à mão erra, e o erro é invisível — some dentro de um percentual plausível.

**Desoneração.** No regime desonerado a CPP de 20% sai da folha e vira CPRB
sobre a receita bruta, que é tributo e portanto vive no **BDI**
(`ComposicaoBDI.cprb`), não aqui. Por isso o quadro desonerado nasce sem a
rubrica A1 — e não com ela zerada, que faria a planilha alegar uma contribuição
inexistente.

**Horista × mensalista.** O mensalista recebe repouso semanal e feriados
embutidos no salário; aplicar o grupo B do horista sobre ele paga o mesmo
descanso duas vezes. Os dois quadros convivem no mesmo orçamento e a explosão
escolhe pela unidade do insumo — `H` (hora) → horista, `MES` → mensalista.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import ComposicaoEncargos, Orcamento, RubricaEncargos

CEM = Decimal("100")
QUATRO = Decimal("0.0001")


class QuadroInvalido(Exception):
    """Quadro que não fecha — alíquota negativa, grupo derivado sem base."""


# ---------------------------------------------------------------------------
# Modelo de partida
# ---------------------------------------------------------------------------
#
# A **estrutura** das rubricas é estável e pública: é a metodologia SINAPI, que
# o TCU usa como referência e que toda publicação estadual espelha. As
# **alíquotas** não são todas iguais:
#
#   - grupo A é lei (CPP 20%, FGTS 8%, salário-educação 2,5%, sistema S,
#     INCRA, RAT) — entra preenchido, porque não depende de publicação;
#   - grupos B e C dependem da publicação, da UF e do acordo coletivo (dias de
#     chuva no Sul não é o do Nordeste) — entram como **valores de partida**,
#     marcados para conferência.
#
# Por isso `criar_quadro_padrao` devolve o quadro com `conferir=True` até
# alguém salvar: o número aparece, mas declarado como partida, não como verdade
# da publicação vigente. É a mesma regra do `cobertura_pct` da curva por
# natureza — dado que não é da fonte diz que não é.

_GRUPO_A = [
    ("A1", "INSS / Contribuição previdenciária patronal", Decimal("20.00"), True),
    ("A2", "SESI", Decimal("1.50"), True),
    ("A3", "SENAI", Decimal("1.00"), True),
    ("A4", "INCRA", Decimal("0.20"), True),
    ("A5", "SEBRAE", Decimal("0.60"), True),
    ("A6", "Salário-educação", Decimal("2.50"), True),
    ("A7", "Seguro contra acidentes de trabalho (RAT ajustado)", Decimal("3.00"), True),
    ("A8", "FGTS", Decimal("8.00"), True),
    ("A9", "SECONCI", Decimal("0.00"), True),
]

_GRUPO_B_HORISTA = [
    ("B1", "Repouso semanal remunerado", Decimal("17.82")),
    ("B2", "Feriados", Decimal("3.98")),
    ("B3", "Auxílio-enfermidade", Decimal("0.91")),
    ("B4", "13º salário", Decimal("10.97")),
    ("B5", "Licença-paternidade", Decimal("0.08")),
    ("B6", "Faltas justificadas", Decimal("0.73")),
    ("B7", "Dias de chuva", Decimal("1.56")),
    ("B8", "Auxílio acidente de trabalho", Decimal("0.11")),
    ("B9", "Férias gozadas", Decimal("12.02")),
    ("B10", "Salário-maternidade", Decimal("0.03")),
]

# O mensalista não tem B1/B2 (o salário do mês já os contém) nem "dias de
# chuva" — ausência, não zero: rubrica que não se aplica não entra no quadro.
_GRUPO_B_MENSALISTA = [
    ("B1", "13º salário", Decimal("8.33")),
    ("B2", "Férias gozadas", Decimal("9.68")),
    ("B3", "Auxílio-enfermidade", Decimal("0.69")),
    ("B4", "Licença-paternidade", Decimal("0.06")),
    ("B5", "Faltas justificadas", Decimal("0.56")),
    ("B6", "Auxílio acidente de trabalho", Decimal("0.08")),
    ("B7", "Salário-maternidade", Decimal("0.03")),
]

_GRUPO_C_HORISTA = [
    ("C1", "Aviso prévio indenizado", Decimal("4.31"), True),
    ("C2", "Aviso prévio trabalhado", Decimal("0.11"), True),
    ("C3", "Férias indenizadas", Decimal("1.05"), False),
    ("C4", "Depósito por rescisão sem justa causa", Decimal("3.83"), False),
    ("C5", "Indenização adicional", Decimal("0.36"), False),
]

_GRUPO_C_MENSALISTA = [
    ("C1", "Aviso prévio indenizado", Decimal("3.30"), True),
    ("C2", "Aviso prévio trabalhado", Decimal("0.08"), True),
    ("C3", "Férias indenizadas", Decimal("0.80"), False),
    ("C4", "Depósito por rescisão sem justa causa", Decimal("2.93"), False),
    ("C5", "Indenização adicional", Decimal("0.28"), False),
]

_GRUPO_D = [
    ("D1", "Reincidência de A sobre B", RubricaEncargos.BaseCalculo.A_SOBRE_B),
    ("D2", "Reincidência do FGTS sobre o aviso prévio", RubricaEncargos.BaseCalculo.FGTS_SOBRE_AVISO),
]


def _rubricas_de_partida(tipo: str, regime: str) -> list[dict]:
    """As linhas do quadro novo, na ordem em que a publicação as imprime."""
    horista = tipo == ComposicaoEncargos.TipoMaoDeObra.HORISTA
    desonerado = regime == ComposicaoEncargos.Regime.DESONERADO
    linhas: list[dict] = []

    for ordem, (codigo, descricao, percentual, _lei) in enumerate(_GRUPO_A):
        # No desonerado a CPP não existe — a rubrica **sai** do quadro. Zerá-la
        # deixaria uma linha "INSS 0,00%" que sugere contribuição apurada em
        # zero, quando o certo é dizer que a base mudou de folha para receita.
        if desonerado and codigo == "A1":
            continue
        linhas.append({
            "grupo": RubricaEncargos.Grupo.A, "codigo": codigo, "descricao": descricao,
            "percentual": percentual, "ordem": ordem,
            "e_fgts": codigo == "A8",
        })

    tabela_b = _GRUPO_B_HORISTA if horista else _GRUPO_B_MENSALISTA
    for ordem, (codigo, descricao, percentual) in enumerate(tabela_b):
        linhas.append({
            "grupo": RubricaEncargos.Grupo.B, "codigo": codigo, "descricao": descricao,
            "percentual": percentual, "ordem": ordem,
        })

    tabela_c = _GRUPO_C_HORISTA if horista else _GRUPO_C_MENSALISTA
    for ordem, (codigo, descricao, percentual, aviso) in enumerate(tabela_c):
        linhas.append({
            "grupo": RubricaEncargos.Grupo.C, "codigo": codigo, "descricao": descricao,
            "percentual": percentual, "ordem": ordem, "e_aviso_previo": aviso,
        })

    for ordem, (codigo, descricao, base) in enumerate(_GRUPO_D):
        linhas.append({
            "grupo": RubricaEncargos.Grupo.D, "codigo": codigo, "descricao": descricao,
            "percentual": Decimal("0"), "ordem": ordem, "base_calculo": base,
        })
    return linhas


@transaction.atomic
def criar_quadro_padrao(
    orcamento: Orcamento,
    *,
    tipo: str = ComposicaoEncargos.TipoMaoDeObra.HORISTA,
    regime: str | None = None,
    nome: str = "",
) -> ComposicaoEncargos:
    """Cria o quadro de partida e já o calcula.

    O regime, quando não vem, é herdado do orçamento — quem escolheu
    onerado/desonerado na capa não deveria escolher de novo aqui, e as duas
    escolhas divergirem é como um orçamento passa a somar CPP e CPRB ao mesmo
    tempo.
    """
    if regime is None:
        regime = (
            ComposicaoEncargos.Regime.DESONERADO
            if orcamento.regime_encargos == ComposicaoEncargos.Regime.DESONERADO
            else ComposicaoEncargos.Regime.ONERADO
        )

    rotulo = dict(ComposicaoEncargos.TipoMaoDeObra.choices)[tipo]
    composicao = ComposicaoEncargos.objects.create(
        tenant_id=orcamento.tenant_id,
        orcamento=orcamento,
        nome=nome or f"Encargos sociais — {rotulo.lower()}",
        tipo_mao_de_obra=tipo,
        regime=regime,
        padrao=not ComposicaoEncargos.objects.filter(orcamento=orcamento).exists(),
        data_base=orcamento.data_base,
    )
    RubricaEncargos.objects.bulk_create([
        RubricaEncargos(tenant_id=orcamento.tenant_id, composicao=composicao, **linha)
        for linha in _rubricas_de_partida(tipo, regime)
    ])
    return salvar_encargos(composicao)


# ---------------------------------------------------------------------------
# O cálculo
# ---------------------------------------------------------------------------


def calcular_encargos(composicao: ComposicaoEncargos) -> dict:
    """Totaliza os quatro grupos e **deriva** o D. Não grava.

    Devolve os totais e as rubricas de D já resolvidas, para a tela mostrar a
    conta ao lado do número bloqueado. Duas travas:

    - alíquota negativa levanta erro — encargo negativo não existe, e um sinal
      trocado numa rubrica some dentro do total sem isso;
    - `a_sobre_b` sem grupo A **ou** sem grupo B devolve zero em vez de erro:
      um quadro em montagem passa por esse estado o tempo todo, e recusar-se a
      calcular deixaria a tela sem número enquanto o usuário digita.
    """
    rubricas = list(composicao.rubricas.all())
    for rubrica in rubricas:
        if rubrica.base_calculo == RubricaEncargos.BaseCalculo.DIRETA and rubrica.percentual < 0:
            raise QuadroInvalido(
                f"{rubrica.codigo or rubrica.descricao}: alíquota negativa ({rubrica.percentual}%)."
            )

    def soma(grupo) -> Decimal:
        return sum(
            (
                r.percentual for r in rubricas
                if r.grupo == grupo and r.base_calculo == RubricaEncargos.BaseCalculo.DIRETA
            ),
            Decimal("0"),
        )

    total_a = soma(RubricaEncargos.Grupo.A)
    total_b = soma(RubricaEncargos.Grupo.B)
    total_c = soma(RubricaEncargos.Grupo.C)

    fgts = sum((r.percentual for r in rubricas if r.e_fgts), Decimal("0"))
    aviso = sum((r.percentual for r in rubricas if r.e_aviso_previo), Decimal("0"))

    derivadas: list[dict] = []
    total_d = Decimal("0")
    for rubrica in rubricas:
        if rubrica.grupo != RubricaEncargos.Grupo.D:
            continue
        if rubrica.base_calculo == RubricaEncargos.BaseCalculo.A_SOBRE_B:
            valor = total_a * total_b / CEM
            conta = f"A ({total_a}%) × B ({total_b}%) ÷ 100"
        elif rubrica.base_calculo == RubricaEncargos.BaseCalculo.FGTS_SOBRE_AVISO:
            valor = fgts * aviso / CEM
            conta = f"FGTS ({fgts}%) × aviso prévio ({aviso}%) ÷ 100"
        else:
            valor = rubrica.percentual
            conta = "alíquota digitada"
        valor = valor.quantize(QUATRO, rounding=ROUND_HALF_UP)
        total_d += valor
        derivadas.append({"rubrica": rubrica, "valor": valor, "conta": conta})

    total = total_a + total_b + total_c + total_d
    return {
        "total_grupo_a": total_a.quantize(QUATRO, rounding=ROUND_HALF_UP),
        "total_grupo_b": total_b.quantize(QUATRO, rounding=ROUND_HALF_UP),
        "total_grupo_c": total_c.quantize(QUATRO, rounding=ROUND_HALF_UP),
        "total_grupo_d": total_d.quantize(QUATRO, rounding=ROUND_HALF_UP),
        "percentual_calculado": total.quantize(QUATRO, rounding=ROUND_HALF_UP),
        "derivadas": derivadas,
        "fgts": fgts,
        "aviso_previo": aviso,
    }


@transaction.atomic
def salvar_encargos(composicao: ComposicaoEncargos) -> ComposicaoEncargos:
    """Calcula, grava as derivadas e — se for o padrão — propaga para o orçamento.

    Espelha `precificacao.salvar_bdi`: o `encargos_sociais_percentual` do
    cabeçalho continua sendo o número que a explosão multiplica, e esta função
    passa a ser quem o alimenta. Digitar direto segue possível para quem não
    quer detalhar; havendo quadro, é o quadro que manda.
    """
    calculo = calcular_encargos(composicao)

    for derivada in calculo["derivadas"]:
        rubrica = derivada["rubrica"]
        if rubrica.percentual != derivada["valor"]:
            rubrica.percentual = derivada["valor"]
            rubrica.save(update_fields=["percentual"])

    composicao.total_grupo_a = calculo["total_grupo_a"]
    composicao.total_grupo_b = calculo["total_grupo_b"]
    composicao.total_grupo_c = calculo["total_grupo_c"]
    composicao.total_grupo_d = calculo["total_grupo_d"]
    composicao.percentual_calculado = calculo["percentual_calculado"]
    # `padrao` entra no `update_fields` porque é ele que decide a demoção dos
    # outros quadros logo abaixo. Ler a intenção da instância em memória e não
    # gravá-la deixaria o banco com **zero** padrão: o antigo demovido, o novo
    # nunca promovido — e o cabeçalho do orçamento com um percentual órfão.
    composicao.save(update_fields=[
        "total_grupo_a", "total_grupo_b", "total_grupo_c", "total_grupo_d",
        "percentual_calculado", "padrao",
    ])

    if composicao.padrao:
        ComposicaoEncargos.objects.filter(orcamento=composicao.orcamento).exclude(
            pk=composicao.pk
        ).update(padrao=False)
        orcamento = composicao.orcamento
        orcamento.encargos_sociais_percentual = composicao.percentual_calculado.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        orcamento.save(update_fields=["encargos_sociais_percentual", "atualizado_em"])
    return composicao


def quadro(composicao: ComposicaoEncargos) -> dict:
    """O quadro pronto para a tela e para o PDF: grupos, linhas e subtotais."""
    calculo = calcular_encargos(composicao)
    contas = {d["rubrica"].pk: d["conta"] for d in calculo["derivadas"]}
    valores = {d["rubrica"].pk: d["valor"] for d in calculo["derivadas"]}

    grupos: dict[str, dict] = {}
    for rubrica in composicao.rubricas.all():
        bloco = grupos.setdefault(rubrica.grupo, {
            "grupo": rubrica.grupo,
            "rotulo": dict(RubricaEncargos.Grupo.choices)[rubrica.grupo],
            "rubricas": [],
        })
        derivada = rubrica.base_calculo != RubricaEncargos.BaseCalculo.DIRETA
        bloco["rubricas"].append({
            "rubrica": rubrica.pk,
            "codigo": rubrica.codigo,
            "descricao": rubrica.descricao,
            "percentual": str(valores.get(rubrica.pk, rubrica.percentual)),
            "derivada": derivada,
            "conta": contas.get(rubrica.pk, ""),
            "e_fgts": rubrica.e_fgts,
            "e_aviso_previo": rubrica.e_aviso_previo,
        })

    subtotais = {
        "A": calculo["total_grupo_a"], "B": calculo["total_grupo_b"],
        "C": calculo["total_grupo_c"], "D": calculo["total_grupo_d"],
    }
    for chave, bloco in grupos.items():
        bloco["subtotal"] = str(subtotais.get(chave, Decimal("0")))

    return {
        "encargos": composicao.pk,
        "orcamento": composicao.orcamento_id,
        "nome": composicao.nome,
        "tipo_mao_de_obra": composicao.tipo_mao_de_obra,
        "regime": composicao.regime,
        "padrao": composicao.padrao,
        "data_base": composicao.data_base.isoformat() if composicao.data_base else None,
        "grupos": [grupos[c] for c in ("A", "B", "C", "D") if c in grupos],
        "total": str(calculo["percentual_calculado"]),
    }


# ---------------------------------------------------------------------------
# Resolução na explosão da composição
# ---------------------------------------------------------------------------

# Unidades que a SINAPI usa para mão de obra mensalista. Fora desta lista, a
# hipótese é horista — que é a esmagadora maioria dos insumos de mão de obra de
# obra civil (pedreiro, servente, carpinteiro são todos publicados em H).
_UNIDADES_MENSALISTAS = {"MES", "MÊS", "M", "MS", "MENSAL"}


class ResolvedorEncargos:
    """Escolhe o percentual de encargos de cada insumo de mão de obra.

    Existe como objeto, e não como função, porque a explosão de uma composição
    passa por dezenas de insumos: carregar os quadros do orçamento uma vez e
    consultar em memória evita a consulta por insumo, que é como um recálculo de
    planilha grande vira minuto.

    A escala de decisão, do mais específico ao mais geral:

    1. quadro do **tipo** que a unidade do insumo indica (`MES` → mensalista);
    2. quadro marcado `padrao`;
    3. `encargos_sociais_percentual` do cabeçalho — o caminho de quem não
       detalhou, que continua funcionando exatamente como antes do ORC.7.
    """

    def __init__(self, orcamento: Orcamento):
        self.orcamento = orcamento
        self._por_tipo: dict[str, Decimal] = {}
        self._padrao: Decimal | None = None
        for composicao in ComposicaoEncargos.objects.filter(orcamento=orcamento):
            self._por_tipo[composicao.tipo_mao_de_obra] = composicao.percentual_calculado
            if composicao.padrao:
                self._padrao = composicao.percentual_calculado
        self._cabecalho = orcamento.encargos_sociais_percentual or Decimal("0")

    def percentual(self, unidade: str = "") -> Decimal:
        """Percentual aplicável (em pontos, não fração)."""
        normalizada = (unidade or "").strip().upper()
        if normalizada in _UNIDADES_MENSALISTAS:
            mensalista = self._por_tipo.get(ComposicaoEncargos.TipoMaoDeObra.MENSALISTA)
            if mensalista is not None:
                return mensalista
        else:
            horista = self._por_tipo.get(ComposicaoEncargos.TipoMaoDeObra.HORISTA)
            if horista is not None:
                return horista
        if self._padrao is not None:
            return self._padrao
        return self._cabecalho

    def fator(self, unidade: str = "") -> Decimal:
        """`1 + encargos`, que é como a explosão multiplica."""
        return Decimal("1") + self.percentual(unidade) / CEM

    @property
    def detalhado(self) -> bool:
        """Se há quadro analítico — a tela usa para dizer de onde veio o número."""
        return bool(self._por_tipo)
