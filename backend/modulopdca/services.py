# backend/modulopdca/services.py
"""As regras de negócio do PDCA — as que não passam por HTTP.

**PDCA.0** povoou a árvore de locais e ensinou a contar dia útil. **PDCA.1** usa
as duas: o CPM (§3 deste arquivo) roda sobre o grafo de precedências convertendo
duração em datas pelo calendário, e o versionamento (§4) transforma cada
replanejamento numa linha de base legível. **PDCA.2** fecha o ciclo: o avanço
apontado sobe a árvore ponderado pelo peso (§7), a curva S ganha a linha
realizada (§8) e o percentual da etapa passa a ser apurado (§9).

O CPM roda **no servidor** por decisão de desenho (planta §5.5): é fonte de
verdade para prazo e dinheiro, e recalculá-lo no navegador daria um resultado
por máquina.
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Sum
from django.utils import timezone

from payment.planos import (
    PDCA_CPM_SEGUNDOS,
    PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_PONTOS_CURVA_S,
    PDCA_PROFUNDIDADE_MAXIMA_LOCAL,
    PDCA_PROFUNDIDADE_MAXIMA_WBS,
    PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
    PDCA_TETO_CPM_SINCRONO,
    PDCA_TETO_LINHAS_POR_LOTE,
    PDCA_TETO_LOCAIS_POR_GERACAO,
    PDCA_TETO_LOCAIS_POR_OBRA,
    PDCA_TETO_VERSOES_POR_CRONOGRAMA,
)

from .models import (
    ApontamentoAvanco, Atividade, CalendarioTrabalho, Cronograma,
    ExcecaoCalendario, LocalObra, NivelLocal, Precedencia,
)

# ---------------------------------------------------------------------------
# 1. A árvore de locais
# ---------------------------------------------------------------------------


def _milhar(n: int) -> str:
    """1.600, não 1,600. A mensagem de recusa é lida por quem opera a obra, em
    português — e um teto escrito com separador inglês num aviso de limite é
    exatamente o tipo de número que o leitor lê errado por um fator de mil."""
    return f"{n:,}".replace(",", ".")


def profundidade_de(pai: LocalObra | None) -> int:
    """Raiz é 1. É o único lugar que sabe disso — o modelo guarda o número, mas
    quem o calcula é aqui."""
    return 1 if pai is None else pai.profundidade + 1


def validar_profundidade(pai: LocalObra | None, *, quantos_niveis: int = 1) -> None:
    final = profundidade_de(pai) + quantos_niveis - 1
    if final > PDCA_PROFUNDIDADE_MAXIMA_LOCAL:
        raise ValidationError(
            f"A hierarquia de locais vai até {PDCA_PROFUNDIDADE_MAXIMA_LOCAL} níveis; "
            f"esta geração chegaria ao nível {final}."
        )


def _expandir(spec: dict) -> list[tuple[str, str]]:
    """Um degrau da receita vira uma lista de `(codigo, nome)`.

    Duas formas, e as duas existem porque o canteiro fala as duas: **faixa**
    (`de`/`ate`, "pavimentos 1 a 20") e **lista** (`itens`, "101, 102, 103, 104").
    A faixa aceita `formato_codigo`/`formato_nome` com `{n}` — sem isso, gerar 20
    pavimentos com nome decente exigiria digitar os 20.
    """
    nivel = spec.get("nivel")
    if nivel not in NivelLocal.values:
        raise ValidationError(f"Nível desconhecido: {nivel!r}.")

    itens = spec.get("itens")
    if itens:
        saida = []
        for item in itens:
            if isinstance(item, dict):
                codigo = str(item.get("codigo") or "").strip()
                nome = str(item.get("nome") or codigo).strip()
            else:
                codigo = nome = str(item).strip()
            if not codigo:
                raise ValidationError("Item sem código na receita de geração.")
            saida.append((codigo[:40], nome[:150]))
        return saida

    if "de" in spec and "ate" in spec:
        try:
            de, ate = int(spec["de"]), int(spec["ate"])
        except (TypeError, ValueError):
            raise ValidationError("`de` e `ate` precisam ser inteiros.")
        if ate < de:
            raise ValidationError("`ate` não pode ser menor que `de`.")
        fmt_codigo = spec.get("formato_codigo") or "{n}"
        fmt_nome = spec.get("formato_nome") or fmt_codigo
        saida = []
        for n in range(de, ate + 1):
            try:
                codigo = fmt_codigo.format(n=n)
                nome = fmt_nome.format(n=n)
            except (KeyError, IndexError):
                raise ValidationError(
                    "O formato só conhece o marcador `{n}` (ex.: 'P{n:02d}')."
                )
            saida.append((codigo[:40], nome[:150]))
        return saida

    raise ValidationError(
        "Cada nível da receita precisa de `itens` (lista) ou de `de`/`ate` (faixa)."
    )


def gerar_em_lote(*, obra, tenant_id: int, receita: list[dict],
                  pai: LocalObra | None = None, simular: bool = False) -> dict:
    """Cria a árvore inteira a partir de uma receita de poucos campos.

    "Torre A, pavimentos 1 a 20, quatro unidades por andar" são 1.600 linhas; o
    recurso existe porque criá-las à mão é o que faz ninguém usar a hierarquia —
    e sem hierarquia não há linha de balanço nem endereço de não-conformidade.

    **Sempre devolve o mesmo relatório**, simulando ou gravando: quantos seriam
    criados, quantos já existiam, e a árvore resultante em números. `simular=True`
    é o pré-visualizar da tela — a mesma conta, sem escrever. Sem isso o cliente
    descobre que pediu 16.000 locais **depois** de tê-los criado.

    Idempotente por `(pai, codigo)`: rodar duas vezes a mesma receita não duplica
    nada, e é o que salva o clique dobrado e o retry do navegador.
    """
    if not receita:
        raise ValidationError("A receita de geração está vazia.")
    validar_profundidade(pai, quantos_niveis=len(receita))

    niveis = [(spec.get("nivel"), _expandir(spec)) for spec in receita]

    # O tamanho do estrago, contado ANTES de escrever: o produto cartesiano dos
    # degraus. É esta conta — e não o número de linhas na receita — que o teto
    # precisa ver, porque três linhas de formulário produzem milhares de locais.
    total = 0
    largura = 1
    for _nivel, itens in niveis:
        largura *= len(itens)
        total += largura
    if total == 0:
        raise ValidationError("A receita não gera nenhum local.")
    if total > PDCA_TETO_LOCAIS_POR_GERACAO:
        raise ValidationError(
            f"Esta receita geraria {_milhar(total)} locais de uma vez, e o limite por "
            f"geração é {_milhar(PDCA_TETO_LOCAIS_POR_GERACAO)}. Divida em partes "
            f"(uma torre por vez, por exemplo)."
        )

    existentes = LocalObra.objects.filter(tenant_id=tenant_id, obra=obra).count()
    if existentes + total > PDCA_TETO_LOCAIS_POR_OBRA:
        raise ValidationError(
            f"A obra já tem {_milhar(existentes)} locais e esta geração somaria {_milhar(total)}, "
            f"passando do limite de {_milhar(PDCA_TETO_LOCAIS_POR_OBRA)} por obra."
        )

    relatorio = {
        "total_previsto": total,
        "criados": 0,
        "ja_existiam": 0,
        "por_nivel": {},
        "simulado": bool(simular),
    }

    if simular:
        largura = 1
        for nivel, itens in niveis:
            largura *= len(itens)
            relatorio["por_nivel"][nivel] = relatorio["por_nivel"].get(nivel, 0) + largura
        return relatorio

    with transaction.atomic():
        pais_do_nivel = [pai]
        for nivel, itens in niveis:
            proximos = []
            for progenitor in pais_do_nivel:
                profundidade = profundidade_de(progenitor)
                existentes_aqui = {
                    l.codigo: l
                    for l in LocalObra.objects.filter(
                        tenant_id=tenant_id, obra=obra, pai=progenitor
                    )
                }
                for ordem, (codigo, nome) in enumerate(itens, start=1):
                    ja = existentes_aqui.get(codigo)
                    if ja is not None:
                        relatorio["ja_existiam"] += 1
                        proximos.append(ja)
                        continue
                    criado = LocalObra.objects.create(
                        tenant_id=tenant_id, obra=obra, pai=progenitor, nivel=nivel,
                        codigo=codigo, nome=nome, ordem=ordem,
                        profundidade=profundidade,
                    )
                    relatorio["criados"] += 1
                    relatorio["por_nivel"][nivel] = relatorio["por_nivel"].get(nivel, 0) + 1
                    proximos.append(criado)
            pais_do_nivel = proximos

    return relatorio


# ---------------------------------------------------------------------------
# 2. O calendário — de duração para datas
# ---------------------------------------------------------------------------
# Teto de segurança das funções que caminham no calendário. Não é limite de
# produto (não vai para `planos.py`, §5.6): é o guarda-corpo de um laço que
# avança um dia por vez. Um calendário sem nenhum dia útil ligado — sete
# `trabalha_*` desmarcados, que a tela permite — faria `somar_dias_uteis` andar
# para sempre. Cinco anos de dias corridos é muito além de qualquer duração de
# atividade real e curto o bastante para o erro aparecer como erro.
_MAXIMO_DIAS_CAMINHADOS = 365 * 5


def feriados_do_periodo(calendario: CalendarioTrabalho, inicio: date, fim: date) -> dict:
    """`{data: nome}` no período, na localidade do calendário.

    Nacional sempre; estadual só com `uf`; municipal só com `ibge`. Afirmar um
    feriado municipal sem saber o município seria inventar dia parado — a mesma
    régua de dado honesto do resto da casa.
    """
    if not calendario.considera_feriados:
        return {}

    from django.db.models import Q

    from modulocalendar.models import Feriado

    escopo = Q(escopo="nacional")
    if calendario.uf:
        escopo |= Q(escopo="estadual", uf=calendario.uf)
    if calendario.ibge:
        escopo |= Q(escopo="municipal", ibge=calendario.ibge)

    return {
        f.data: f.nome
        for f in Feriado.objects.filter(escopo, data__gte=inicio, data__lte=fim)
    }


def base_de_feriados_sincronizada() -> bool:
    """A tabela de feriados do `modulocalendar` está populada?

    **Achado no teste de fumaça da PDCA.0**, e é a diferença entre um cálculo
    certo e um cálculo mudo: a tabela é global e nasce **vazia** — quem a enche é
    o comando `sincronizar_feriados`. Sem esta pergunta, um calendário com
    `considera_feriados=True` responde "5 dias úteis" para uma semana com
    feriado, sem nada na resposta indicando que a base não foi carregada. O
    número estaria errado e pareceria certo, que é o pior dos dois mundos e o
    oposto da régua de dado honesto da casa.
    """
    from modulocalendar.models import Feriado

    return Feriado.objects.exists()


def _excecoes(calendario: CalendarioTrabalho, inicio: date, fim: date) -> dict:
    return {
        e.data: e.trabalha
        for e in ExcecaoCalendario.objects.filter(
            calendario=calendario, data__gte=inicio, data__lte=fim
        )
    }


def eh_dia_util(calendario: CalendarioTrabalho, dia: date, *,
                feriados: dict | None = None, excecoes: dict | None = None) -> bool:
    """A ordem de precedência, do mais específico para o mais geral: **exceção**
    do dia > **feriado** > regra da semana. É o que faz o mutirão de sábado
    valer mesmo caindo em feriado, e o recesso vencer a segunda-feira."""
    if excecoes is None:
        excecoes = _excecoes(calendario, dia, dia)
    if dia in excecoes:
        return excecoes[dia]
    if feriados is None:
        feriados = feriados_do_periodo(calendario, dia, dia)
    if dia in feriados:
        return False
    return calendario.dias_da_semana[dia.weekday()]


def dias_uteis(calendario: CalendarioTrabalho, inicio: date, fim: date) -> int:
    """Quantos dias se trabalha entre duas datas, **incluindo as duas pontas**.
    Uma atividade que começa e termina na segunda dura 1 dia, não 0."""
    if fim < inicio:
        return 0
    feriados = feriados_do_periodo(calendario, inicio, fim)
    excecoes = _excecoes(calendario, inicio, fim)
    total = 0
    dia = inicio
    while dia <= fim:
        if eh_dia_util(calendario, dia, feriados=feriados, excecoes=excecoes):
            total += 1
        dia += timedelta(days=1)
    return total


def proximo_dia_util(calendario: CalendarioTrabalho, dia: date) -> date:
    """O próprio dia, se já for útil; senão o primeiro seguinte que for."""
    caminhados = 0
    while not eh_dia_util(calendario, dia):
        dia += timedelta(days=1)
        caminhados += 1
        if caminhados > _MAXIMO_DIAS_CAMINHADOS:
            raise ValidationError(
                f"O calendário '{calendario.nome}' não tem nenhum dia útil — "
                "marque ao menos um dia da semana."
            )
    return dia


def somar_dias_uteis(calendario: CalendarioTrabalho, inicio: date, duracao: int) -> date:
    """A data de término de uma atividade que começa em `inicio` e dura `duracao`
    dias úteis. **O dia de início conta como o primeiro** — é a convenção do MS
    Project e do P6, e é a que o planejador espera: duração 1 termina no mesmo
    dia."""
    if duracao < 1:
        raise ValidationError("A duração em dias úteis precisa ser pelo menos 1.")
    dia = proximo_dia_util(calendario, inicio)
    restantes = duracao - 1
    caminhados = 0
    while restantes > 0:
        dia += timedelta(days=1)
        caminhados += 1
        if caminhados > _MAXIMO_DIAS_CAMINHADOS:
            raise ValidationError(
                f"O calendário '{calendario.nome}' não tem dias úteis suficientes "
                f"para uma duração de {duracao} dias."
            )
        if eh_dia_util(calendario, dia):
            restantes -= 1
    return dia


def calendario_da_obra(obra, *, tenant_id: int) -> CalendarioTrabalho | None:
    """O da obra, se houver; senão o padrão da empresa; senão `None` — e `None`
    é resposta honesta, não erro: a empresa ainda não disse quando trabalha."""
    proprio = CalendarioTrabalho.objects.filter(
        tenant_id=tenant_id, obra=obra, ativo=True
    ).first()
    if proprio is not None:
        return proprio
    return CalendarioTrabalho.objects.filter(
        tenant_id=tenant_id, padrao=True, ativo=True
    ).first()


# ---------------------------------------------------------------------------
# 3. O CPM — de duração para datas, e de datas para caminho crítico
# ---------------------------------------------------------------------------
# Guarda-corpo do caminhamento do calendário no CPM. Não é limite de produto
# (§5.6 do `planos.py`): é o fundo do poço de um laço que anda um dia por vez.
# Um cronograma de 5.000 atividades encadeadas de 1 dia consome ~5.000 dias
# úteis, que são ~19 anos corridos; 30 anos é a ordem de grandeza acima disso, e
# curta o bastante para o calendário quebrado aparecer como erro em vez de como
# espera infinita.
_MAXIMO_DIAS_CORRIDOS_CPM = 365 * 30

#: Quantos dias corridos o carregador de calendário busca por lote. Cada lote é
#: uma consulta de feriados e uma de exceções; 400 cobre um ano com folga, então
#: o cronograma típico carrega tudo em um ou dois lotes.
_JANELA_DE_CARGA = 400


class CalendarioEmMemoria:
    """Um `CalendarioTrabalho` carregado de uma vez, para o CPM não consultar o
    banco a cada dia caminhado.

    **É a diferença entre milissegundos e minutos.** As funções da §2 aceitam
    `feriados`/`excecoes` já carregados, mas quem as chama sem esses argumentos
    faz uma consulta *por dia examinado* — e o CPM examina cada dia de cada
    atividade, várias vezes (ida, volta e folga). Aqui os feriados e as exceções
    entram em lote, e a lista de dias úteis vira um índice: perguntar "que dia é
    12 dias úteis depois deste?" passa a ser uma soma de inteiros.

    O índice é **por calendário**: uma atividade de turno da noite e outra de
    expediente normal têm listas diferentes, e comparar índices entre as duas não
    significaria nada. Por isso toda conta que atravessa dois calendários passa
    por **data**, que é a única linguagem comum aos dois.
    """

    def __init__(self, calendario: CalendarioTrabalho, ancora: date):
        self.calendario = calendario
        self.ancora = ancora
        self._dias: list[date] = []
        self._indice: dict[date, int] = {}
        self._cursor = ancora
        self._feriados: dict[date, str] = {}
        self._excecoes: dict[date, bool] = {}
        self._carregado_ate: date | None = None
        self._caminhados = 0

    # -- carga -------------------------------------------------------------
    def _carregar_ate(self, limite: date) -> None:
        if self._carregado_ate is not None and self._carregado_ate >= limite:
            return
        inicio = self._cursor if self._carregado_ate is None else self._carregado_ate + timedelta(days=1)
        fim = max(limite, inicio + timedelta(days=_JANELA_DE_CARGA))
        self._feriados.update(feriados_do_periodo(self.calendario, inicio, fim))
        self._excecoes.update(_excecoes(self.calendario, inicio, fim))
        self._carregado_ate = fim

    def _util(self, dia: date) -> bool:
        self._carregar_ate(dia)
        if dia in self._excecoes:
            return self._excecoes[dia]
        if dia in self._feriados:
            return False
        return self.calendario.dias_da_semana[dia.weekday()]

    def _crescer_ate_data(self, alvo: date) -> None:
        """Estende a lista até cobrir `alvo` (dia útil ou não)."""
        while self._cursor <= alvo:
            if self._util(self._cursor):
                self._indice[self._cursor] = len(self._dias)
                self._dias.append(self._cursor)
            self._cursor += timedelta(days=1)
            self._caminhados += 1
            self._estourou()

    def _crescer_ate_indice(self, alvo: int) -> None:
        """Estende a lista até ter ao menos `alvo + 1` dias úteis."""
        while len(self._dias) <= alvo:
            if self._util(self._cursor):
                self._indice[self._cursor] = len(self._dias)
                self._dias.append(self._cursor)
            self._cursor += timedelta(days=1)
            self._caminhados += 1
            self._estourou()

    def _estourou(self) -> None:
        if self._caminhados > _MAXIMO_DIAS_CORRIDOS_CPM:
            raise ValidationError(
                f"O calendário '{self.calendario.nome}' não produz dias úteis suficientes "
                "para este cronograma — verifique se algum dia da semana está marcado como "
                "trabalhado e se as exceções não param a obra indefinidamente."
            )

    # -- conversões --------------------------------------------------------
    def indice_adiante(self, dia: date) -> int:
        """Índice do primeiro dia útil **igual ou posterior** a `dia`."""
        self._crescer_ate_data(dia)
        while True:
            achado = self._indice.get(dia)
            if achado is not None:
                return achado
            dia += timedelta(days=1)
            self._crescer_ate_data(dia)

    def indice_atras(self, dia: date) -> int:
        """Índice do último dia útil **igual ou anterior** a `dia`.

        Devolve 0 quando `dia` é anterior a toda a régua: a âncora do cronograma
        é o chão do mundo, e nenhuma atividade começa antes dela.
        """
        self._crescer_ate_data(dia)
        limite = dia
        while limite >= self.ancora:
            achado = self._indice.get(limite)
            if achado is not None:
                return achado
            limite -= timedelta(days=1)
        return 0

    def data(self, indice: int) -> date:
        if indice < 0:
            indice = 0
        self._crescer_ate_indice(indice)
        return self._dias[indice]

    def entre(self, inicio: date, fim: date) -> int:
        """Dias úteis de `inicio` a `fim`, **incluindo as duas pontas**."""
        if fim < inicio:
            return 0
        return self.indice_atras(fim) - self.indice_adiante(inicio) + 1


def _calendarios_do_cronograma(cronograma: Cronograma,
                               atividades: list[Atividade]) -> dict[int, CalendarioEmMemoria]:
    """Um `CalendarioEmMemoria` por calendário citado, carregado uma vez só.

    A âncora recua 90 dias antes do início do plano para dar espaço à antecipação
    (*lead*, atraso negativo) e à atividade cuja restrição de data é anterior ao
    plano — sem isso, uma conta intermediária cairia antes do começo da régua.
    """
    ancora = cronograma.data_inicio
    for a in atividades:
        if a.nao_comecar_antes_de and a.nao_comecar_antes_de < ancora:
            ancora = a.nao_comecar_antes_de
    ancora -= timedelta(days=90)

    usados: dict[int, CalendarioTrabalho] = {}
    if cronograma.calendario_id:
        usados[cronograma.calendario_id] = cronograma.calendario
    for a in atividades:
        if a.calendario_id and a.calendario_id not in usados:
            usados[a.calendario_id] = a.calendario
    return {cid: CalendarioEmMemoria(cal, ancora) for cid, cal in usados.items()}


def _ordem_topologica(folhas: list[Atividade],
                      ligacoes: list[Precedencia]) -> list[int]:
    """Ordem em que as atividades podem ser calculadas — e o **ciclo** nomeado
    quando não existe ordem nenhuma.

    Um ciclo ("A depois de B, B depois de A") não é caso raro: é o que acontece
    quando o planejador liga a barra errada no Gantt. Devolver "erro ao calcular"
    faria dele um mistério; devolver os códigos das atividades envolvidas faz
    dele um conserto de dez segundos.
    """
    grau = {a.atividade_id: 0 for a in folhas}
    saidas: dict[int, list[int]] = {a.atividade_id: [] for a in folhas}
    for lig in ligacoes:
        saidas[lig.origem_id].append(lig.destino_id)
        grau[lig.destino_id] += 1

    fila = [aid for aid, g in grau.items() if g == 0]
    ordem: list[int] = []
    while fila:
        atual = fila.pop()
        ordem.append(atual)
        for seguinte in saidas[atual]:
            grau[seguinte] -= 1
            if grau[seguinte] == 0:
                fila.append(seguinte)

    if len(ordem) != len(folhas):
        presos = {a.atividade_id: a for a in folhas if grau[a.atividade_id] > 0}
        nomes = ", ".join(sorted(f"{a.codigo} {a.nome}".strip() for a in list(presos.values())[:8]))
        raise ValidationError(
            "As precedências formam um ciclo — há atividades que dependem umas das "
            f"outras em círculo e nenhuma pode começar. Envolvidas: {nomes}."
        )
    return ordem


def calcular_cpm(cronograma: Cronograma, *, gravar: bool = True) -> dict:
    """O método do caminho crítico sobre o cronograma inteiro.

    Devolve datas cedo e tarde, folga total e livre, o **caminho crítico** e o
    término do projeto. Grava tudo em coluna por padrão — a tela lê a árvore
    inteira de uma vez, e recalcular a cada leitura poria o servidor a fazer o
    mesmo trabalho várias vezes por segundo para um resultado que não mudou.

    **Só a folha entra no grafo.** A sintética é o intervalo dos filhos, apurado
    depois, de baixo para cima. Precedência ligada a uma sintética é recusada na
    escrita (serializer), e não aqui: erro barrado na entrada tem endereço; erro
    barrado no cálculo vira "o cronograma não calcula".

    A aritmética interna usa **término exclusivo** — a atividade ocupa
    `[inicio, inicio + duração)`. É o que faz o marco (duração zero) ser um
    instante sem virar caso especial em cada conta, e o que dá a regra do FS de
    graça: a sucessora começa onde a predecessora termina.
    """
    relogio = time.monotonic()

    atividades = list(
        cronograma.atividades.select_related("calendario").all()
    )
    if not atividades:
        raise ValidationError("O cronograma não tem nenhuma atividade para calcular.")
    if len(atividades) > PDCA_TETO_CPM_SINCRONO:
        raise ValidationError(
            f"Este cronograma tem {len(atividades)} atividades e o recálculo dentro da "
            f"requisição vai até {PDCA_TETO_CPM_SINCRONO}."
        )

    com_filhos = {a.pai_id for a in atividades if a.pai_id}
    folhas = [a for a in atividades if a.atividade_id not in com_filhos]
    sinteticas = [a for a in atividades if a.atividade_id in com_filhos]
    por_id = {a.atividade_id: a for a in atividades}

    ids_folha = {a.atividade_id for a in folhas}
    ligacoes = [
        lig for lig in Precedencia.objects.filter(
            origem__cronograma=cronograma
        ).only("origem_id", "destino_id", "tipo", "atraso_dias")
        if lig.origem_id in ids_folha and lig.destino_id in ids_folha
    ]

    if cronograma.calendario_id is None and any(a.calendario_id is None for a in folhas):
        raise ValidationError(
            "Há atividades sem calendário e o cronograma não tem um padrão. "
            "Defina o calendário do cronograma — sem ele, converter duração em data "
            "seria inventar quando a obra trabalha."
        )

    calendarios = _calendarios_do_cronograma(cronograma, atividades)

    def cal_de(a: Atividade) -> CalendarioEmMemoria:
        return calendarios[a.calendario_id or cronograma.calendario_id]

    def duracao_de(a: Atividade) -> int:
        if a.eh_marco:
            return 0
        return int(a.duracao_dias or 1)

    ordem = _ordem_topologica(folhas, ligacoes)
    entradas: dict[int, list[Precedencia]] = {a.atividade_id: [] for a in folhas}
    saidas: dict[int, list[Precedencia]] = {a.atividade_id: [] for a in folhas}
    for lig in ligacoes:
        entradas[lig.destino_id].append(lig)
        saidas[lig.origem_id].append(lig)

    # --- ida: as datas cedo ------------------------------------------------
    inicio_cedo: dict[int, date] = {}
    termino_cedo: dict[int, date] = {}
    #: O que **cada ligação** implicou para a sucessora. É a matéria-prima da
    #: folga livre: sem guardar isto, saber quanto uma atividade pode atrasar sem
    #: empurrar a seguinte exigiria refazer a ida inteira por atividade.
    implicado: dict[int, date] = {}

    for aid in ordem:
        a = por_id[aid]
        cal = cal_de(a)
        dur = duracao_de(a)

        piso = cronograma.data_inicio
        if a.nao_comecar_antes_de and a.nao_comecar_antes_de > piso:
            piso = a.nao_comecar_antes_de
        indice = cal.indice_adiante(piso)

        for lig in entradas[aid]:
            p = por_id[lig.origem_id]
            atraso = lig.atraso_dias
            if lig.tipo == Precedencia.Tipo.FS:
                base = cal.indice_adiante(termino_cedo[p.atividade_id] + timedelta(days=1))
                candidato = base + atraso
            elif lig.tipo == Precedencia.Tipo.SS:
                candidato = cal.indice_adiante(inicio_cedo[p.atividade_id]) + atraso
            elif lig.tipo == Precedencia.Tipo.FF:
                fim = cal.indice_adiante(termino_cedo[p.atividade_id]) + atraso
                candidato = fim - max(dur - 1, 0)
            else:  # SF
                fim = cal.indice_adiante(inicio_cedo[p.atividade_id]) + atraso
                candidato = fim - max(dur - 1, 0)
            candidato = max(candidato, 0)
            implicado[lig.precedencia_id] = cal.data(candidato)
            if candidato > indice:
                indice = candidato

        inicio_cedo[aid] = cal.data(indice)
        termino_cedo[aid] = cal.data(indice + dur - 1) if dur >= 1 else cal.data(indice)

        if time.monotonic() - relogio > PDCA_CPM_SEGUNDOS:
            raise ValidationError(
                f"O recálculo passou de {PDCA_CPM_SEGUNDOS}s e foi interrompido. "
                "Verifique se há precedências em excesso ou reduza o cronograma."
            )

    fim_do_projeto = max(termino_cedo.values())

    # --- volta: as datas tarde --------------------------------------------
    inicio_tarde: dict[int, date] = {}
    termino_tarde: dict[int, date] = {}

    for aid in reversed(ordem):
        a = por_id[aid]
        cal = cal_de(a)
        dur = duracao_de(a)

        if not saidas[aid]:
            fim_indice = cal.indice_atras(fim_do_projeto)
        else:
            fim_indice = None
            for lig in saidas[aid]:
                sucessora = por_id[lig.destino_id]
                cal_s = cal_de(sucessora)
                atraso = lig.atraso_dias
                if lig.tipo == Precedencia.Tipo.FS:
                    limite = cal_s.data(
                        max(cal_s.indice_adiante(inicio_tarde[sucessora.atividade_id]) - atraso, 0)
                    )
                    candidato = cal.indice_atras(limite - timedelta(days=1))
                elif lig.tipo == Precedencia.Tipo.SS:
                    limite = cal_s.data(
                        max(cal_s.indice_adiante(inicio_tarde[sucessora.atividade_id]) - atraso, 0)
                    )
                    candidato = cal.indice_atras(limite) + max(dur - 1, 0)
                elif lig.tipo == Precedencia.Tipo.FF:
                    limite = cal_s.data(
                        max(cal_s.indice_atras(termino_tarde[sucessora.atividade_id]) - atraso, 0)
                    )
                    candidato = cal.indice_atras(limite)
                else:  # SF
                    limite = cal_s.data(
                        max(cal_s.indice_atras(termino_tarde[sucessora.atividade_id]) - atraso, 0)
                    )
                    candidato = cal.indice_atras(limite) + max(dur - 1, 0)
                fim_indice = candidato if fim_indice is None else min(fim_indice, candidato)

        fim_indice = max(fim_indice, 0)
        termino_tarde[aid] = cal.data(fim_indice)
        inicio_tarde[aid] = cal.data(max(fim_indice - max(dur - 1, 0), 0))

    # --- folgas e criticidade ---------------------------------------------
    folga_total: dict[int, int] = {}
    folga_livre: dict[int, int] = {}
    for aid in ordem:
        a = por_id[aid]
        cal = cal_de(a)
        total = max(cal.entre(inicio_cedo[aid], inicio_tarde[aid]) - 1, 0)
        folga_total[aid] = total

        if not saidas[aid]:
            livre = total
        else:
            livre = total
            for lig in saidas[aid]:
                sucessora = por_id[lig.destino_id]
                cal_s = cal_de(sucessora)
                sobra = max(
                    cal_s.entre(
                        implicado.get(lig.precedencia_id, inicio_cedo[sucessora.atividade_id]),
                        inicio_cedo[sucessora.atividade_id],
                    ) - 1,
                    0,
                )
                livre = min(livre, sobra)
        folga_livre[aid] = min(livre, total)

    # --- de baixo para cima: a sintética é o intervalo dos filhos ----------
    for a in sorted(sinteticas, key=lambda x: -x.profundidade):
        filhos = [f for f in atividades if f.pai_id == a.atividade_id]
        calculados = [f for f in filhos if f.atividade_id in inicio_cedo]
        if not calculados:
            continue
        ids = [f.atividade_id for f in calculados]
        inicio_cedo[a.atividade_id] = min(inicio_cedo[i] for i in ids)
        termino_cedo[a.atividade_id] = max(termino_cedo[i] for i in ids)
        inicio_tarde[a.atividade_id] = min(inicio_tarde[i] for i in ids)
        termino_tarde[a.atividade_id] = max(termino_tarde[i] for i in ids)
        folga_total[a.atividade_id] = min(folga_total[i] for i in ids)
        folga_livre[a.atividade_id] = min(folga_livre[i] for i in ids)

    criticas = set()
    for aid, total in folga_total.items():
        if total == 0:
            criticas.add(aid)

    for a in atividades:
        aid = a.atividade_id
        a.inicio_cedo = inicio_cedo.get(aid)
        a.termino_cedo = termino_cedo.get(aid)
        a.inicio_tarde = inicio_tarde.get(aid)
        a.termino_tarde = termino_tarde.get(aid)
        a.folga_total = folga_total.get(aid)
        a.folga_livre = folga_livre.get(aid)
        a.critica = aid in criticas

    if gravar:
        with transaction.atomic():
            Atividade.objects.bulk_update(
                atividades,
                ["inicio_cedo", "termino_cedo", "inicio_tarde", "termino_tarde",
                 "folga_total", "folga_livre", "critica"],
                batch_size=500,
            )
            Cronograma.objects.filter(pk=cronograma.pk).update(
                calculado_em=timezone.now(), termino_calculado=fim_do_projeto,
            )
            cronograma.calculado_em = timezone.now()
            cronograma.termino_calculado = fim_do_projeto

    return {
        "atividades": len(atividades),
        "folhas": len(folhas),
        "precedencias": len(ligacoes),
        "inicio": cronograma.data_inicio,
        "termino": fim_do_projeto,
        "duracao_dias_uteis": (
            calendarios[cronograma.calendario_id].entre(cronograma.data_inicio, fim_do_projeto)
            if cronograma.calendario_id else None
        ),
        "criticas": sorted(criticas),
        "caminho_critico": [
            por_id[i].codigo for i in ordem if i in criticas
        ],
        "segundos": round(time.monotonic() - relogio, 3),
        # A base de feriados é global e nasce vazia. Um cronograma calculado sem
        # ela devolve datas que ignoram o feriado sem dizer — número errado com
        # cara de certo, o mesmo defeito que a PDCA.0 fechou no calendário.
        "feriados_sincronizados": base_de_feriados_sincronizada(),
    }


# ---------------------------------------------------------------------------
# 4. Versionamento — publicar, replanejar, e a linha de base que sobra
# ---------------------------------------------------------------------------


def validar_profundidade_wbs(pai: Atividade | None, *, quantos_niveis: int = 1) -> None:
    final = (1 if pai is None else pai.profundidade + 1) + quantos_niveis - 1
    if final > PDCA_PROFUNDIDADE_MAXIMA_WBS:
        raise ValidationError(
            f"A WBS vai até {PDCA_PROFUNDIDADE_MAXIMA_WBS} níveis; "
            f"esta atividade chegaria ao nível {final}."
        )


def validar_teto_de_atividades(cronograma: Cronograma, *, acrescentando: int = 1) -> None:
    atual = Atividade.objects.filter(cronograma=cronograma).count()
    if atual + acrescentando > PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA:
        raise ValidationError(
            f"O cronograma já tem {_milhar(atual)} atividades e o limite é "
            f"{_milhar(PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA)}."
        )


def publicar(cronograma: Cronograma, *, por: str = "") -> dict:
    """Rascunho → vigente, com o CPM rodado **antes** de virar a chave.

    Publicar um plano cujas datas nunca foram calculadas seria publicar barras
    desenhadas à mão: o prazo vigente é a régua contra a qual o atraso da obra
    inteira será medido, e ele precisa ser resultado de conta, não de digitação.

    A versão vigente anterior é rebaixada a `substituido` **na mesma transação** —
    é o que garante que a constraint de um vigente por obra nunca veja duas.
    """
    if cronograma.status != Cronograma.Status.RASCUNHO:
        raise ValidationError("Só um cronograma em rascunho pode ser publicado.")

    resultado = calcular_cpm(cronograma)

    with transaction.atomic():
        (Cronograma.objects
         .filter(tenant_id=cronograma.tenant_id, obra_id=cronograma.obra_id,
                 status=Cronograma.Status.VIGENTE)
         .exclude(pk=cronograma.pk)
         .update(status=Cronograma.Status.SUBSTITUIDO))
        cronograma.status = Cronograma.Status.VIGENTE
        cronograma.publicado_em = timezone.now()
        cronograma.publicado_por = (por or "")[:150]
        cronograma.save(update_fields=["status", "publicado_em", "publicado_por"])

    return resultado


def replanejar(cronograma: Cronograma, *, motivo: str) -> Cronograma:
    """Cria a versão seguinte como cópia integral desta, em rascunho.

    **O motivo é obrigatório** e é o que dá sentido à linha de base: se o plano
    pode mudar sem justificativa declarada, comparar o vigente com a versão
    anterior não responde nada — vira duas fotos sem legenda.

    A cópia é integral (atividades e precedências) porque a linha de base tem de
    continuar legível **inteira**. Guardar só o que mudou pouparia linhas e
    tiraria da versão antiga a capacidade de ser lida sozinha, que é justamente
    para o que ela existe.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError(
            "Replanejar exige o motivo — é ele que transforma a versão anterior "
            "numa linha de base com legenda."
        )
    if cronograma.status == Cronograma.Status.RASCUNHO:
        raise ValidationError(
            "Este cronograma ainda é rascunho: edite-o em vez de criar outra versão."
        )

    ultima = (Cronograma.objects
              .filter(tenant_id=cronograma.tenant_id, obra_id=cronograma.obra_id)
              .order_by("-versao").first())
    proxima = (ultima.versao if ultima else cronograma.versao) + 1
    if proxima > PDCA_TETO_VERSOES_POR_CRONOGRAMA:
        raise ValidationError(
            f"Esta obra já tem {proxima - 1} versões de cronograma e o limite é "
            f"{PDCA_TETO_VERSOES_POR_CRONOGRAMA}."
        )

    with transaction.atomic():
        nova = Cronograma.objects.create(
            tenant_id=cronograma.tenant_id,
            obra_id=cronograma.obra_id,
            descricao=cronograma.descricao,
            versao=proxima,
            status=Cronograma.Status.RASCUNHO,
            data_inicio=cronograma.data_inicio,
            calendario_id=cronograma.calendario_id,
            origem=cronograma,
            motivo_replanejamento=motivo,
        )

        copiar_estrutura(cronograma, nova, manter_vinculos_da_obra=True)

    return nova


def copiar_estrutura(origem: Cronograma, destino: Cronograma, *,
                     manter_vinculos_da_obra: bool) -> dict[int, int]:
    """Copia a WBS inteira e a rede de `origem` para `destino`.

    Existe em função separada porque tem **dois** clientes com necessidades
    opostas, e a diferença entre eles é uma linha de correção, não de estilo:

    - **replanejar** copia dentro da mesma obra, e por isso mantém os vínculos:
      o local, a etapa e o item orçado continuam existindo e continuam sendo os
      certos;
    - **aplicar um modelo** copia para **outra** obra, e aí os mesmos vínculos
      apontariam para o esqueleto, o orçamento e as etapas da obra de origem. Um
      cronograma da Obra B ponderando o avanço pelo orçamento da Obra A é um erro
      que ninguém vê na tela e que sai no boletim de medição.

    O `responsavel` sobrevive nos dois casos: funcionário é da empresa, não da
    obra. O `calendario` da atividade só sobrevive quando é da empresa (sem obra)
    ou da obra de destino — expediente de outra obra é dado de outra obra.

    Devolve o mapa `id antigo -> id novo`, que é o que a rede precisa para ser
    religada.
    """
    antigas = list(origem.atividades.all().order_by("profundidade", "atividade_id"))
    traducao: dict[int, int] = {}
    for velha in antigas:
        calendario_id = velha.calendario_id
        if calendario_id and not manter_vinculos_da_obra:
            calendario_id = (
                velha.calendario_id
                if velha.calendario and velha.calendario.obra_id in (None, destino.obra_id)
                else None
            )
        copia = Atividade.objects.create(
            tenant_id=destino.tenant_id,
            cronograma=destino,
            pai_id=traducao.get(velha.pai_id) if velha.pai_id else None,
            codigo=velha.codigo, nome=velha.nome, ordem=velha.ordem,
            profundidade=velha.profundidade,
            duracao_dias=velha.duracao_dias, eh_marco=velha.eh_marco,
            nao_comecar_antes_de=(
                velha.nao_comecar_antes_de if manter_vinculos_da_obra else None
            ),
            calendario_id=calendario_id,
            local_id=velha.local_id if manter_vinculos_da_obra else None,
            etapa_id=velha.etapa_id if manter_vinculos_da_obra else None,
            item_orcado_id=velha.item_orcado_id if manter_vinculos_da_obra else None,
            peso_informado=velha.peso_informado,
            responsavel_id=velha.responsavel_id,
            observacao=velha.observacao,
        )
        traducao[velha.atividade_id] = copia.atividade_id

    Precedencia.objects.bulk_create([
        Precedencia(
            tenant_id=destino.tenant_id,
            origem_id=traducao[lig.origem_id],
            destino_id=traducao[lig.destino_id],
            tipo=lig.tipo, atraso_dias=lig.atraso_dias,
        )
        for lig in Precedencia.objects.filter(origem__cronograma=origem)
        if lig.origem_id in traducao and lig.destino_id in traducao
    ], batch_size=500)

    return traducao


def linha_de_base(cronograma: Cronograma) -> Cronograma | None:
    """A versão contra a qual este plano é comparado.

    É a **origem** — a versão de que este nasceu —, e não a primeira de todas. A
    pergunta que o planejador faz é *"atrasou quanto desde o último combinado?"*,
    e responder com o plano de dois replanejamentos atrás mediria um desvio que
    já foi discutido e aceito.
    """
    if cronograma.origem_id:
        return cronograma.origem
    return None


def comparar_com_base(cronograma: Cronograma) -> dict:
    """Atividade a atividade, o deslocamento entre este plano e a linha de base.

    O pareamento é pelo **código** da atividade, não pelo id: a cópia do
    replanejamento gera ids novos, e é o código da EAP que sobrevive à versão —
    o mesmo motivo pelo qual ele existe.
    """
    base = linha_de_base(cronograma)
    if base is None:
        return {"tem_base": False, "base": None, "linhas": []}

    antigas = {a.codigo: a for a in base.atividades.all()}
    linhas = []
    for a in cronograma.atividades.all():
        velha = antigas.get(a.codigo)
        if velha is None:
            linhas.append({
                "codigo": a.codigo, "nome": a.nome, "situacao": "nova",
                "base_inicio": None, "base_termino": None,
                "inicio": a.inicio_cedo, "termino": a.termino_cedo,
                "desvio_dias": None,
            })
            continue
        desvio = None
        if a.termino_cedo and velha.termino_cedo:
            desvio = (a.termino_cedo - velha.termino_cedo).days
        linhas.append({
            "codigo": a.codigo, "nome": a.nome,
            "situacao": "mantida" if desvio in (0, None) else ("atrasada" if desvio > 0 else "adiantada"),
            "base_inicio": velha.inicio_cedo, "base_termino": velha.termino_cedo,
            "inicio": a.inicio_cedo, "termino": a.termino_cedo,
            "desvio_dias": desvio,
        })

    sumidas = set(antigas) - {a.codigo for a in cronograma.atividades.all()}
    for codigo in sorted(sumidas):
        velha = antigas[codigo]
        linhas.append({
            "codigo": codigo, "nome": velha.nome, "situacao": "removida",
            "base_inicio": velha.inicio_cedo, "base_termino": velha.termino_cedo,
            "inicio": None, "termino": None, "desvio_dias": None,
        })

    return {
        "tem_base": True,
        "base": {"cronograma_id": base.cronograma_id, "versao": base.versao,
                 "termino": base.termino_calculado},
        "linhas": linhas,
    }


# ---------------------------------------------------------------------------
# 5. O peso — e de onde ele veio
# ---------------------------------------------------------------------------


def peso_de(atividade: Atividade) -> tuple[Decimal | None, str]:
    """`(peso, origem)`, e a origem viaja junto de propósito.

    Vinculada ao orçamento, a atividade **vale o que o item vale** — é o que faz
    o avanço da PDCA.2 virar dinheiro sem digitação. Sem vínculo, vale o peso que
    o planejador informou. Sem nenhum dos dois, vale `None` — e `None` é resposta
    honesta: a atividade ainda não tem como ponderar o pai, e devolver zero aqui
    faria o avanço do pai parecer calculado quando não é (planta §5.4).
    """
    if atividade.item_orcado_id and atividade.item_orcado is not None:
        return (atividade.item_orcado.total_com_bdi, "orcado")
    if atividade.peso_informado is not None:
        return (atividade.peso_informado, "informado")
    return (None, "")


def cobertura_do_orcamento(cronograma: Cronograma) -> dict:
    """Quantas atividades têm régua de custo — no molde do `realizado_cobertura`
    do Orçamento (planta §11.1).

    Vínculo que não existe **não é inventado**: em vez de somar só o que tem
    vínculo e apresentar o total como se fosse o do cronograma, a resposta diz
    quantas linhas ficaram de fora. É a diferença entre um número e um número com
    denominador.
    """
    total = 0
    com_orcado = 0
    com_informado = 0
    valor = Decimal("0")
    for a in cronograma.atividades.select_related("item_orcado").all():
        if a.filhos.exists():
            continue
        total += 1
        peso, origem = peso_de(a)
        if origem == "orcado":
            com_orcado += 1
            valor += peso or Decimal("0")
        elif origem == "informado":
            com_informado += 1
    return {
        "folhas": total,
        "com_item_orcado": com_orcado,
        "com_peso_informado": com_informado,
        "sem_peso": total - com_orcado - com_informado,
        "valor_orcado_vinculado": valor,
        "cobertura": round(com_orcado / total, 4) if total else None,
    }


# ---------------------------------------------------------------------------
# Plano modelo (PDCA.1b) — a biblioteca de padrões da construtora
# ---------------------------------------------------------------------------
#
# *Decisão do dono, 23/08/2026, respondendo à D116:* **"deixa o plano para poder
# ser usado como modelo em outra obra... para não ter que criar 300 planos em um
# empreendimento grande"**.
#
# O caso é real e é o mais comum de todos: um empreendimento de 300 unidades
# repete a mesma sequência construtiva 300 vezes. Montar isso à mão é o que faz
# a construtora desistir do planejamento e voltar para a planilha.

def marcar_como_modelo(cronograma: Cronograma, *, nome: str) -> Cronograma:
    """Promove um cronograma a modelo da biblioteca da empresa.

    A trava de nome está no banco (constraint condicional), e a checagem aqui
    existe para a mensagem: "já existe um modelo com esse nome" é acionável;
    `IntegrityError` não é.

    **A quota é do plano e é checada na view**, com o mecanismo de sempre
    (`nucleo.quotas`) — aqui não se decide comércio.
    """
    nome = (nome or "").strip()
    if not nome:
        raise ValidationError(
            "O modelo precisa de nome — é por ele que alguém o escolhe seis meses "
            "depois, e 'Plano da Obra 47 v3' não diz o que ele padroniza."
        )
    if not cronograma.atividades.exists():
        raise ValidationError(
            "Este cronograma não tem atividade nenhuma: não há padrão a guardar."
        )
    colisao = (Cronograma.objects
               .filter(tenant_id=cronograma.tenant_id, eh_modelo=True, nome_modelo__iexact=nome)
               .exclude(pk=cronograma.pk)
               .first())
    if colisao is not None:
        raise ValidationError(
            f"Já existe um plano modelo chamado '{colisao.nome_modelo}'. "
            "Dois com o mesmo nome é a forma mais rápida de alguém aplicar o "
            "padrão errado numa obra inteira."
        )

    cronograma.eh_modelo = True
    cronograma.nome_modelo = nome
    cronograma.save(update_fields=["eh_modelo", "nome_modelo", "atualizado_em"])
    return cronograma


def desmarcar_modelo(cronograma: Cronograma) -> Cronograma:
    """Tira o cronograma da biblioteca. O plano continua existindo — o que sai é
    a marca, e com ela a vaga na quota."""
    cronograma.eh_modelo = False
    cronograma.nome_modelo = ""
    cronograma.save(update_fields=["eh_modelo", "nome_modelo", "atualizado_em"])
    return cronograma


def aplicar_modelo(modelo: Cronograma, *, obra, descricao: str, data_inicio,
                   calendario=None) -> Cronograma:
    """Cria o cronograma de `obra` a partir de um modelo.

    O que nasce é um **rascunho v1 comum**: não é modelo (senão aplicar um padrão
    encheria a biblioteca de cópias e a quota junto), não é vigente (quem assume
    o prazo é quem publica, e essa decisão não vem de graça com o padrão) e não
    tem `origem` (a linha de base é o fio entre versões da mesma obra; o modelo é
    de outra obra, e apontar para ele mediria o desvio contra um plano que nunca
    foi combinado com este cliente).

    As datas não são copiadas — são **recalculadas**: o modelo guarda durações e
    rede, que é o que se repete; o calendário e a âncora são da obra nova.
    """
    if not modelo.eh_modelo:
        raise ValidationError("Este cronograma não está marcado como modelo.")

    existente = (Cronograma.objects
                 .filter(tenant_id=modelo.tenant_id, obra_id=obra.pk)
                 .order_by("-versao").first())
    if existente is not None:
        raise ValidationError(
            f"Esta obra já tem cronograma (v{existente.versao}). Aplicar um modelo "
            "cria o primeiro plano da obra — para trocar o plano de uma obra que "
            "já tem, replaneje."
        )

    with transaction.atomic():
        novo = Cronograma.objects.create(
            tenant_id=modelo.tenant_id,
            obra_id=obra.pk,
            descricao=(descricao or modelo.descricao).strip(),
            versao=1,
            status=Cronograma.Status.RASCUNHO,
            data_inicio=data_inicio,
            calendario_id=(calendario.pk if calendario is not None else None),
        )
        copiar_estrutura(modelo, novo, manter_vinculos_da_obra=False)

    return novo


def modelos_do_tenant(tenant_id):
    """A biblioteca, pronta para o seletor da tela."""
    return (Cronograma.objects
            .filter(tenant_id=tenant_id, eh_modelo=True)
            .order_by("nome_modelo"))


# ---------------------------------------------------------------------------
# Escrita em lote — o gesto de colar uma planilha, numa requisição
# ---------------------------------------------------------------------------

#: Só o que a grade edita. A lista é branca de propósito: `pai`, `cronograma` e
#: `tenant` mudam a estrutura ou a dona da linha, e nenhum dos dois é gesto de
#: planilha — quem os mexe passa pelo caminho normal, com validação inteira.
CAMPOS_DO_LOTE = frozenset({
    "codigo", "nome", "duracao_dias", "nao_comecar_antes_de",
    "peso_informado", "observacao", "ordem",
})


def escrever_em_lote(cronograma: Cronograma, edicoes: list[dict]) -> dict:
    """Aplica muitas mudanças de uma vez, atomicamente.

    **Por que existe.** Colar 200 linhas de planilha e renumerar 400 códigos são
    dois gestos que o planejador faz sem pensar, e ambos viravam N requisições —
    cada uma com ida e volta pela rede, autenticação e RLS. Não é só lentidão: a
    metade de um `PATCH` a cada linha deixa o plano em estado intermediário
    visível para quem estiver olhando a mesma obra.

    **Duas passadas quando há código.** O código é único por cronograma, então
    renomear `1.2` para `1.1` com `1.1` ainda de pé bate na trava do banco. A
    primeira passada leva todo código que muda para um valor temporário; a
    segunda assenta o definitivo. Dentro de UMA transação — o estado temporário
    nunca é observável de fora.

    O teto é do dono (`PDCA_TETO_LINHAS_POR_LOTE`, §5.5e do `planos.py`).
    """
    if not cronograma.editavel:
        raise ValidationError(
            "Este cronograma não é mais rascunho. Para mudar o plano, replaneje."
        )
    if not edicoes:
        raise ValidationError("Nenhuma edição foi enviada.")
    if len(edicoes) > PDCA_TETO_LINHAS_POR_LOTE:
        raise ValidationError(
            f"São {len(edicoes)} linhas de uma vez e o limite por chamada é "
            f"{PDCA_TETO_LINHAS_POR_LOTE}. Divida em blocos."
        )

    alvos = {a.atividade_id: a for a in cronograma.atividades.all()}
    preparadas: list[tuple[Atividade, dict]] = []
    for item in edicoes:
        atividade = alvos.get(item.get("atividade"))
        if atividade is None:
            raise ValidationError(
                f"A atividade {item.get('atividade')} não é deste cronograma."
            )
        campos = {k: v for k, v in (item.get("campos") or {}).items() if k in CAMPOS_DO_LOTE}
        if not campos:
            raise ValidationError(
                f"A edição da atividade {atividade.codigo} não traz nenhum campo "
                "que a grade edite."
            )
        preparadas.append((atividade, campos))

    renomeando = [(a, c) for a, c in preparadas if "codigo" in c and c["codigo"] != a.codigo]

    with transaction.atomic():
        for atividade, _campos in renomeando:
            Atividade.objects.filter(pk=atividade.pk).update(
                codigo=f"~{atividade.pk}",
            )
        tocadas = 0
        for atividade, campos in preparadas:
            for chave, valor in campos.items():
                setattr(atividade, chave, valor)
            atividade.full_clean(exclude=["tenant", "cronograma", "pai"])
            atividade.save(update_fields=[*campos.keys(), "atualizado_em"])
            tocadas += 1

    return {
        "atividades": tocadas,
        "renomeadas": len(renomeando),
        "teto": PDCA_TETO_LINHAS_POR_LOTE,
    }


def renumerar_eap(cronograma: Cronograma, *, simular: bool = False) -> dict:
    """Reescreve a EAP inteira na ordem da árvore — `1`, `1.1`, `1.2`, `2`…

    **Por que é endpoint próprio, e não um lote.** O lote fatia em blocos, e
    fatiar aqui quebraria a única coisa que faz a renumeração funcionar: o código
    é único por cronograma, então renomear `1.2` para `1.1` com `1.1` ainda de pé
    bate na trava do banco. A saída é levar **todos** os que mudam para um nome
    temporário antes de assentar qualquer definitivo — e "todos" não cabe em
    blocos independentes: um código do segundo bloco colidiria com o primeiro.

    Por isso o limite aqui é o do **cronograma** (`PDCA_TETO_ATIVIDADES_POR_
    CRONOGRAMA`), e não o da chamada: a operação é sobre a árvore, e a árvore já
    tem teto declarado pelo dono.

    `simular=True` conta sem escrever — é o que a tela usa para perguntar
    "renumerar muda o código de 87 atividades, continuar?" antes de fazer.
    """
    if not simular and not cronograma.editavel:
        raise ValidationError(
            "Este cronograma não é mais rascunho. Para mudar o plano, replaneje."
        )

    atividades = list(cronograma.atividades.all())
    if len(atividades) > PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA:
        raise ValidationError(
            f"Este cronograma tem {len(atividades)} atividades e o teto é "
            f"{PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA}."
        )

    por_pai: dict[int | None, list[Atividade]] = {}
    for a in atividades:
        por_pai.setdefault(a.pai_id, []).append(a)
    for irmas in por_pai.values():
        irmas.sort(key=lambda x: (x.ordem, x.codigo, x.atividade_id))

    novos: list[tuple[Atividade, str]] = []

    def descer(pai_id, prefixo):
        for indice, filha in enumerate(por_pai.get(pai_id, []), start=1):
            codigo = f"{prefixo}{indice}"
            if filha.codigo != codigo:
                novos.append((filha, codigo))
            descer(filha.atividade_id, f"{codigo}.")

    descer(None, "")

    if simular or not novos:
        return {"mudancas": len(novos), "aplicadas": 0, "simulado": True}

    with transaction.atomic():
        for atividade, _codigo in novos:
            Atividade.objects.filter(pk=atividade.pk).update(codigo=f"~{atividade.pk}")
        for atividade, codigo in novos:
            Atividade.objects.filter(pk=atividade.pk).update(codigo=codigo)

    return {"mudancas": len(novos), "aplicadas": len(novos), "simulado": False}


# ---------------------------------------------------------------------------
# 7. O avanço apontado (PDCA.2) — de "quanto andou" até a curva S realizada
# ---------------------------------------------------------------------------
#
# A fatia anterior fechou a coluna **Plan**. Esta abre a **Do/Check**: o campo
# aponta quanto andou, o avanço sobe a árvore ponderado pelo peso, e a curva S
# ganha a segunda linha — a que o cliente confere contra a primeira.
#
# Três decisões governam tudo o que está aqui:
#
# 1. **O acumulado é derivado, nunca gravado.** A tabela guarda deltas; a soma é
#    feita na leitura. Guardar o acumulado em coluna obrigaria a reescrever a
#    linha anterior a cada apontamento — e o apontamento é append-only.
# 2. **O avanço atravessa versões pelo código da EAP**, no mesmo contrato de
#    `comparar_com_base`. Replanejar copia a árvore e gera ids novos: sem isto,
#    publicar a v2 de uma obra 40% executada mostraria a obra em zero.
# 3. **Sem peso não há ponderação, e a resposta diz isso.** Folha sem peso fica
#    fora da média e entra num denominador declarado. É a régua do
#    `cobertura_do_orcamento` aplicada ao avanço: número sem denominador mente.


def _cadeia_de_versoes(cronograma: Cronograma) -> list[int]:
    """Este cronograma e todos de que ele descende, do mais novo ao mais antigo.

    O apontamento fica preso à atividade em que foi feito, e a atividade é de uma
    versão. Ler só a versão corrente devolveria zero para toda obra que já
    replanejou — que são todas, depois do segundo mês.

    O laço tem fim garantido por dois motivos: `origem` aponta sempre para uma
    versão **anterior** (quem a preenche é o `replanejar`), e o teto de versões do
    `planos.py` é o fundo do poço caso alguém monte um ciclo na marra.
    """
    cadeia: list[int] = []
    vistos: set[int] = set()
    no: Cronograma | None = cronograma
    while (no is not None and no.pk not in vistos
           and len(cadeia) <= PDCA_TETO_VERSOES_POR_CRONOGRAMA):
        cadeia.append(no.pk)
        vistos.add(no.pk)
        no = no.origem
    return cadeia


def _apontado_por_codigo(cronograma: Cronograma) -> dict[str, dict]:
    """`{código da EAP: {"total", "lancamentos", "ultimo"}}`.

    Uma consulta agregada para o cronograma inteiro, e não uma por atividade: a
    tela do Gantt lê a árvore toda de uma vez, e um N+1 aqui seria uma consulta
    por linha numa grade de 800.
    """
    linhas = (ApontamentoAvanco.objects
              .filter(atividade__cronograma_id__in=_cadeia_de_versoes(cronograma))
              .values("atividade__codigo")
              .annotate(total=Sum("percentual"),
                        lancamentos=Count("apontamento_id"),
                        ultimo=Max("data")))
    return {
        linha["atividade__codigo"]: {
            "total": linha["total"] or Decimal("0"),
            "lancamentos": linha["lancamentos"],
            "ultimo": linha["ultimo"],
        }
        for linha in linhas
    }


def _entre_zero_e_cem(valor: Decimal) -> Decimal:
    """O acumulado que a leitura apresenta nunca sai de 0–100.

    O serviço de escrita já recusa o apontamento que estouraria a faixa; isto é a
    rede embaixo da rede, para uma carga feita por fora (comando de bancada,
    importação futura) não pintar uma barra de 130% no Gantt.
    """
    if valor < 0:
        return Decimal("0")
    if valor > 100:
        return Decimal("100")
    return valor


def avanco_do_cronograma(cronograma: Cronograma) -> dict:
    """O avanço de **cada** atividade e o da obra, numa passada só.

    A folha vale a soma dos seus apontamentos. A sintética vale a média dos
    filhos **ponderada pelo peso**, e o peso da sintética é a soma dos pesos dos
    filhos que têm peso — o que faz a conta da raiz ser idêntica à média
    ponderada de todas as folhas, qualquer que seja o formato da árvore.

    **Folha sem peso não entra na média.** Ela é contada em `folhas_sem_peso`, e
    a tela mostra o número ao lado do percentual: 78% apurado sobre 12 de 300
    folhas é bonito e mente. É a mesma régua do `cobertura_do_orcamento`.

    O avanço **financeiro** é a metade que vira dinheiro: roda só sobre as folhas
    vinculadas ao orçamento, em reais, e devolve `None` — não zero — quando
    nenhuma folha tem vínculo.
    """
    atividades = list(cronograma.atividades.select_related("item_orcado").all())
    apontado = _apontado_por_codigo(cronograma)

    filhos: dict[int, list[int]] = {}
    for a in atividades:
        if a.pai_id:
            filhos.setdefault(a.pai_id, []).append(a.atividade_id)

    peso: dict[int, Decimal | None] = {}
    origem_peso: dict[int, str] = {}
    avanco: dict[int, Decimal | None] = {}

    folhas = 0
    folhas_sem_peso = 0
    folhas_apontadas = 0
    orcado_total = Decimal("0")
    realizado_total = Decimal("0")
    folhas_orcadas = 0
    ultimo: date | None = None

    # De baixo para cima: a profundidade decrescente garante que todo filho já
    # foi resolvido quando o pai é visitado. É o mesmo caminhamento com que o CPM
    # faz a sintética ser o intervalo dos filhos, e evita recursão sobre uma
    # árvore cuja profundidade quem escolhe é o cliente.
    for a in sorted(atividades, key=lambda x: (x.profundidade, x.atividade_id), reverse=True):
        meus = filhos.get(a.atividade_id, [])
        if not meus:
            folhas += 1
            p, de_onde = peso_de(a)
            peso[a.atividade_id] = p
            origem_peso[a.atividade_id] = de_onde
            registro = apontado.get(a.codigo)
            if registro:
                folhas_apontadas += 1
                if registro["ultimo"] and (ultimo is None or registro["ultimo"] > ultimo):
                    ultimo = registro["ultimo"]
            bruto = registro["total"] if registro else Decimal("0")
            atual = _entre_zero_e_cem(bruto)
            avanco[a.atividade_id] = atual
            if p is None:
                folhas_sem_peso += 1
            elif de_onde == "orcado":
                folhas_orcadas += 1
                orcado_total += p
                realizado_total += p * atual / Decimal("100")
            continue

        soma_peso = Decimal("0")
        soma_ponderada = Decimal("0")
        tem = False
        for filho in meus:
            p = peso.get(filho)
            v = avanco.get(filho)
            if p is None or v is None:
                continue
            tem = True
            soma_peso += p
            soma_ponderada += p * v
        peso[a.atividade_id] = soma_peso if tem else None
        origem_peso[a.atividade_id] = "derivado" if tem else ""
        avanco[a.atividade_id] = (
            (soma_ponderada / soma_peso) if (tem and soma_peso > 0) else None
        )

    # O total da obra sai das **folhas**, e não da média das raízes: duas raízes
    # de tamanhos muito diferentes ponderadas igualmente diriam que metade da
    # casa de apoio vale metade da torre.
    peso_folhas = Decimal("0")
    ponderado_folhas = Decimal("0")
    for a in atividades:
        if filhos.get(a.atividade_id):
            continue
        p = peso.get(a.atividade_id)
        v = avanco.get(a.atividade_id)
        if p is None or v is None or p <= 0:
            continue
        peso_folhas += p
        ponderado_folhas += p * v

    fisico = (ponderado_folhas / peso_folhas) if peso_folhas > 0 else None

    return {
        "por_atividade": {
            a.atividade_id: {
                "avanco": (None if avanco.get(a.atividade_id) is None
                           else float(round(avanco[a.atividade_id], 2))),
                "peso": (None if peso.get(a.atividade_id) is None
                         else str(peso[a.atividade_id])),
                "peso_origem": origem_peso.get(a.atividade_id, ""),
                "lancamentos": apontado.get(a.codigo, {}).get("lancamentos", 0),
            }
            for a in atividades
        },
        "fisico": None if fisico is None else float(round(fisico, 2)),
        "financeiro": (
            None if folhas_orcadas == 0 else {
                "orcado": str(orcado_total.quantize(Decimal("0.01"))),
                "realizado": str(realizado_total.quantize(Decimal("0.01"))),
                "percentual": (
                    float(round(realizado_total / orcado_total * 100, 2))
                    if orcado_total > 0 else None
                ),
                "folhas": folhas_orcadas,
            }
        ),
        "folhas": folhas,
        "folhas_sem_peso": folhas_sem_peso,
        "folhas_apontadas": folhas_apontadas,
        "ultimo_apontamento": ultimo,
    }


def avanco_da_atividade(atividade: Atividade) -> Decimal:
    """O acumulado de **uma** folha, para o caminho de escrita conferir o teto.

    Soma pelo código na cadeia de versões, igual à leitura da árvore — as duas
    contas têm de ser a mesma, senão a API recusaria um apontamento que a tela
    mostra como cabível (ou o contrário).
    """
    total = (ApontamentoAvanco.objects
             .filter(atividade__cronograma_id__in=_cadeia_de_versoes(atividade.cronograma),
                     atividade__codigo=atividade.codigo)
             .aggregate(total=Sum("percentual"))["total"])
    return total or Decimal("0")


def validar_apontamento(atividade: Atividade, percentual: Decimal) -> Decimal:
    """As quatro recusas do avanço — e o acumulado que o lançamento produz.

    1. **Sintética não recebe apontamento.** O avanço dela é dos filhos; aceitar
       um número aqui criaria duas verdades sobre a mesma parte da obra.
    2. **Só a versão vigente recebe avanço.** Rascunho é plano que ninguém
       assumiu, substituído é história. Apontar no rascunho prenderia a execução
       a um plano que talvez nunca seja publicado.
    3. **Marco não tem percentual intermediário.** Ou aconteceu (100) ou não
       (-100 desfaz): concretagem liberada não fica em 40%.
    4. **O acumulado fica entre 0 e 100.** O estorno é o caminho do erro, e ele
       também não leva a atividade a avanço negativo.
    """
    if atividade.filhos.exists():
        raise ValidationError(
            f"'{atividade.codigo} {atividade.nome}' é sintética: o avanço dela é a "
            "média ponderada das filhas. Aponte na atividade que executa."
        )
    if atividade.cronograma.status != Cronograma.Status.VIGENTE:
        raise ValidationError(
            "Só o cronograma vigente recebe apontamento de avanço — este está "
            f"{atividade.cronograma.get_status_display().lower()}. "
            "Publique o plano antes de apontar a execução."
        )
    if atividade.eh_marco and percentual not in (Decimal("100"), Decimal("-100")):
        raise ValidationError(
            f"'{atividade.codigo}' é um marco: ele acontece ou não acontece. "
            "Aponte 100% para cumpri-lo, ou -100% para desfazer."
        )

    antes = avanco_da_atividade(atividade)
    acumulado = antes + percentual
    if acumulado > 100:
        raise ValidationError(
            f"'{atividade.codigo}' já está em {antes:.2f}% — este apontamento "
            f"levaria a {acumulado:.2f}%, e o avanço não passa de 100%."
        )
    if acumulado < 0:
        raise ValidationError(
            f"Este estorno levaria '{atividade.codigo}' a {acumulado:.2f}%. O "
            "avanço não fica negativo: estorne no máximo o que foi apontado."
        )
    return acumulado


@transaction.atomic
def registrar_apontamento(*, atividade: Atividade, percentual: Decimal, data,
                          local=None, origem: str = "web", observacao: str = "",
                          foto=None, por: str = "", estorna=None,
                          sincronizar: bool = True) -> "ApontamentoAvanco":
    """Grava um apontamento depois de passar pelas recusas — e **trava a linha**.

    O `select_for_update` na atividade não é zelo excessivo: dois apontamentos
    simultâneos da mesma frente (o engenheiro na grade e o mestre pelo celular)
    leriam o mesmo acumulado, e os dois passariam na conferência dos 100%. A
    trava põe um atrás do outro, e o segundo leva a recusa que merece.

    `sincronizar=False` é para o **lote**, que espelha o percentual das etapas
    uma vez no fim em vez de uma vez por linha — a diferença entre uma varredura
    da árvore e duzentas.
    """
    travada = Atividade.objects.select_for_update().filter(pk=atividade.pk).first()
    if travada is None:
        raise ValidationError("Esta atividade não existe mais.")
    validar_apontamento(travada, percentual)
    apontamento = ApontamentoAvanco.objects.create(
        tenant_id=travada.tenant_id,
        atividade=travada,
        local=local,
        data=data,
        percentual=percentual,
        origem=origem,
        observacao=observacao,
        foto=foto,
        estorna=estorna,
        apontado_por=(por or "")[:150],
    )
    if sincronizar:
        sincronizar_percentual_das_etapas(travada.cronograma)
    return apontamento


def estornar(apontamento: "ApontamentoAvanco", *, motivo: str, por: str = "",
             data=None) -> "ApontamentoAvanco":
    """A correção de um apontamento errado é **outro apontamento**, de sinal
    contrário, apontando para ele.

    O motivo é obrigatório pela mesma razão que o do replanejamento: sem ele, o
    livro fica com duas linhas que se anulam e nenhuma explicação — e é
    exatamente isso que quem auditar a medição daqui a dois anos vai encontrar.

    Estornar um estorno é recusado. Cadeia de correção de correção é o caminho
    mais curto para ninguém mais saber o que aconteceu; quem errou o estorno
    aponta o avanço de novo, que é o gesto honesto.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError(
            "Estornar exige o motivo — é ele que separa a correção do erro no "
            "livro que vai virar medição."
        )
    if apontamento.estorna_id:
        raise ValidationError(
            "Este apontamento já é um estorno. Para corrigir, aponte o avanço de "
            "novo em vez de encadear correções."
        )
    if apontamento.estornos.exists():
        raise ValidationError("Este apontamento já foi estornado.")
    return registrar_apontamento(
        atividade=apontamento.atividade,
        percentual=-apontamento.percentual,
        data=data or apontamento.data,
        local=apontamento.local,
        origem=apontamento.origem,
        observacao=motivo,
        por=por,
        estorna=apontamento,
    )


def apontar_em_lote(cronograma: Cronograma, linhas: list[dict], *,
                    por: str = "", origem: str = "web") -> dict:
    """A **grade da semana**: N frentes apontadas numa transação só.

    É o gesto que o engenheiro de obra faz na segunda-feira de manhã — abre as
    frentes ativas, digita o percentual de cada uma e manda. Uma requisição por
    linha seriam 40 idas de rede e, pior, um avanço parcial gravado se a décima
    falhasse: metade da semana no sistema e metade no caderno.

    **Ou entra tudo, ou não entra nada** — e a recusa cita a linha e o código da
    atividade, não "erro ao salvar". O teto por chamada é do dono (`planos.py`
    §5.5f); acima dele o cliente fatia em blocos e vê o progresso.
    """
    if len(linhas) > PDCA_TETO_APONTAMENTOS_POR_LOTE:
        raise ValidationError(
            f"São {len(linhas)} apontamentos numa chamada e o limite é "
            f"{PDCA_TETO_APONTAMENTOS_POR_LOTE}. Divida em blocos."
        )
    if not linhas:
        raise ValidationError("Nenhum apontamento foi enviado.")

    do_plano = {a.atividade_id: a for a in cronograma.atividades.all()}
    criados = 0
    with transaction.atomic():
        for n, linha in enumerate(linhas, start=1):
            atividade = do_plano.get(linha["atividade"])
            if atividade is None:
                raise ValidationError(
                    f"Linha {n}: a atividade {linha['atividade']} não é deste cronograma."
                )
            try:
                registrar_apontamento(
                    atividade=atividade,
                    percentual=linha["percentual"],
                    data=linha["data"],
                    local=linha.get("local"),
                    origem=linha.get("origem") or origem,
                    observacao=linha.get("observacao", ""),
                    por=por,
                    sincronizar=False,
                )
            except ValidationError as erro:
                raise ValidationError(
                    f"Linha {n} ({atividade.codigo} {atividade.nome}): "
                    + " ".join(erro.messages)
                )
            criados += 1
        etapas = sincronizar_percentual_das_etapas(cronograma)
    return {
        "apontamentos": criados,
        "etapas_sincronizadas": etapas,
        "teto": PDCA_TETO_APONTAMENTOS_POR_LOTE,
    }


# ---------------------------------------------------------------------------
# 8. A curva S — prevista × realizada, física × financeira
# ---------------------------------------------------------------------------
#
# A PDCA.1 desenhava a curva prevista **no cliente**, distribuindo o peso
# linearmente nos dias corridos da barra, e declarava a aproximação na planta.
# Ela vem para cá agora, por dois motivos que só a PDCA.2 criou:
#
# - a realizada precisa cruzar apontamento com peso, e o peso vem do orçamento —
#   duas tabelas que o navegador não tem;
# - com as duas curvas na mesma tela, uma calculada por dias corridos e outra por
#   data de apontamento, o desvio entre elas carregaria o erro de fim de semana
#   da aproximação. Aqui o previsto é distribuído nos **dias úteis do calendário
#   de cada atividade**, que é a régua com que o CPM produziu as datas.

_GRANULARIDADES = ("dia", "semana", "mes")


def _balde(dia: date, granularidade: str) -> date:
    if granularidade == "dia":
        return dia
    if granularidade == "semana":
        return dia - timedelta(days=dia.weekday())  # a segunda-feira da semana
    return dia.replace(day=1)


def _proximo_balde(dia: date, granularidade: str) -> date:
    if granularidade == "dia":
        return dia + timedelta(days=1)
    if granularidade == "semana":
        return dia + timedelta(days=7)
    return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)


def _quantos_baldes(inicio: date, fim: date, granularidade: str) -> int:
    if granularidade == "dia":
        return (fim - inicio).days + 1
    if granularidade == "semana":
        return (fim - inicio).days // 7 + 1
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1


def _rotulo_do_balde(dia: date, granularidade: str) -> str:
    if granularidade == "mes":
        return f"{dia.month:02d}/{dia.year}"
    return f"{dia.day:02d}/{dia.month:02d}"


def _percentual(parte: Decimal, base: Decimal) -> float:
    return float(round(parte / base * 100, 2)) if base > 0 else 0.0


def curva_s(cronograma: Cronograma, *, granularidade: str = "semana") -> dict:
    """As duas curvas, nas duas moedas, cada uma com o seu denominador.

    **Física** é o peso — venha ele do orçamento ou do campo `peso_informado` —,
    normalizado em percentual. **Financeira** é só o que tem vínculo com o
    orçamento, em reais. Separá-las é o que impede o erro mais comum: uma obra
    com 40% das folhas sem vínculo teria uma curva financeira "completa" que
    ignora 40% do serviço, e ninguém veria isso num gráfico de uma linha só.

    A **realizada para onde a obra parou de apontar** — a série devolve `null`
    dali em diante, em vez de seguir reta até o fim do plano. Linha reta num
    gráfico é lida como "em dia", e o que aconteceu foi o contrário: ninguém
    apontou.
    """
    if granularidade not in _GRANULARIDADES:
        raise ValidationError(
            f"Granularidade '{granularidade}' não existe — use dia, semana ou mes."
        )

    atividades = list(cronograma.atividades
                      .select_related("item_orcado", "calendario").all())
    com_filhos = {a.pai_id for a in atividades if a.pai_id}
    folhas = [a for a in atividades if a.atividade_id not in com_filhos]

    calendarios = _calendarios_do_cronograma(cronograma, atividades)

    peso_de_folha: dict[int, Decimal] = {}
    valor_de_folha: dict[int, Decimal] = {}
    sem_peso = 0
    sem_data = 0

    # -- previsto: o peso espalhado nos dias ÚTEIS de cada atividade ----------
    previsto_fisico: dict[date, Decimal] = {}
    previsto_financeiro: dict[date, Decimal] = {}

    for a in folhas:
        p, de_onde = peso_de(a)
        if p is None or p <= 0:
            sem_peso += 1
            continue
        peso_de_folha[a.atividade_id] = p
        if de_onde == "orcado":
            valor_de_folha[a.atividade_id] = p
        if not a.inicio_cedo or not a.termino_cedo:
            sem_data += 1
            continue

        calendario = calendarios.get(a.calendario_id or cronograma.calendario_id)
        dias: list[date] = []
        if calendario is not None:
            comeco = calendario.indice_adiante(a.inicio_cedo)
            fim = calendario.indice_atras(a.termino_cedo)
            dias = [calendario.data(i) for i in range(comeco, max(fim, comeco) + 1)]
        if not dias:
            # Marco (duração zero) e cronograma sem calendário caem aqui: o peso
            # inteiro no dia do término, que é quando o compromisso vence.
            dias = [a.termino_cedo]

        fatia = p / Decimal(len(dias))
        financeira = a.atividade_id in valor_de_folha
        for dia in dias:
            chave = _balde(dia, granularidade)
            previsto_fisico[chave] = previsto_fisico.get(chave, Decimal("0")) + fatia
            if financeira:
                previsto_financeiro[chave] = (
                    previsto_financeiro.get(chave, Decimal("0")) + fatia
                )

    # -- realizado: cada apontamento no dia em que o serviço andou -----------
    realizado_fisico: dict[date, Decimal] = {}
    realizado_financeiro: dict[date, Decimal] = {}
    por_codigo = {a.codigo: a.atividade_id for a in folhas}
    ultimo_apontamento: date | None = None

    lancamentos = (ApontamentoAvanco.objects
                   .filter(atividade__cronograma_id__in=_cadeia_de_versoes(cronograma))
                   .values("atividade__codigo", "data")
                   .annotate(total=Sum("percentual"))
                   .order_by("data"))
    for lancamento in lancamentos:
        folha = por_codigo.get(lancamento["atividade__codigo"])
        peso = peso_de_folha.get(folha) if folha is not None else None
        if peso is None:
            continue
        quanto = peso * (lancamento["total"] or Decimal("0")) / Decimal("100")
        dia = lancamento["data"]
        if ultimo_apontamento is None or dia > ultimo_apontamento:
            ultimo_apontamento = dia
        chave = _balde(dia, granularidade)
        realizado_fisico[chave] = realizado_fisico.get(chave, Decimal("0")) + quanto
        if folha in valor_de_folha:
            realizado_financeiro[chave] = (
                realizado_financeiro.get(chave, Decimal("0")) + quanto
            )

    baldes = sorted(set(previsto_fisico) | set(realizado_fisico))
    if not baldes:
        return {
            "granularidade": granularidade,
            "granularidade_pedida": granularidade,
            "pontos": [],
            "base_fisica": "0",
            "base_financeira": None,
            "folhas": len(folhas),
            "folhas_sem_peso": sem_peso,
            "folhas_sem_data": sem_data,
            "ultimo_apontamento": None,
            "motivo_vazio": (
                "Nenhuma folha tem peso — sem vínculo com o orçamento nem peso "
                "informado, não há o que acumular."
                if folhas and sem_peso == len(folhas) else
                "O plano ainda não foi calculado: rode o CPM para as atividades "
                "ganharem data."
            ),
        }

    # O teto de pontos é do dono (`planos.py` §5.5f). Passar dele **engrossa a
    # granularidade e declara qual valeu** — engrossar calado faria a tela dizer
    # "por dia" desenhando meses.
    grossa = granularidade
    for candidata in _GRANULARIDADES[_GRANULARIDADES.index(granularidade):]:
        grossa = candidata
        if _quantos_baldes(baldes[0], baldes[-1], candidata) <= PDCA_TETO_PONTOS_CURVA_S:
            break
    if grossa != granularidade:
        saida = curva_s(cronograma, granularidade=grossa)
        saida["granularidade_pedida"] = granularidade
        return saida

    base_fisica = sum(peso_de_folha.values(), Decimal("0"))
    base_financeira = sum(valor_de_folha.values(), Decimal("0"))
    corte = None if ultimo_apontamento is None else _balde(ultimo_apontamento, granularidade)

    pontos = []
    acumulado_previsto = Decimal("0")
    acumulado_realizado = Decimal("0")
    acumulado_previsto_reais = Decimal("0")
    acumulado_realizado_reais = Decimal("0")
    cursor = baldes[0]
    while cursor <= baldes[-1]:
        no_periodo_previsto = previsto_fisico.get(cursor, Decimal("0"))
        no_periodo_realizado = realizado_fisico.get(cursor, Decimal("0"))
        acumulado_previsto += no_periodo_previsto
        acumulado_realizado += no_periodo_realizado
        acumulado_previsto_reais += previsto_financeiro.get(cursor, Decimal("0"))
        acumulado_realizado_reais += realizado_financeiro.get(cursor, Decimal("0"))
        mostra_realizado = corte is not None and cursor <= corte

        pontos.append({
            "iso": cursor.isoformat(),
            "rotulo": _rotulo_do_balde(cursor, granularidade),
            "previsto": _percentual(acumulado_previsto, base_fisica),
            "realizado": (_percentual(acumulado_realizado, base_fisica)
                          if mostra_realizado else None),
            "previsto_periodo": _percentual(no_periodo_previsto, base_fisica),
            "realizado_periodo": (_percentual(no_periodo_realizado, base_fisica)
                                  if mostra_realizado else None),
            "previsto_reais": (str(acumulado_previsto_reais.quantize(Decimal("0.01")))
                               if base_financeira > 0 else None),
            "realizado_reais": (str(acumulado_realizado_reais.quantize(Decimal("0.01")))
                                if (base_financeira > 0 and mostra_realizado) else None),
        })
        cursor = _proximo_balde(cursor, granularidade)

    return {
        "granularidade": granularidade,
        "granularidade_pedida": granularidade,
        "pontos": pontos,
        "base_fisica": str(base_fisica),
        "base_financeira": str(base_financeira) if base_financeira > 0 else None,
        "folhas": len(folhas),
        "folhas_sem_peso": sem_peso,
        "folhas_sem_data": sem_data,
        "ultimo_apontamento": ultimo_apontamento,
        "motivo_vazio": "",
    }


# ---------------------------------------------------------------------------
# 9. A tomada do percentual da etapa (planta §11.2)
# ---------------------------------------------------------------------------
#
# `EtapaObra.percentual_conclusao` é digitado à mão desde sempre e pondera quatro
# leituras da casa (resumo da obra, serializer, portal do cliente, curva S do
# Orçamento). Havendo atividades do PDCA vinculadas à etapa, ele passa a ser
# **apurado** — e a edição manual continua possível, atrás de
# `obras.etapa.percentual_manual`.
#
# A função mora aqui, e não no app `obras`, por uma razão de dependência: `obras`
# é fundação sem entitlement e o `pdca` é módulo vendido. Fundação não importa
# módulo pago; o módulo pago **oferece** a leitura, e quem chama trata a ausência.


def avanco_da_etapa(etapa) -> dict | None:
    """O avanço apurado de uma `EtapaObra` pelo cronograma **vigente** da obra.

    `None` quando não há o que apurar — sem cronograma vigente, sem atividade
    vinculada à etapa, ou sem peso em nenhuma delas. `None` é a resposta que
    devolve a etapa ao percentual digitado; zero diria "a obra não andou", que é
    uma afirmação diferente.
    """
    vigente = (Cronograma.objects
               .filter(tenant_id=etapa.tenant_id, obra_id=etapa.obra_id,
                       status=Cronograma.Status.VIGENTE)
               .select_related("origem").first())
    if vigente is None:
        return None

    pais = dict(vigente.atividades.values_list("atividade_id", "pai_id"))
    vinculadas = set(
        vigente.atividades.filter(etapa_id=etapa.pk).values_list("atividade_id", flat=True)
    )
    if not vinculadas:
        return None

    # Só as **mais altas** de cada ramo entram na conta. Uma etapa ligada ao pai
    # e também a uma filha contaria a filha duas vezes — uma dentro do peso do
    # pai e outra por fora.
    topo = [aid for aid in vinculadas if not _tem_ancestral_em(aid, vinculadas, pais)]

    media = _media_ponderada(avanco_do_cronograma(vigente)["por_atividade"], topo)
    if media is None:
        return None

    return {
        "percentual": float(round(media, 2)),
        "cronograma": vigente.pk,
        "versao": vigente.versao,
        "atividades": len(topo),
    }


def _tem_ancestral_em(atividade_id: int, conjunto: set[int],
                      pais: dict[int, int | None]) -> bool:
    """A atividade descende de outra que também está vinculada à mesma etapa?"""
    no = pais.get(atividade_id)
    passos = 0
    while no is not None and passos <= PDCA_PROFUNDIDADE_MAXIMA_WBS:
        if no in conjunto:
            return True
        no = pais.get(no)
        passos += 1
    return False


def etapas_com_apuracao(*, obra_id: int, tenant_id: int) -> frozenset[int]:
    """Quais `EtapaObra` desta obra têm avanço **apurado** pelo cronograma.

    É a pergunta barata — existe atividade vinculada? —, e é só ela que o
    serializer do `obras` precisa para dizer de onde veio o número. Recalcular o
    percentual de cada etapa numa listagem seria uma varredura da árvore por
    linha da tabela.
    """
    vigente = (Cronograma.objects
               .filter(tenant_id=tenant_id, obra_id=obra_id,
                       status=Cronograma.Status.VIGENTE)
               .only("cronograma_id").first())
    if vigente is None:
        return frozenset()
    return frozenset(
        vigente.atividades.exclude(etapa=None).values_list("etapa_id", flat=True)
    )


def _media_ponderada(por_atividade: dict, ids) -> Decimal | None:
    soma_peso = Decimal("0")
    soma_ponderada = Decimal("0")
    for aid in ids:
        dados = por_atividade.get(aid) or {}
        if dados.get("peso") is None or dados.get("avanco") is None:
            continue
        p = Decimal(dados["peso"])
        soma_peso += p
        soma_ponderada += p * Decimal(str(dados["avanco"]))
    if soma_peso <= 0:
        return None
    return soma_ponderada / soma_peso


def sincronizar_percentual_das_etapas(cronograma: Cronograma) -> int:
    """Espelha o avanço apurado em `EtapaObra.percentual_conclusao`.

    **Por que escrever na coluna em vez de calcular na leitura** (planta §11.2):
    aquele percentual pondera quatro leituras que já existem e que não conhecem o
    PDCA — o resumo da obra, o `progresso_ponderado` do serializer, o portal do
    cliente e a curva S do Orçamento. Calcular só na tela do PDCA deixaria as
    quatro mostrando o número digitado meses atrás; escrever aqui faz o
    apontamento do campo chegar a todas elas sem que nenhuma precise saber que
    este módulo existe.

    Roda **depois do apontamento**, e não a cada leitura: é escrita derivada de
    um gesto, no molde do `calculado_em` do CPM. Uma passada pela árvore por
    lote, não por linha.
    """
    if cronograma.status != Cronograma.Status.VIGENTE:
        return 0

    vinculadas: dict[int, set[int]] = {}
    pais: dict[int, int | None] = {}
    for aid, pai_id, etapa_id in cronograma.atividades.values_list(
        "atividade_id", "pai_id", "etapa_id"
    ):
        pais[aid] = pai_id
        if etapa_id:
            vinculadas.setdefault(etapa_id, set()).add(aid)
    if not vinculadas:
        return 0

    por_atividade = avanco_do_cronograma(cronograma)["por_atividade"]
    from obras.models import EtapaObra

    mudadas = []
    for etapa_id, ids in vinculadas.items():
        topo = [aid for aid in ids if not _tem_ancestral_em(aid, ids, pais)]
        media = _media_ponderada(por_atividade, topo)
        if media is None:
            continue
        mudadas.append(EtapaObra(
            pk=etapa_id, percentual_conclusao=round(media, 2),
        ))
    if not mudadas:
        return 0
    # `bulk_update` e não um `save()` por etapa: são no máximo dezenas de linhas,
    # e cada `save()` dispararia os sinais do `obras` para uma escrita que é
    # derivada — o gesto do usuário foi apontar avanço, não editar a etapa.
    EtapaObra.objects.bulk_update(mudadas, ["percentual_conclusao"])
    return len(mudadas)
