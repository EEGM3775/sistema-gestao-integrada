# backend/modulopdca/services.py
"""As regras de negócio do PDCA — as que não passam por HTTP.

**PDCA.0** povoou a árvore de locais e ensinou a contar dia útil. **PDCA.1** usa
as duas: o CPM (§3 deste arquivo) roda sobre o grafo de precedências convertendo
duração em datas pelo calendário, e o versionamento (§4) transforma cada
replanejamento numa linha de base legível. **PDCA.2** fecha o ciclo: o avanço
apontado sobe a árvore ponderado pelo peso (§7), a curva S ganha a linha
realizada (§8) e o percentual da etapa passa a ser apurado (§9). **PDCA.3**
transforma esse avanço em dinheiro: a medição nasce proposta dele (§10), sobe a
escada de atesto do `nucleo` e, aprovada, congela e gera o título no ERP.

O CPM roda **no servidor** por decisão de desenho (planta §5.5): é fonte de
verdade para prazo e dinheiro, e recalculá-lo no navegador daria um resultado
por máquina.
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

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
    PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO,
    PDCA_TETO_DEDUCOES_POR_MEDICAO,
    PDCA_TETO_ITENS_POR_ADITIVO,
    PDCA_TETO_ITENS_POR_CONTRATO,
    PDCA_TETO_LINHAS_POR_LOTE,
    PDCA_TETO_LINHAS_POR_MEDICAO,
    PDCA_TETO_LOCAIS_POR_GERACAO,
    PDCA_TETO_LOCAIS_POR_OBRA,
    PDCA_TETO_VERSOES_POR_CRONOGRAMA,
)

from .models import (
    AcaoAditivo, AditivoContrato, ApontamentoAvanco, Atividade,
    CalendarioTrabalho, ContratoObra, Cronograma, DeducaoMedicao,
    ExcecaoCalendario, ItemAditivo, ItemContrato, ItemMedicao,
    LiberacaoRetencao, LocalObra, Medicao, NivelLocal, OrigemCusto,
    Precedencia, RegimeContrato, TipoDeducao,
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


# ---------------------------------------------------------------------------
# 10. Contrato, aditivo e medição (PDCA.3 + PDCA.4) — do avanço ao título
# ---------------------------------------------------------------------------
#
# É a parte do módulo que faz dinheiro sair, e a ordem das travas importa mais
# do que cada trava isolada:
#
#   propor → conferir → submeter → atestar (escada) → congelar → título
#
# **Nada disto grava agregado.** Não há coluna de "total medido", "saldo",
# "contratado atual" nem "acumulado": toda soma é feita na leitura, sobre as
# linhas de `ItemMedicao` e `ItemAditivo` (§4.9 da planta). O que se congela é o
# *insumo* — quantidade e preço do dia —, não o resultado.
#
# **Três somas diferentes de "já medido", e confundi-las é o erro caro:**
#
#   - o **acumulado que trava** conta as medições `APROVADA` **e**
#     `EM_APROVACAO`. Contar só as aprovadas deixaria duas medições subirem a
#     escada em paralelo, cada uma passando na validação sozinha e as duas
#     juntas estourando o contratado — e o estouro só apareceria depois de os
#     dois títulos existirem;
#   - o **retido disponível** conta só as `APROVADA`, porque retenção que ainda
#     não foi descontada de nada não é dinheiro retido;
#   - o **medido para a tela** mostra as três faixas separadas, sem somar.
#
# **E uma quarta soma, que a PDCA.4 trouxe:** o *contratado atual* é o original
# do dia da assinatura mais os deltas dos aditivos **aprovados**. Aditivo em
# rascunho ou na escada não move saldo nenhum — é intenção, como o rascunho de
# medição. Toda trava desta seção confere contra o **atual**; nenhuma confere
# contra o campo do `ItemContrato` diretamente.
#
# **A régua da grade é a G703** (o padrão de boletim que o mercado usa há
# décadas): contratado original → aditivos → contratado atual → acumulado
# anterior → este período → material estocado → acumulado → % → saldo. Cada
# coluna sai de uma função daqui, e **nenhuma** é calculada no navegador: o
# primeiro desenho desta tela somava saldo no React e mostrava número diferente
# conforme o caminho pelo qual o gestor tivesse chegado nela.

_CENTAVO = Decimal("0.01")
_ZERO = Decimal("0")
#: A precisão de `ItemContrato.quantidade_contratada` e `ItemMedicao.quantidade`.
_QUANTIDADE = Decimal("0.0001")

#: As medições que ocupam saldo do contrato. Ver a nota do cabeçalho.
_EM_VOO = (Medicao.Status.APROVADA, Medicao.Status.EM_APROVACAO)

#: Os status de medição que **existem** para efeito de período e de estoque de
#: material — o rascunho entra aqui e não entra em `_EM_VOO`, porque ele ainda
#: não ocupa dinheiro mas já ocupa a janela de tempo que o gestor está medindo.
_VIVAS = (
    Medicao.Status.RASCUNHO, Medicao.Status.EM_APROVACAO, Medicao.Status.APROVADA,
)


def _dinheiro(valor: Decimal) -> Decimal:
    """Arredonda para centavo **no fim da conta**, nunca nas parcelas.

    `quantidade` e `preco_unitario` têm quatro casas de propósito (ver o model):
    arredondar o unitário antes de multiplicar por 1.200 m³ erra em dezenas de
    reais. O centavo aparece aqui, uma vez, na fronteira com o ERP.
    """
    return Decimal(valor).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def _quantidade(valor: Decimal) -> Decimal:
    """Arredonda para a precisão **da coluna** que vai guardar o número.

    Sem isto a proposta sairia com a precisão que a divisão produziu (8 casas ou
    mais) e o banco a truncaria para 4 na gravação. O estrago não é estético:
    `criar_medicao` compara `quantidade == quantidade_proposta` para decidir se a
    linha é `AVANCO` ou `MANUAL`, e a tela devolve o número **já arredondado** —
    então toda linha aceita sem alteração voltaria marcada como "digitada pelo
    gestor", apagando exatamente o rastro que a fatia existe para manter.
    """
    return Decimal(valor).quantize(_QUANTIDADE, rounding=ROUND_HALF_UP)


# --- O contratado: original, aditivado, atual -------------------------------


def aditivo_por_item(contrato: ContratoObra) -> dict[int, Decimal]:
    """`{item_contrato_id: Σ deltas de aditivos APROVADOS}`.

    Só os aprovados, e é a mesma régua do rascunho de medição: um aditivo que
    ainda sobe a escada não pode aumentar o saldo contra o qual alguém mede,
    senão o gestor mediria contra uma autorização que a diretoria ainda pode
    negar — e o estouro só apareceria quando ela negasse.
    """
    linhas = (
        ItemAditivo.objects
        .filter(
            aditivo__contrato=contrato,
            aditivo__status=AditivoContrato.Status.APROVADO,
            item_contrato__isnull=False,
        )
        .values("item_contrato_id")
        .annotate(total=Sum("quantidade_delta"))
    )
    return {linha["item_contrato_id"]: linha["total"] or _ZERO for linha in linhas}


def contratado_atual_por_item(contrato: ContratoObra,
                              itens: list[ItemContrato] | None = None,
                              ) -> dict[int, Decimal]:
    """`{item_contrato_id: quantidade que vale hoje}` = original + Σ deltas.

    É **a** régua desta seção. Nenhuma trava confere contra
    `item.quantidade_contratada` diretamente: esse campo é o do dia da
    assinatura, e num contrato aditado ele deixou de ser o limite há meses.
    """
    aditado = aditivo_por_item(contrato)
    itens = contrato.itens.all() if itens is None else itens
    return {
        item.pk: item.quantidade_contratada + aditado.get(item.pk, _ZERO)
        for item in itens
    }


def valor_contratado(contrato: ContratoObra) -> Decimal:
    """O que o contrato vale **hoje**.

    No **unitário** é a soma dos itens pela quantidade *atual* — e não um total
    guardado ao lado dela, que seria a segunda verdade do §4.9. No **global** e
    na **administração** é o valor fechado mais o que os aditivos acrescentaram,
    porque ali o valor fechado *é* o dado primário (a constraint do model cobra a
    presença dele justamente por isto).
    """
    if contrato.regime == RegimeContrato.UNITARIO:
        atual = contratado_atual_por_item(contrato)
        total = _ZERO
        for item in contrato.itens.all():
            total += atual.get(item.pk, item.quantidade_contratada) * item.preco_unitario
        return _dinheiro(total)
    return _dinheiro((contrato.valor_global or _ZERO) + valor_dos_aditivos(contrato))


def valor_contratado_original(contrato: ContratoObra) -> Decimal:
    """O do dia da assinatura — o denominador do limite do regime público.

    Sem ele, o segundo aditivo de 20% seria conferido contra um contrato que o
    primeiro já engordou, e 20% + 20% passariam como se fossem 40% do original
    quando são 44%. É exatamente o erro que a Lei 14.133 existe para impedir.
    """
    if contrato.regime == RegimeContrato.UNITARIO:
        total = _ZERO
        for item in contrato.itens.all():
            if item.aditivo_origem_id is not None:
                continue
            total += item.quantidade_contratada * item.preco_unitario
        return _dinheiro(total)
    return _dinheiro(contrato.valor_global or _ZERO)


def valor_dos_aditivos(contrato: ContratoObra) -> Decimal:
    """Quanto os aditivos aprovados somaram (ou tiraram) em dinheiro."""
    total = _ZERO
    for aditivo in contrato.aditivos.filter(
        status=AditivoContrato.Status.APROVADO,
    ).prefetch_related("itens", "itens__item_contrato"):
        total += resumo_do_aditivo(aditivo)["liquido"]
    return _dinheiro(total)


# --- O medido, e o material que está na obra sem estar aplicado -------------


def medido_por_item(contrato: ContratoObra, *,
                    excluir_medicao_id: int | None = None) -> dict[int, Decimal]:
    """`{item_contrato_id: quantidade acumulada}` nas medições que ocupam saldo.

    `excluir_medicao_id` tira a própria medição da conta quando se está
    validando uma que já existe — sem isso, revalidar uma medição em aprovação
    a contaria duas vezes e ela reprovaria contra si mesma.
    """
    linhas = (
        ItemMedicao.objects
        .filter(medicao__contrato=contrato, medicao__status__in=_EM_VOO)
        .exclude(medicao_id=excluir_medicao_id)
        .values("item_contrato_id")
        .annotate(total=Sum("quantidade"))
    )
    return {linha["item_contrato_id"]: linha["total"] or _ZERO for linha in linhas}


def estocado_ate(contrato: ContratoObra, *, antes_de: int | None = None,
                 excluir_medicao_id: int | None = None) -> dict[int, Decimal]:
    """`{item_contrato_id: saldo de material estocado}` **declarado por último**.

    Material estocado não é delta (ver o campo no model): cada medição declara o
    estoque que existe *naquele momento*, e o que se paga de material numa
    medição é a diferença contra o que a anterior declarava. Esta função é o "o
    que a anterior declarava".

    `antes_de` é o **número** da medição que está sendo calculada: só contam as
    que vieram antes dela. Sem isso, calcular uma medição antiga leria o estoque
    de uma posterior e pagaria material para trás.
    """
    consulta = (
        ItemMedicao.objects
        .filter(medicao__contrato=contrato, medicao__status__in=_EM_VOO)
        .exclude(medicao_id=excluir_medicao_id)
    )
    if antes_de is not None:
        consulta = consulta.filter(medicao__numero__lt=antes_de)

    saldo: dict[int, Decimal] = {}
    ultimo: dict[int, int] = {}
    for item_id, numero, estocada in consulta.values_list(
        "item_contrato_id", "medicao__numero", "quantidade_estocada",
    ):
        if numero >= ultimo.get(item_id, -1):
            ultimo[item_id] = numero
            saldo[item_id] = estocada or _ZERO
    return saldo


def _cronograma_vigente(contrato: ContratoObra) -> Cronograma | None:
    if contrato.obra_id is None:
        return None
    return Cronograma.objects.filter(
        obra_id=contrato.obra_id, status=Cronograma.Status.VIGENTE,
    ).first()


def _atividades_do_item(item: ItemContrato,
                        cronograma: Cronograma | None) -> list[Atividade]:
    """As atividades cujo avanço alimenta esta linha de contrato.

    A ordem de busca é do mais específico para o mais geral, e é o desenho do
    model: o vínculo **direto** (`atividade`) ganha do vínculo **pelo orçamento**
    (`item_orcado`), porque quem o preencheu disse exatamente qual frente paga
    esta linha. Sem nenhum dos dois a lista é vazia — e vazia não é zero: quem
    chama declara "sem vínculo" em vez de propor quantidade nenhuma como se
    nada tivesse andado.
    """
    if item.atividade_id:
        return [item.atividade] if item.atividade is not None else []
    if item.item_orcado_id and cronograma is not None:
        return list(
            Atividade.objects.filter(
                cronograma=cronograma, item_orcado_id=item.item_orcado_id,
            )
        )
    return []


def avanco_do_periodo(atividades: list[Atividade], inicio: date, fim: date, *,
                      detalhado: bool = False):
    """`(percentual, criterio)` — quanto estas atividades andaram na janela.

    O apontamento é **delta**, então o avanço do período é literalmente a soma
    dos lançamentos com `data` dentro da janela, estornos incluídos (eles são
    negativos e por isso se cancelam sozinhos). Nada de subtrair acumulados de
    duas datas — isso reabriria a porta que o append-only fechou.

    **Com mais de uma atividade, a média é ponderada pelo peso** — o mesmo
    `peso_de` que a árvore do avanço usa, pelo mesmo motivo: duas frentes de
    tamanhos diferentes não contribuem igual para uma linha de contrato. Sem
    peso em nenhuma delas, cai para média simples e **declara** o critério, em
    vez de apresentar um número ponderado que não foi.

    `detalhado` acrescenta a **memória de cálculo**: uma entrada por atividade,
    com o avanço que ela apontou no período e o peso que teve na média. Sai da
    mesma consulta, sem custo novo, e é o que a tela mostra quando o gestor
    pergunta *"de onde saiu 95?"* — a pergunta que a grade não sabia responder,
    embora o servidor sempre tivesse a resposta na mão.
    """
    if not atividades:
        return (None, "sem_vinculo", []) if detalhado else (None, "sem_vinculo")

    ids = [a.pk for a in atividades]
    por_atividade = dict(
        ApontamentoAvanco.objects
        .filter(atividade_id__in=ids, data__gte=inicio, data__lte=fim)
        .values_list("atividade_id")
        .annotate(total=Sum("percentual"))
        .values_list("atividade_id", "total")
    )

    pesos: list[tuple[Decimal, Decimal]] = []
    soma_simples = _ZERO
    tem_peso = False
    detalhe: list[dict] = []
    for atividade in atividades:
        delta = por_atividade.get(atividade.pk) or _ZERO
        soma_simples += delta
        peso, origem_do_peso = peso_de(atividade)
        if peso is not None and peso > 0:
            tem_peso = True
            pesos.append((peso, delta))
        detalhe.append({
            "atividade_id": atividade.pk,
            "codigo": atividade.codigo,
            "nome": atividade.nome,
            "percentual": delta,
            "peso": peso,
            "origem_do_peso": origem_do_peso,
        })

    def responder(valor, criterio):
        return (valor, criterio, detalhe) if detalhado else (valor, criterio)

    if tem_peso and len(atividades) > 1:
        base = sum(p for p, _ in pesos)
        if base > 0:
            return responder(sum(p * d for p, d in pesos) / base, "ponderado")
    if len(atividades) == 1:
        return responder(soma_simples, "direto")
    return responder(soma_simples / Decimal(len(atividades)), "media_simples")


# --- A proposta e o contexto da grade ---------------------------------------


def propor_medicao(contrato: ContratoObra, *, inicio: date, fim: date,
                   medicao: Medicao | None = None) -> dict:
    """As linhas da grade — **a única fonte dos números que a tela mostra**.

    Devolve uma linha por item do contrato, sempre: inclusive as que não têm
    vínculo e as que não andaram, porque a grade precisa mostrar o contrato
    inteiro para que "não medi isto" seja uma decisão visível, e não uma linha
    que sumiu.

    Cada linha traz as dez colunas da G703 já calculadas — original, aditivo,
    atual, acumulado anterior, proposta do período, estoque anterior, saldo,
    percentual. **A tela não recalcula nenhuma delas.** Este contrato é o
    conserto de um defeito real: a primeira escrita da página montava
    `saldo = contratado − já medido` no navegador com dados que só existiam
    quando o gestor chegava pela prévia; entrando pelo link direto da medição,
    a mesma tela mostrava "já medido" **negativo** e saldo acima do contratado.

    Com `medicao`, a leitura é a de um documento aberto: o acumulado **exclui**
    as linhas dele (senão a própria medição apareceria como excesso contra si
    mesma) e cada linha vem com o que está gravado ali.

    **A quantidade proposta é limitada ao saldo**, e o motivo é declarado. Sem
    isso, um apontamento de avanço errado propagaria direto para uma proposta
    acima do contratado, e a validação só o pegaria na submissão — depois de o
    gestor ter conferido uma grade cheia de números impossíveis.
    """
    if fim < inicio:
        raise ValidationError("O fim do período não pode ser anterior ao início.")

    cronograma = _cronograma_vigente(contrato)
    itens = list(contrato.itens.select_related("aditivo_origem").all())
    excluir = medicao.pk if medicao is not None else None

    ja_medido = medido_por_item(contrato, excluir_medicao_id=excluir)
    aditado = aditivo_por_item(contrato)
    estoque_anterior = estocado_ate(
        contrato,
        antes_de=medicao.numero if medicao is not None else None,
        excluir_medicao_id=excluir,
    )
    gravado = {
        linha.item_contrato_id: linha
        for linha in (medicao.itens.all() if medicao is not None else [])
    }

    linhas = []
    for item in itens:
        atividades = _atividades_do_item(item, cronograma)
        percentual, criterio, memoria = avanco_do_periodo(
            atividades, inicio, fim, detalhado=True,
        )
        acumulado = ja_medido.get(item.pk, _ZERO)
        delta_aditivo = aditado.get(item.pk, _ZERO)
        contratado = item.quantidade_contratada + delta_aditivo
        estocado_antes = estoque_anterior.get(item.pk, _ZERO)
        # O saldo desconta o que já foi medido **e** o que já está estocado e
        # pago: material posto na obra ocupa contrato igual a serviço feito.
        saldo = contratado - acumulado - estocado_antes
        linha_gravada = gravado.get(item.pk)

        if percentual is None:
            quantidade, limitada = _ZERO, False
        else:
            quantidade = _quantidade(contratado * percentual / Decimal("100"))
            limitada = quantidade > saldo
            if limitada:
                quantidade = max(saldo, _ZERO)

        # Com o documento aberto, a proposta que vale é a **gravada nele**: ela
        # foi feita quando o documento nasceu, e recalculá-la agora apagaria o
        # rastro de "o sistema propôs 120 e o gestor confirmou 95".
        proposta = quantidade
        percentual_linha = percentual
        if linha_gravada is not None and linha_gravada.quantidade_proposta is not None:
            proposta = linha_gravada.quantidade_proposta
            percentual_linha = linha_gravada.percentual_avanco_periodo

        linhas.append({
            "item_contrato_id": item.pk,
            "codigo": item.codigo,
            "descricao": item.descricao,
            "unidade": item.unidade,
            # As três colunas do contratado. `quantidade_contratada` continua
            # sendo o nome do *atual* porque é contra ele que tudo se confere —
            # o original viaja ao lado, para a grade poder mostrar a diferença.
            "quantidade_contratada": contratado,
            "quantidade_original": item.quantidade_contratada,
            "quantidade_aditivada": delta_aditivo,
            "nasceu_de_aditivo": item.aditivo_origem_id is not None,
            "quantidade_ja_medida": acumulado,
            "saldo": saldo,
            "quantidade_proposta": proposta,
            "percentual_avanco_periodo": percentual_linha,
            "criterio": criterio,
            "limitada_pelo_saldo": limitada,
            "preco_unitario": (
                linha_gravada.preco_unitario if linha_gravada is not None
                else item.preco_unitario
            ),
            "atividades": [a.pk for a in atividades],
            # A memória de cálculo da linha — de onde saiu a proposta, atividade
            # por atividade. Vem junto porque sai da mesma consulta: pedi-la
            # depois seria uma chamada por linha clicada.
            "memoria": memoria,
            # O que está gravado no documento aberto (zero quando não há
            # documento, ou quando esta linha não foi medida).
            "quantidade_medida": (
                linha_gravada.quantidade if linha_gravada is not None else _ZERO
            ),
            "quantidade_estocada": (
                linha_gravada.quantidade_estocada if linha_gravada is not None
                else estocado_antes
            ),
            "estocado_anterior": estocado_antes,
            "origem": (
                linha_gravada.origem if linha_gravada is not None else None
            ),
            "observacao": (
                linha_gravada.observacao if linha_gravada is not None else ""
            ),
        })

    sem_vinculo = [linha for linha in linhas if linha["criterio"] == "sem_vinculo"]
    return {
        "contrato_id": contrato.pk,
        "regime": contrato.regime,
        "periodo": {"inicio": inicio, "fim": fim},
        "linhas": linhas,
        # O denominador da honestidade, na régua do `cobertura_do_orcamento`:
        # quem lê a proposta precisa saber quanto dela o sistema NÃO conseguiu
        # calcular, em vez de receber zeros indistinguíveis de "não andou".
        "cobertura": {
            "itens": len(linhas),
            "sem_vinculo": len(sem_vinculo),
            "codigos_sem_vinculo": [linha["codigo"] for linha in sem_vinculo][:20],
        },
    }


def contexto_de_medicao(medicao: Medicao) -> dict:
    """A grade de um documento que **existe** — a leitura da tela da medição.

    É `propor_medicao` amarrado ao período e ao estado do documento, mais o que
    só faz sentido com ele aberto: os totais congelados, as deduções e o degrau
    da escada. Uma chamada, uma verdade — a tela não soma nada.
    """
    proposta = propor_medicao(
        medicao.contrato,
        inicio=medicao.periodo_inicio,
        fim=medicao.periodo_fim,
        medicao=medicao,
    )
    proposta.update({
        "medicao_id": medicao.pk,
        "numero": medicao.numero,
        "status": medicao.status,
        "editavel": medicao.status == Medicao.Status.RASCUNHO,
        "totais": totais_da_medicao(medicao),
    })
    return proposta


def sugerir_periodo(contrato: ContratoObra) -> dict:
    """De quando a **próxima** medição deveria falar.

    Medição de obra é uma corrente: o período começa no dia seguinte ao fim do
    anterior, e um buraco entre dois períodos é serviço executado que ninguém
    mediu. A tela abria sempre em "primeiro do mês → hoje", o que produzia
    sobreposição no mês em que alguém mediu quinzenalmente e buraco no mês em
    que a medição atrasou.

    Devolve também o que **não** fecha, para a tela poder dizer em vez de
    esconder: `lacuna_dias` conta o vão entre a última medição e a sugestão,
    quando ele existe por decisão de quem mediu (uma medição que só foi aberta
    dois meses depois).
    """
    ultima = (
        contrato.medicoes.filter(status__in=_VIVAS, retifica__isnull=True)
        .order_by("-periodo_fim", "-numero")
        .first()
    )
    hoje = timezone.localdate()
    if ultima is None:
        inicio = contrato.data_inicio
    else:
        inicio = ultima.periodo_fim + timedelta(days=1)

    fim = hoje
    if contrato.data_fim and fim > contrato.data_fim:
        fim = contrato.data_fim
    if fim < inicio:
        fim = inicio

    return {
        "inicio": inicio,
        "fim": fim,
        "ultima_medicao": None if ultima is None else {
            "medicao_id": ultima.pk,
            "numero": ultima.numero,
            "periodo_fim": ultima.periodo_fim,
            "status": ultima.status,
        },
        "lacuna_dias": max((inicio - contrato.data_inicio).days, 0)
        if ultima is None else 0,
    }


def _conflito_de_periodo(contrato: ContratoObra, *, inicio: date, fim: date,
                         excluir_medicao_id: int | None = None) -> Medicao | None:
    """A medição em voo cujo período pisa neste — ou `None`.

    Duas medições cobrindo o mesmo dia pagam o mesmo avanço duas vezes: a
    proposta de ambas lê os mesmos apontamentos, e a trava do acumulado só
    percebe quando a soma estoura o contratado, que pode ser muitos meses
    depois. A retificadora é a exceção declarada — ela **repete** o período de
    propósito, porque está corrigindo aquele período.
    """
    return (
        contrato.medicoes
        .filter(status__in=_EM_VOO, retifica__isnull=True)
        .filter(periodo_inicio__lte=fim, periodo_fim__gte=inicio)
        .exclude(pk=excluir_medicao_id)
        .order_by("numero")
        .first()
    )


# --- Os totais do documento -------------------------------------------------


def valor_da_deducao(deducao: "DeducaoMedicao", bruto: Decimal) -> Decimal:
    """Quanto esta linha tira do pagamento.

    Percentual e valor nunca coexistem (constraint do model): o percentual
    incide sobre a base declarada — e, sem base declarada, sobre o bruto da
    medição, que é o caso comum.
    """
    if deducao.valor is not None:
        return _dinheiro(deducao.valor)
    base = deducao.base_calculo if deducao.base_calculo is not None else bruto
    return _dinheiro(base * (deducao.percentual or _ZERO) / Decimal("100"))


def totais_da_medicao(medicao: Medicao) -> dict:
    """Bruto → retenção → deduções → líquido, somados na leitura (§4.9).

    **Três regimes, três brutos:**

    - **unitário** e **global**: `Σ quantidade × preço do dia`, mais o material
      que entrou em estoque no período. São a mesma conta porque no global os
      itens *são* o cronograma físico-financeiro — o que muda é a invariante (a
      soma dos contratados fecha com `valor_global`), conferida em
      `validar_medicao`, e não a aritmética da medição;
    - **administração**: `custo reembolsável + taxa sobre ele`. Os itens não
      entram, porque o que se paga não é quantidade executada — é custo, e ele
      vem declarado com a origem junto (`OrigemCusto`).

    **O material estocado paga a diferença, não o saldo.** Um estoque de 100 t
    declarado em duas medições seguidas é a mesma 100 t: pagar o saldo em ambas
    pagaria o material duas vezes. O que entra no bruto é `estoque desta −
    estoque da anterior`, que é negativo quando o material foi aplicado — e é
    exatamente isso que faz o serviço executado, que entra pela quantidade, não
    ser cobrado duas vezes.

    **A retenção incide sobre o bruto; as deduções, sobre o que cada uma
    declara.** A ordem importa e é a do mercado: reter é a construtora segurando
    dinheiro que vai devolver (`LiberacaoRetencao`); deduzir é dinheiro que não
    volta (imposto, amortização, multa).
    """
    contrato = medicao.contrato
    executado = _ZERO
    estoque = _ZERO

    if contrato.regime == RegimeContrato.ADMINISTRACAO:
        custo = medicao.custo_reembolsavel or _ZERO
        taxa = medicao.taxa_administracao_aplicada or _ZERO
        bruto = custo + (custo * taxa / Decimal("100"))
    else:
        anterior = estocado_ate(
            contrato, antes_de=medicao.numero, excluir_medicao_id=medicao.pk,
        )
        for item in medicao.itens.all():
            executado += item.quantidade * item.preco_unitario
            delta = item.quantidade_estocada - anterior.get(
                item.item_contrato_id, _ZERO,
            )
            estoque += delta * item.preco_unitario
        bruto = executado + estoque

    bruto = _dinheiro(bruto)
    retencao = _dinheiro(bruto * medicao.retencao_percentual_aplicado / Decimal("100"))

    deducoes = []
    total_deducoes = _ZERO
    for deducao in medicao.deducoes.all():
        valor = valor_da_deducao(deducao, bruto)
        total_deducoes += valor
        deducoes.append({
            "deducao_id": deducao.pk,
            "tipo": deducao.tipo,
            "tipo_rotulo": deducao.get_tipo_display(),
            "descricao": deducao.descricao,
            "percentual": deducao.percentual,
            "base_calculo": deducao.base_calculo,
            "valor": valor,
        })

    return {
        "executado": _dinheiro(executado),
        "material_estocado": _dinheiro(estoque),
        "bruto": bruto,
        "retencao": retencao,
        "retencao_percentual": medicao.retencao_percentual_aplicado,
        "deducoes": deducoes,
        "total_deducoes": _dinheiro(total_deducoes),
        "liquido": bruto - retencao - _dinheiro(total_deducoes),
    }


# --- O ciclo de vida da medição ---------------------------------------------


@transaction.atomic
def criar_medicao(*, contrato: ContratoObra, inicio: date, fim: date,
                  por: str = "", linhas: list[dict] | None = None,
                  custo_reembolsavel: Decimal | None = None,
                  observacao: str = "") -> Medicao:
    """Abre o boletim do período, já preenchido pela proposta.

    `linhas` sobrescreve a proposta item a item (é o gestor conferindo antes
    mesmo de abrir); `None` aceita a proposta inteira. Em ambos os casos o que
    o sistema propôs fica guardado em `quantidade_proposta`, para o ajuste ser
    auditável.

    **O contrato precisa estar vigente.** Medir contrato em rascunho produziria
    título a pagar de um documento que ninguém assinou; medir contrato
    encerrado é o caminho do pagamento fora de vigência. Suspenso também
    recusa, que é o que "suspenso" quer dizer.

    **E o período não pode pisar no de outra medição em voo** — ver
    `_conflito_de_periodo`.
    """
    if contrato.status != ContratoObra.Status.VIGENTE:
        raise ValidationError(
            f"Só contrato vigente aceita medição (este está "
            f"{contrato.get_status_display().lower()})."
        )
    if inicio < contrato.data_inicio:
        raise ValidationError(
            f"O período começa em {inicio:%d/%m/%Y}, antes do início da vigência "
            f"({contrato.data_inicio:%d/%m/%Y})."
        )
    conflito = _conflito_de_periodo(contrato, inicio=inicio, fim=fim)
    if conflito is not None:
        raise ValidationError(
            f"O período {inicio:%d/%m/%Y}–{fim:%d/%m/%Y} se sobrepõe ao da "
            f"medição {conflito.numero} ({conflito.periodo_inicio:%d/%m/%Y}–"
            f"{conflito.periodo_fim:%d/%m/%Y}), que já está "
            f"{conflito.get_status_display().lower()}. Dois períodos que se "
            f"cruzam pagam o mesmo avanço duas vezes — comece no dia seguinte "
            f"ao fim dela, ou retifique-a."
        )

    proposta = {
        linha["item_contrato_id"]: linha
        for linha in propor_medicao(contrato, inicio=inicio, fim=fim)["linhas"]
    }
    escolhidas = (
        {linha["item_contrato_id"]: linha for linha in linhas}
        if linhas is not None else None
    )
    if escolhidas is not None:
        desconhecidos = set(escolhidas) - set(proposta)
        if desconhecidos:
            raise ValidationError(
                f"Itens que não são deste contrato: {sorted(desconhecidos)}."
            )
        if len(escolhidas) > PDCA_TETO_LINHAS_POR_MEDICAO:
            raise ValidationError(
                f"Uma medição aceita no máximo "
                f"{_milhar(PDCA_TETO_LINHAS_POR_MEDICAO)} linhas "
                f"(recebidas {_milhar(len(escolhidas))})."
            )

    proximo = (
        Medicao.todos.filter(contrato=contrato).aggregate(m=Max("numero"))["m"] or 0
    ) + 1

    medicao = Medicao.objects.create(
        tenant_id=contrato.tenant_id,
        contrato=contrato,
        numero=proximo,
        periodo_inicio=inicio,
        periodo_fim=fim,
        # Congelados no nascimento — mudar a cláusula depois não reescreve este
        # documento (ver os campos no model).
        retencao_percentual_aplicado=contrato.retencao_percentual,
        taxa_administracao_aplicada=contrato.taxa_administracao,
        custo_reembolsavel=custo_reembolsavel,
        custo_origem=OrigemCusto.INFORMADO,
        apurada_por=por or "",
        observacao=observacao,
    )

    a_gravar = []
    for item_id, linha in proposta.items():
        escolhida = escolhidas.get(item_id) if escolhidas is not None else linha
        if escolhida is None:
            continue
        quantidade = Decimal(str(
            escolhida.get("quantidade", linha["quantidade_proposta"])
        ))
        estocada = Decimal(str(
            escolhida.get("quantidade_estocada", linha["estocado_anterior"])
        ))
        # Linha sem quantidade **e** sem estoque não vira registro: o contrato
        # inteiro aparece na grade pela proposta, mas gravar um `ItemMedicao`
        # vazio encheria o documento de linhas que não pagam nada.
        if quantidade == 0 and estocada == 0:
            continue
        a_gravar.append(ItemMedicao(
            tenant_id=contrato.tenant_id,
            medicao=medicao,
            item_contrato_id=item_id,
            quantidade=quantidade,
            quantidade_estocada=estocada,
            quantidade_proposta=linha["quantidade_proposta"],
            preco_unitario=linha["preco_unitario"],
            percentual_avanco_periodo=linha["percentual_avanco_periodo"],
            origem=(
                ItemMedicao.Origem.AVANCO
                if escolhidas is None or quantidade == linha["quantidade_proposta"]
                else ItemMedicao.Origem.MANUAL
            ),
        ))
    if a_gravar:
        ItemMedicao.objects.bulk_create(a_gravar)
    return medicao


@transaction.atomic
def reescrever_linhas(*, medicao: Medicao, linhas: list[dict]) -> dict:
    """Substitui a grade do rascunho pelo que o gestor conferiu.

    **Substitui, não soma.** A grade da tela *é* o documento inteiro: um
    endpoint que acumulasse faria dois envios acidentais dobrarem a medição, e o
    gestor não teria como perceber — a tela mostraria o total certo depois do
    primeiro envio e o dobro depois do segundo, sem nenhuma linha nova visível.

    É o endpoint que o **autosave** da grade chama. Ele roda a cada pausa de
    digitação, e por isso é idempotente por construção: reenviar o mesmo corpo
    duas vezes deixa o documento no mesmo estado.

    A `quantidade_proposta` e o `percentual_avanco_periodo` da linha original
    **sobrevivem** à reescrita, e é isto que mantém o ajuste auditável: sem eles,
    reescrever apagaria a memória do que o sistema tinha calculado e o "ajustou
    de 120 para 95" viraria apenas "95".
    """
    if medicao.status != Medicao.Status.RASCUNHO:
        raise ValidationError(
            f"Só o rascunho aceita reescrita (esta medição está "
            f"{medicao.get_status_display().lower()})."
        )
    if len(linhas) > PDCA_TETO_LINHAS_POR_MEDICAO:
        raise ValidationError(
            f"Uma medição aceita no máximo "
            f"{_milhar(PDCA_TETO_LINHAS_POR_MEDICAO)} linhas "
            f"(recebidas {_milhar(len(linhas))})."
        )

    contrato = medicao.contrato
    validos = {item.pk: item for item in contrato.itens.all()}
    desconhecidos = {
        linha["item_contrato_id"] for linha in linhas
    } - set(validos)
    if desconhecidos:
        raise ValidationError(
            f"Itens que não são deste contrato: {sorted(desconhecidos)}."
        )

    # O que o sistema tinha proposto, para não se perder na substituição.
    memoria = {
        linha.item_contrato_id: (
            linha.quantidade_proposta, linha.percentual_avanco_periodo,
            linha.preco_unitario, linha.observacao,
        )
        for linha in medicao.itens.all()
    }

    medicao.itens.all().delete()
    a_gravar = []
    for linha in linhas:
        quantidade = Decimal(str(linha.get("quantidade", 0) or 0))
        estocada = Decimal(str(linha.get("quantidade_estocada", 0) or 0))
        if quantidade == 0 and estocada == 0:
            continue
        item_id = linha["item_contrato_id"]
        proposta, percentual, preco, observacao = memoria.get(
            item_id, (None, None, None, ""),
        )
        a_gravar.append(ItemMedicao(
            tenant_id=contrato.tenant_id,
            medicao=medicao,
            item_contrato_id=item_id,
            quantidade=quantidade,
            quantidade_estocada=estocada,
            quantidade_proposta=proposta,
            # O preço é o **do documento**, quando a linha já existia nele: o
            # `ItemMedicao` congela o preço do dia em que a medição nasceu, e
            # reler o preço do contrato aqui faria uma revisão de preço por
            # aditivo reescrever em silêncio um rascunho já conferido.
            preco_unitario=(
                preco if preco is not None else validos[item_id].preco_unitario
            ),
            percentual_avanco_periodo=percentual,
            observacao=linha.get("observacao", observacao) or "",
            origem=(
                ItemMedicao.Origem.AVANCO
                if proposta is not None and quantidade == proposta
                else ItemMedicao.Origem.MANUAL
            ),
        ))
    if a_gravar:
        ItemMedicao.objects.bulk_create(a_gravar)

    medicao.refresh_from_db()
    return {"linhas": len(a_gravar), "totais": totais_da_medicao(medicao)}


@transaction.atomic
def reescrever_deducoes(*, medicao: Medicao, deducoes: list[dict]) -> dict:
    """Substitui as deduções do rascunho — mesma regra da grade.

    **Por que elas não são só um campo "outros descontos".** Tipar permite ao
    financeiro conciliar a guia de INSS com as medições que a originaram, e ao
    gestor explicar por que o empreiteiro recebeu 82% do que mediu sem abrir
    cinco documentos. O texto livre resolve o líquido e não responde nenhuma
    das duas perguntas.
    """
    if medicao.status != Medicao.Status.RASCUNHO:
        raise ValidationError(
            f"Só o rascunho aceita mudança de deduções (esta medição está "
            f"{medicao.get_status_display().lower()})."
        )
    if len(deducoes) > PDCA_TETO_DEDUCOES_POR_MEDICAO:
        raise ValidationError(
            f"Uma medição aceita no máximo "
            f"{_milhar(PDCA_TETO_DEDUCOES_POR_MEDICAO)} deduções "
            f"(recebidas {_milhar(len(deducoes))})."
        )

    problemas = []
    for linha in deducoes:
        tem_percentual = linha.get("percentual") is not None
        tem_valor = linha.get("valor") is not None
        if tem_percentual == tem_valor:
            problemas.append(
                f"{linha.get('tipo', 'dedução')}: informe **ou** o percentual "
                f"**ou** o valor, nunca os dois nem nenhum."
            )
        if linha.get("tipo") == TipoDeducao.OUTROS and not (
            linha.get("descricao") or ""
        ).strip():
            problemas.append(
                "Dedução do tipo 'Outros' exige descrição — é ela que diz o que "
                "está sendo descontado do empreiteiro."
            )
    if problemas:
        raise ValidationError(problemas)

    medicao.deducoes.all().delete()
    if deducoes:
        DeducaoMedicao.objects.bulk_create([
            DeducaoMedicao(
                tenant_id=medicao.tenant_id,
                medicao=medicao,
                tipo=linha["tipo"],
                descricao=linha.get("descricao", "") or "",
                base_calculo=linha.get("base_calculo"),
                percentual=linha.get("percentual"),
                valor=linha.get("valor"),
            )
            for linha in deducoes
        ])

    medicao.refresh_from_db()
    return {"deducoes": len(deducoes), "totais": totais_da_medicao(medicao)}


def validar_medicao(medicao: Medicao) -> dict:
    """As travas que a planta manda, todas de uma vez — e a lista inteira.

    Devolve `{"avisos": [...]}` quando passa; levanta `ValidationError` com
    **todos** os problemas quando não. Parar no primeiro faria o gestor corrigir
    uma linha, resubmeter e descobrir a segunda — três idas e vindas para um
    documento que ele vê inteiro na tela.

    A trava central é a do mercado (§4.4): **medição acumulada não pode exceder
    o contratado** — o *atual*, com aditivos aprovados dentro. Ela conta as
    aprovadas e as que estão na escada, pelo motivo do cabeçalho deste bloco.
    """
    contrato = medicao.contrato
    problemas: list[str] = []
    avisos: list[str] = []

    if contrato.regime == RegimeContrato.ADMINISTRACAO:
        if medicao.custo_reembolsavel is None:
            problemas.append(
                "Contrato por administração: informe o custo reembolsável do período."
            )
        if contrato.taxa_administracao is None:
            problemas.append(
                "Contrato por administração sem taxa definida — defina a taxa no "
                "contrato antes de medir."
            )
        # **A régua de dado honesto é cumprida pelo REGISTRO, não por um aviso.**
        # `custo_origem` grava quem informou o número e o boletim o imprime —
        # quem ateste lê isso no documento que está assinando. O aviso que
        # existia aqui repetia, em toda submissão, uma frase que não dizia o que
        # fazer ("a apropriação de HH ainda não está ligada") e que só faz
        # sentido para quem conhece o roadmap. Aviso que aparece sempre e não
        # pede ação nenhuma é ruído: ensina a ignorar a faixa de avisos, onde um
        # dia vai aparecer algo que importa.
    else:
        if not medicao.itens.exists():
            problemas.append("A medição não tem nenhuma linha com quantidade.")

    if contrato.regime == RegimeContrato.GLOBAL:
        atual = contratado_atual_por_item(contrato)
        soma_itens = _dinheiro(sum(
            (atual.get(i.pk, i.quantidade_contratada) * i.preco_unitario
             for i in contrato.itens.all()), _ZERO,
        ))
        fechado = _dinheiro(
            (contrato.valor_global or _ZERO) + valor_dos_aditivos(contrato)
        )
        if soma_itens != fechado:
            problemas.append(
                f"Preço global: a soma dos itens (R$ {soma_itens}) não fecha com o "
                f"valor global do contrato (R$ {fechado}). Ajuste a planilha "
                f"contratual antes de medir — é ela que diz quanto cada frente vale."
            )

    # --- a trava do acumulado -------------------------------------------------
    ja_medido = medido_por_item(contrato, excluir_medicao_id=medicao.pk)
    estoque_anterior = estocado_ate(
        contrato, antes_de=medicao.numero, excluir_medicao_id=medicao.pk,
    )
    atual = contratado_atual_por_item(contrato)
    codigos = {item.pk: item.codigo for item in contrato.itens.all()}

    for linha in medicao.itens.all():
        contratado = atual.get(linha.item_contrato_id, _ZERO)
        codigo = codigos.get(linha.item_contrato_id, str(linha.item_contrato_id))
        acumulado = ja_medido.get(linha.item_contrato_id, _ZERO) + linha.quantidade
        # Executado acumulado **mais** o material ainda estocado: os dois
        # ocupam contrato, e conferir só o executado deixaria pagar material
        # até o dobro do contratado antes de qualquer alarme.
        ocupado = acumulado + linha.quantidade_estocada
        if ocupado > contratado:
            excesso = ocupado - contratado
            estoque = (
                f" (executado {acumulado} + estocado {linha.quantidade_estocada})"
                if linha.quantidade_estocada else ""
            )
            problemas.append(
                f"Item {codigo}: o acumulado medido ({ocupado}){estoque} excede o "
                f"contratado ({contratado}) em {excesso}. Aumentar quantidade "
                f"contratada é aditivo, não medição."
            )
        if acumulado < 0:
            problemas.append(
                f"Item {codigo}: a retificação deixaria o acumulado negativo "
                f"({acumulado}) — não se devolve mais do que se mediu."
            )
        # Material que baixou sem o serviço aparecer: não é erro (o empreiteiro
        # pode ter devolvido material à contratante), mas é o tipo de linha que
        # ninguém quer descobrir depois de assinar.
        antes = estoque_anterior.get(linha.item_contrato_id, _ZERO)
        if linha.quantidade_estocada < antes and linha.quantidade == 0:
            avisos.append(
                f"Item {codigo}: o material estocado caiu de {antes} para "
                f"{linha.quantidade_estocada} sem quantidade executada no período "
                f"— esta medição devolve R$ "
                f"{_dinheiro((antes - linha.quantidade_estocada) * linha.preco_unitario)}."
            )

    if contrato.data_fim and medicao.periodo_fim > contrato.data_fim:
        # Aviso, e não recusa: o serviço é executado dentro da vigência e medido
        # depois dela o tempo todo — é o caso normal da última medição. O que
        # seria erro é medir **antes** do início, e isso o `criar_medicao` já
        # recusa na entrada.
        avisos.append(
            f"O período termina em {medicao.periodo_fim:%d/%m/%Y}, depois do fim "
            f"da vigência ({contrato.data_fim:%d/%m/%Y})."
        )

    # --- o líquido precisa existir -------------------------------------------
    #
    # **Só quando o bruto é positivo.** A retificadora que devolve quantidade
    # tem bruto negativo por natureza (é uma devolução), e ali o líquido
    # negativo é o resultado certo — `gerar_titulo_de_medicao` não emite título
    # nenhum para ela. Aplicar a trava sem esta condição proibiria exatamente o
    # documento que a §11.5 criou para corrigir uma medição paga a mais.
    totais = totais_da_medicao(medicao)
    if totais["bruto"] > 0 and totais["liquido"] < 0:
        problemas.append(
            f"As deduções (R$ {totais['total_deducoes']}) e a retenção "
            f"(R$ {totais['retencao']}) somam mais que o bruto "
            f"(R$ {totais['bruto']}) — o líquido ficaria negativo, e título "
            f"negativo é documento que ninguém consegue baixar no financeiro."
        )

    if problemas:
        raise ValidationError(problemas)
    return {"avisos": avisos}


@transaction.atomic
def submeter_medicao(*, medicao: Medicao, solicitante, observacao: str = "") -> dict:
    """Rascunho → escada de atesto (ou aprovação em um passo).

    **Sem fluxo configurado, aprova em um passo.** Não é atalho: é o contrato
    escrito do motor do `nucleo` (*"módulo sem escada configurada aprova em um
    passo, do jeito que já aprovava"*). Recusar aqui obrigaria todo tenant a
    configurar uma escada antes de emitir a primeira medição — fricção numa
    tela de administração para exercer o caminho principal do módulo.

    Quem aprova em um passo precisa de `pdca.medicao.atestar`; a view confere
    isso antes de chamar. Havendo escada, a permissão de cada degrau é a que o
    tenant declarou, e o motor a confere sozinho.
    """
    from nucleo import aprovacao as motor

    if medicao.status != Medicao.Status.RASCUNHO:
        raise ValidationError(
            f"Só medição em rascunho pode ser submetida (esta está "
            f"{medicao.get_status_display().lower()})."
        )
    resultado = validar_medicao(medicao)
    totais = totais_da_medicao(medicao)

    fluxo = motor.fluxo_para(medicao, tenant_id=medicao.tenant_id)
    if fluxo is None:
        _congelar_medicao(medicao, aprovada=True)
        return {
            "estado": "aprovada",
            "escada": None,
            "totais": totais,
            "avisos": resultado["avisos"],
        }

    pedido = motor.abrir(
        alvo=medicao, solicitante=solicitante,
        resumo=(
            f"Medição {medicao.numero} · contrato {medicao.contrato.numero} · "
            f"líquido R$ {totais['liquido']}"
        ),
        valor=totais["liquido"],
    )
    medicao.status = Medicao.Status.EM_APROVACAO
    medicao.save(update_fields=["status"])
    return {
        "estado": "em_aprovacao",
        "escada": pedido.pk,
        "totais": totais,
        "avisos": resultado["avisos"],
    }


def _congelar_medicao(medicao: Medicao, *, aprovada: bool) -> Medicao:
    """O último degrau fecha o documento — e, aprovada, gera o título.

    **Revalida antes de congelar**, e isto não é paranoia: entre a submissão e o
    atesto do último degrau podem passar dias, e nesse intervalo outra medição
    do mesmo contrato pode ter sido aprovada. Sem a revalidação, as duas
    passariam e o contratado seria estourado por uma corrida de calendário, não
    de milissegundos.
    """
    if aprovada:
        validar_medicao(medicao)

    medicao.status = (
        Medicao.Status.APROVADA if aprovada else Medicao.Status.REPROVADA
    )
    medicao.congelada_em = timezone.now()
    campos = ["status", "congelada_em"]

    if aprovada:
        conta_id = gerar_titulo_de_medicao(medicao)
        if conta_id is not None:
            medicao.conta_pagar_ref = conta_id
            campos.append("conta_pagar_ref")

    medicao.save(update_fields=campos)
    return medicao


def gerar_titulo_de_medicao(medicao: Medicao) -> int | None:
    """Medição aprovada → `ContaPagar` no ERP. O líquido, não o bruto.

    **Importa tarde, de propósito.** O `moduloerp` é importado aqui dentro e não
    no topo do arquivo porque a §7 da planta é explícita: o PDCA *não paga*. Uma
    importação de módulo faria o planejamento deixar de carregar numa instalação
    que não contrate o ERP — e o seam é frouxo justamente para que a fronteira
    seja atravessável nos dois sentidos, ou em nenhum.

    **O que vai para o título é o líquido** — depois da retenção **e** das
    deduções. A retenção fica com a construtora até a `LiberacaoRetencao`; o
    imposto retido vai para a União; o adiantamento já foi pago antes. Mandar o
    bruto e "descontar depois" produziria um título que ninguém consegue
    conciliar com o boleto do empreiteiro, que é a razão de a descrição abaixo
    listar as parcelas em vez de só o valor.
    """
    from moduloerp.models import ContaPagar

    totais = totais_da_medicao(medicao)
    if totais["liquido"] <= 0:
        # Medição que não paga nada não gera título. É caso real — a
        # retificadora que zera uma medição anterior —, e um `ContaPagar` de
        # R$ 0,00 seria documento que ninguém consegue baixar nem explicar.
        return None

    contrato = medicao.contrato
    vencimento = timezone.localdate() + timedelta(
        days=contrato.prazo_pagamento_dias or 0
    )
    parcelas = ""
    if totais["retencao"] > 0:
        parcelas += (
            f" · retenção R$ {totais['retencao']} "
            f"({medicao.retencao_percentual_aplicado}%)"
        )
    if totais["total_deducoes"] > 0:
        rotulos = ", ".join(
            sorted({d["tipo_rotulo"] for d in totais["deducoes"]})
        )
        parcelas += f" · deduções R$ {totais['total_deducoes']} ({rotulos})"

    conta = ContaPagar.objects.create(
        tenant_id=medicao.tenant_id,
        fornecedor_id=contrato.fornecedor_id,
        empreendimento_id=getattr(contrato.obra, "empreendimento_id", None),
        descricao=(
            f"Medição {medicao.numero} · contrato {contrato.numero} · "
            f"{contrato.obra.nome_obra} · período "
            f"{medicao.periodo_inicio:%d/%m/%Y}–{medicao.periodo_fim:%d/%m/%Y}"
            + parcelas
        ),
        valor=totais["liquido"],
        data_emissao=timezone.localdate(),
        data_vencimento=vencimento,
    )
    return conta.pk


# --- Aditivo: o contrato mudando por escrito (PDCA.4) -----------------------


def resumo_do_aditivo(aditivo: "AditivoContrato") -> dict:
    """Quanto este aditivo acrescenta, suprime e vale — derivado das linhas.

    O **percentual** é sobre o contratado **original**, e não sobre o valor de
    hoje: é assim que o limite legal é conferido, e conferir contra o valor
    aditado deixaria o segundo aditivo de 20% passar como se fosse 40% quando
    são 44% do contrato assinado.
    """
    acrescimo = _ZERO
    supressao = _ZERO
    revisao = _ZERO

    for linha in aditivo.itens.all():
        preco = linha.preco_unitario
        if preco is None:
            preco = (
                linha.item_contrato.preco_unitario
                if linha.item_contrato is not None else _ZERO
            )
        valor = linha.quantidade_delta * preco
        if linha.acao == AcaoAditivo.PRECO:
            # Revisão de preço vale sobre o **saldo** a executar: o que já foi
            # medido está congelado no preço antigo e não se reescreve.
            anterior = (
                linha.item_contrato.preco_unitario
                if linha.item_contrato is not None else _ZERO
            )
            saldo = _ZERO
            if linha.item_contrato is not None:
                contrato = aditivo.contrato
                medido = medido_por_item(contrato).get(linha.item_contrato_id, _ZERO)
                atual = contratado_atual_por_item(contrato).get(
                    linha.item_contrato_id, _ZERO,
                )
                saldo = max(atual - medido, _ZERO)
            revisao += ((preco or _ZERO) - anterior) * saldo
        elif valor >= 0:
            acrescimo += valor
        else:
            supressao += valor

    original = valor_contratado_original(aditivo.contrato)
    liquido = acrescimo + supressao + revisao
    return {
        "acrescimo": _dinheiro(acrescimo),
        "supressao": _dinheiro(supressao),
        "revisao_de_preco": _dinheiro(revisao),
        "liquido": _dinheiro(liquido),
        "contratado_original": original,
        "percentual_sobre_original": (
            _dinheiro(liquido * Decimal("100") / original) if original else None
        ),
        "itens": aditivo.itens.count(),
    }


@transaction.atomic
def criar_aditivo(*, contrato: ContratoObra, objeto: str, justificativa: str,
                  por: str = "", data_assinatura: date | None = None,
                  nova_data_fim: date | None = None,
                  itens: list[dict] | None = None) -> AditivoContrato:
    """Abre o aditivo em rascunho. **Não muda saldo nenhum** até ser aprovado."""
    if contrato.status not in (
        ContratoObra.Status.VIGENTE, ContratoObra.Status.SUSPENSO,
    ):
        raise ValidationError(
            f"Só contrato vigente ou suspenso aceita aditivo (este está "
            f"{contrato.get_status_display().lower()})."
        )
    if not (justificativa or "").strip():
        raise ValidationError(
            "O aditivo exige justificativa — é o campo que a auditoria lê "
            "primeiro, e é o que separa a correção do erro."
        )
    abertos = contrato.aditivos.filter(
        status__in=(
            AditivoContrato.Status.RASCUNHO, AditivoContrato.Status.EM_APROVACAO,
        )
    ).count()
    if abertos >= PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO:
        raise ValidationError(
            f"Este contrato já tem {_milhar(abertos)} aditivos em aberto — "
            f"conclua-os antes de abrir outro. Dois aditivos abertos sobre as "
            f"mesmas linhas se conferem contra o mesmo saldo e passam os dois."
        )

    proximo = (
        AditivoContrato.todos.filter(contrato=contrato)
        .aggregate(m=Max("numero"))["m"] or 0
    ) + 1
    aditivo = AditivoContrato.objects.create(
        tenant_id=contrato.tenant_id,
        contrato=contrato,
        numero=proximo,
        objeto=objeto,
        justificativa=justificativa,
        data_assinatura=data_assinatura,
        nova_data_fim=nova_data_fim,
        criado_por=por or "",
    )
    if itens:
        reescrever_itens_do_aditivo(aditivo=aditivo, itens=itens)
    return aditivo


@transaction.atomic
def reescrever_itens_do_aditivo(*, aditivo: AditivoContrato,
                                itens: list[dict]) -> dict:
    """Substitui as linhas do aditivo em rascunho — mesma regra da grade."""
    if aditivo.status != AditivoContrato.Status.RASCUNHO:
        raise ValidationError(
            f"Só o rascunho aceita reescrita (este aditivo está "
            f"{aditivo.get_status_display().lower()})."
        )
    if len(itens) > PDCA_TETO_ITENS_POR_ADITIVO:
        raise ValidationError(
            f"Um aditivo aceita no máximo "
            f"{_milhar(PDCA_TETO_ITENS_POR_ADITIVO)} linhas "
            f"(recebidas {_milhar(len(itens))})."
        )

    contrato = aditivo.contrato
    validos = {item.pk: item for item in contrato.itens.all()}
    problemas: list[str] = []
    a_gravar: list[ItemAditivo] = []
    codigos_novos: set[str] = set()

    for linha in itens:
        acao = linha.get("acao")
        item_id = linha.get("item_contrato_id")
        delta = Decimal(str(linha.get("quantidade_delta", 0) or 0))
        preco = linha.get("preco_unitario")

        if acao == AcaoAditivo.INCLUSAO:
            codigo = (linha.get("codigo_novo") or "").strip()
            if not codigo:
                problemas.append("Inclusão de item exige código.")
            elif codigo in codigos_novos:
                problemas.append(f"O código {codigo} aparece duas vezes no aditivo.")
            elif contrato.itens.filter(codigo=codigo).exists():
                problemas.append(
                    f"O código {codigo} já existe na planilha contratual — "
                    f"para mudar a quantidade dele use acréscimo, não inclusão."
                )
            codigos_novos.add(codigo)
            if not (linha.get("descricao_nova") or "").strip():
                problemas.append(f"Item novo {codigo}: informe a descrição.")
            if delta <= 0:
                problemas.append(
                    f"Item novo {codigo}: a quantidade precisa ser positiva."
                )
            if preco is None:
                problemas.append(f"Item novo {codigo}: informe o preço unitário.")
        else:
            if item_id not in validos:
                problemas.append(
                    f"Item {item_id} não é deste contrato."
                )
                continue
            codigo = validos[item_id].codigo
            if acao == AcaoAditivo.ACRESCIMO and delta <= 0:
                problemas.append(f"Item {codigo}: acréscimo exige quantidade positiva.")
            if acao == AcaoAditivo.SUPRESSAO and delta >= 0:
                problemas.append(
                    f"Item {codigo}: supressão é quantidade **negativa** — é ela "
                    f"que tira do contratado."
                )
            if acao == AcaoAditivo.PRECO:
                if preco is None:
                    problemas.append(f"Item {codigo}: revisão de preço exige o preço novo.")
                if delta != 0:
                    problemas.append(
                        f"Item {codigo}: revisão de preço não mexe em quantidade — "
                        f"abra uma linha de acréscimo ou supressão para isso."
                    )

        a_gravar.append(ItemAditivo(
            tenant_id=aditivo.tenant_id,
            aditivo=aditivo,
            item_contrato_id=(
                None if acao == AcaoAditivo.INCLUSAO else item_id
            ),
            acao=acao,
            quantidade_delta=delta,
            preco_unitario=None if preco is None else Decimal(str(preco)),
            codigo_novo=(linha.get("codigo_novo") or "").strip(),
            descricao_nova=(linha.get("descricao_nova") or "").strip(),
            unidade_nova=(linha.get("unidade_nova") or "").strip(),
            observacao=linha.get("observacao", "") or "",
        ))

    if problemas:
        raise ValidationError(problemas)

    aditivo.itens.all().delete()
    if a_gravar:
        ItemAditivo.objects.bulk_create(a_gravar)
    aditivo.refresh_from_db()
    return {"itens": len(a_gravar), "resumo": resumo_do_aditivo(aditivo)}


def validar_aditivo(aditivo: AditivoContrato) -> dict:
    """As três travas do §4.4, todas de uma vez.

    1. **Nada cai abaixo do já medido.** Suprimir 200 m² de um item que já teve
       300 m² medidos e pagos não é supressão: é pedir ao sistema para esquecer
       um pagamento que aconteceu.
    2. **O limite do regime público é o do contrato**, digitado pelo usuário —
       o sistema não escolhe 25% nem 50% por ninguém (§11.3).
    3. **Preço revisado não toca medição congelada.** Não é trava, é
       consequência: o `ItemMedicao` guarda o preço do dia, então nenhuma
       medição passada muda. O que se confere aqui é o que isso implica para o
       saldo a executar.
    """
    contrato = aditivo.contrato
    problemas: list[str] = []
    avisos: list[str] = []

    linhas = list(aditivo.itens.select_related("item_contrato").all())
    if not linhas and aditivo.nova_data_fim is None:
        problemas.append(
            "O aditivo não muda nada: sem linhas e sem nova data de fim."
        )

    medido = medido_por_item(contrato)
    atual = contratado_atual_por_item(contrato)
    estocado = estocado_ate(contrato)

    for linha in linhas:
        if linha.item_contrato is None:
            continue
        item = linha.item_contrato
        depois = atual.get(item.pk, item.quantidade_contratada) + linha.quantidade_delta
        ocupado = medido.get(item.pk, _ZERO) + estocado.get(item.pk, _ZERO)
        if depois < ocupado:
            problemas.append(
                f"Item {item.codigo}: o aditivo deixaria o contratado em {depois}, "
                f"abaixo do que já foi medido e estocado ({ocupado}). A quantidade "
                f"final de um item nunca cai abaixo do já medido."
            )
        if depois < 0:
            problemas.append(
                f"Item {item.codigo}: o contratado ficaria negativo ({depois})."
            )

    resumo = resumo_do_aditivo(aditivo)
    if contrato.regime_publico and contrato.limite_acrescimo_percentual is not None:
        # O acumulado conta os aditivos **já aprovados** mais este: é o limite
        # do contrato, não o de cada documento isolado.
        aprovado = _ZERO
        for outro in contrato.aditivos.filter(
            status=AditivoContrato.Status.APROVADO,
        ).exclude(pk=aditivo.pk):
            aprovado += resumo_do_aditivo(outro)["acrescimo"]
        acrescimo_total = aprovado + resumo["acrescimo"]
        original = resumo["contratado_original"]
        if original:
            percentual = _dinheiro(acrescimo_total * Decimal("100") / original)
            if percentual > contrato.limite_acrescimo_percentual:
                problemas.append(
                    f"Regime público: os acréscimos somam {percentual}% do "
                    f"contratado original (R$ {acrescimo_total} sobre "
                    f"R$ {original}), acima do limite de "
                    f"{contrato.limite_acrescimo_percentual}% declarado neste "
                    f"contrato."
                )
            elif percentual > contrato.limite_acrescimo_percentual * Decimal("0.8"):
                avisos.append(
                    f"Os acréscimos já somam {percentual}% do contratado "
                    f"original — o limite declarado é "
                    f"{contrato.limite_acrescimo_percentual}%."
                )

    if aditivo.nova_data_fim is not None:
        if aditivo.nova_data_fim < contrato.data_inicio:
            problemas.append(
                f"A nova data de fim ({aditivo.nova_data_fim:%d/%m/%Y}) é anterior "
                f"ao início da vigência ({contrato.data_inicio:%d/%m/%Y})."
            )
        elif contrato.data_fim and aditivo.nova_data_fim < contrato.data_fim:
            avisos.append(
                f"A nova data de fim ({aditivo.nova_data_fim:%d/%m/%Y}) **antecipa** "
                f"o fim da vigência, que hoje é {contrato.data_fim:%d/%m/%Y}."
            )

    if problemas:
        raise ValidationError(problemas)
    return {"avisos": avisos, "resumo": resumo}


@transaction.atomic
def submeter_aditivo(*, aditivo: AditivoContrato, solicitante) -> dict:
    """Rascunho → escada própria (ou aprovação em um passo, sem fluxo)."""
    from nucleo import aprovacao as motor

    if aditivo.status != AditivoContrato.Status.RASCUNHO:
        raise ValidationError(
            f"Só aditivo em rascunho pode ser submetido (este está "
            f"{aditivo.get_status_display().lower()})."
        )
    resultado = validar_aditivo(aditivo)

    fluxo = motor.fluxo_para(aditivo, tenant_id=aditivo.tenant_id)
    if fluxo is None:
        _congelar_aditivo(aditivo, aprovado=True)
        return {
            "estado": "aprovado", "escada": None,
            "resumo": resultado["resumo"], "avisos": resultado["avisos"],
        }

    pedido = motor.abrir(
        alvo=aditivo, solicitante=solicitante,
        resumo=(
            f"Aditivo {aditivo.numero} · contrato {aditivo.contrato.numero} · "
            f"líquido R$ {resultado['resumo']['liquido']}"
        ),
        valor=resultado["resumo"]["liquido"],
    )
    aditivo.status = AditivoContrato.Status.EM_APROVACAO
    aditivo.save(update_fields=["status"])
    return {
        "estado": "em_aprovacao", "escada": pedido.pk,
        "resumo": resultado["resumo"], "avisos": resultado["avisos"],
    }


@transaction.atomic
def _congelar_aditivo(aditivo: AditivoContrato, *, aprovado: bool) -> AditivoContrato:
    """O último degrau fecha o aditivo — e, aprovado, **aplica**.

    Revalida antes, pelo mesmo motivo da medição: entre a submissão e o atesto
    podem passar dias, e nesse intervalo uma medição pode ter consumido o saldo
    que a supressão ia tirar.
    """
    if aprovado:
        validar_aditivo(aditivo)
        aplicar_aditivo(aditivo)

    aditivo.status = (
        AditivoContrato.Status.APROVADO if aprovado
        else AditivoContrato.Status.REPROVADO
    )
    campos = ["status"]
    if aprovado:
        aditivo.aplicado_em = timezone.now()
        campos.append("aplicado_em")
    aditivo.save(update_fields=campos)
    return aditivo


@transaction.atomic
def aplicar_aditivo(aditivo: AditivoContrato) -> dict:
    """O que o aditivo aprovado **escreve** no contrato.

    Três efeitos, e só três:

    - **inclusão** cria o `ItemContrato` — com quantidade original **zero** e
      `aditivo_origem` preenchido, porque a quantidade dele mora no
      `ItemAditivo` e a regra `atual = original + Σ deltas` vale sem exceção;
    - **revisão de preço** reescreve `preco_unitario` na linha e guarda o
      anterior no `ItemAditivo`. É o único dado do contrato que um aditivo
      sobrescreve, e é seguro porque o `ItemMedicao` congela o preço do dia;
    - **nova data de fim** move a vigência.

    Acréscimo e supressão **não escrevem nada**: eles já são o delta, e o
    contratado atual é a soma deles. Reescrever a quantidade do item aqui seria
    a segunda verdade que o §4.9 proíbe — e apagaria o contratado original, que
    é o denominador do limite legal.
    """
    contrato = aditivo.contrato
    criados = 0
    precos = 0

    ordem = (
        contrato.itens.aggregate(m=Max("ordem"))["m"] or 0
    )
    for linha in aditivo.itens.select_related("item_contrato").all():
        if linha.acao == AcaoAditivo.INCLUSAO and linha.item_contrato_id is None:
            ordem += 1
            item = ItemContrato.objects.create(
                tenant_id=contrato.tenant_id,
                contrato=contrato,
                aditivo_origem=aditivo,
                codigo=linha.codigo_novo,
                descricao=linha.descricao_nova,
                unidade=linha.unidade_nova,
                ordem=ordem,
                quantidade_contratada=_ZERO,
                preco_unitario=linha.preco_unitario or _ZERO,
            )
            linha.item_contrato = item
            linha.save(update_fields=["item_contrato"])
            criados += 1
        elif linha.acao == AcaoAditivo.PRECO and linha.item_contrato is not None:
            item = linha.item_contrato
            linha.preco_unitario_anterior = item.preco_unitario
            linha.save(update_fields=["preco_unitario_anterior"])
            item.preco_unitario = linha.preco_unitario or item.preco_unitario
            item.save(update_fields=["preco_unitario", "atualizado_em"])
            precos += 1

    if aditivo.nova_data_fim is not None:
        contrato.data_fim = aditivo.nova_data_fim
        contrato.save(update_fields=["data_fim", "atualizado_em"])

    return {"itens_criados": criados, "precos_revisados": precos}


# --- Retenção: o que ficou retido, e o que dá para liberar ------------------


def retido_acumulado(contrato: ContratoObra) -> Decimal:
    """Quanto já foi retido nas medições **aprovadas**.

    Só as aprovadas: retenção de medição que ainda sobe a escada não foi
    descontada de nada, e contá-la ofereceria para liberação um dinheiro que
    ninguém segurou ainda.
    """
    total = _ZERO
    for medicao in contrato.medicoes.filter(status=Medicao.Status.APROVADA):
        total += totais_da_medicao(medicao)["retencao"]
    return _dinheiro(total)


def liberado_acumulado(contrato: ContratoObra) -> Decimal:
    """O que já saiu de volta — aprovadas e em aprovação.

    As em aprovação contam pelo mesmo motivo do acumulado da medição: duas
    liberações na escada ao mesmo tempo poderiam, cada uma sozinha, caber no
    saldo, e juntas devolver mais do que foi retido.
    """
    total = contrato.liberacoes.filter(
        status__in=(
            LiberacaoRetencao.Status.APROVADA,
            LiberacaoRetencao.Status.EM_APROVACAO,
        )
    ).aggregate(t=Sum("valor"))["t"] or _ZERO
    return _dinheiro(total)


def retencao_disponivel(contrato: ContratoObra) -> dict:
    """Retido − liberado, e as três parcelas junto.

    Devolve as parcelas, e não só o saldo, porque a tela precisa poder explicar
    o número: "R$ 12.400 retidos, R$ 4.000 já liberados" é uma frase que o
    gestor confere contra o extrato; "saldo R$ 8.400" é um número que ele tem de
    aceitar.
    """
    retido = retido_acumulado(contrato)
    liberado = liberado_acumulado(contrato)
    return {
        "retido": retido,
        "liberado": liberado,
        "disponivel": retido - liberado,
        "natureza": contrato.retencao_natureza,
        "condicao": contrato.retencao_condicao_liberacao,
    }


@transaction.atomic
def solicitar_liberacao(*, contrato: ContratoObra, valor: Decimal, data: date,
                        condicao_atendida: str, solicitante,
                        por: str = "") -> dict:
    """Põe na escada o pedido de devolver o que ficou retido.

    **O teto é o saldo, e ele é derivado** (§4.9): não existe coluna de "retido"
    para conferir contra. A soma é feita aqui, na hora, sobre as medições
    aprovadas menos as liberações que já saíram ou estão saindo.

    **A condição é obrigatória.** A cláusula do contrato diz *quando* a retenção
    volta; este texto é onde quem pede declara que aquilo aconteceu. Liberar
    caução sem dizer o que foi cumprido é o achado que uma auditoria de contrato
    registra — e o campo existe justamente para que ele não exista.
    """
    from nucleo import aprovacao as motor

    condicao = (condicao_atendida or "").strip()
    if not condicao:
        raise ValidationError(
            "Declare qual condição do contrato foi atendida para liberar a "
            "retenção — a cláusula deste contrato diz: "
            + (contrato.retencao_condicao_liberacao or "(não preenchida)")
        )
    valor = _dinheiro(Decimal(str(valor)))
    if valor <= 0:
        raise ValidationError("O valor a liberar precisa ser positivo.")

    saldo = retencao_disponivel(contrato)
    if valor > saldo["disponivel"]:
        raise ValidationError(
            f"Só há R$ {saldo['disponivel']} disponíveis para liberação "
            f"(R$ {saldo['retido']} retidos, R$ {saldo['liberado']} já liberados). "
            f"Pedido: R$ {valor}."
        )

    liberacao = LiberacaoRetencao.objects.create(
        tenant_id=contrato.tenant_id,
        contrato=contrato,
        valor=valor,
        data=data,
        condicao_atendida=condicao,
        solicitada_por=por or "",
    )

    fluxo = motor.fluxo_para(liberacao, tenant_id=contrato.tenant_id)
    if fluxo is None:
        _congelar_liberacao(liberacao, aprovada=True)
        return {"estado": "aprovada", "escada": None, "liberacao": liberacao}

    pedido = motor.abrir(
        alvo=liberacao, solicitante=solicitante,
        resumo=(
            f"Liberação de retenção · contrato {contrato.numero} · R$ {valor}"
        ),
        valor=valor,
    )
    liberacao.status = LiberacaoRetencao.Status.EM_APROVACAO
    liberacao.save(update_fields=["status"])
    return {"estado": "em_aprovacao", "escada": pedido.pk, "liberacao": liberacao}


def _congelar_liberacao(liberacao: LiberacaoRetencao, *,
                        aprovada: bool) -> LiberacaoRetencao:
    """Fecha o pedido e, aprovado, devolve o dinheiro pelo ERP.

    Revalida o saldo antes de congelar, pela mesma razão da medição: entre a
    solicitação e o último atesto, outra liberação pode ter sido aprovada.
    """
    if aprovada:
        saldo = retencao_disponivel(liberacao.contrato)
        # A própria liberação está em `liberado` (ela conta como em aprovação),
        # então o disponível já a desconta — somar de volta é o que diz se ela
        # ainda cabe.
        if saldo["disponivel"] < 0:
            raise ValidationError(
                f"A liberação não cabe mais no saldo retido: faltam "
                f"R$ {-saldo['disponivel']}. Outra liberação foi aprovada no "
                f"intervalo."
            )

    liberacao.status = (
        LiberacaoRetencao.Status.APROVADA if aprovada
        else LiberacaoRetencao.Status.REPROVADA
    )
    liberacao.congelada_em = timezone.now()
    campos = ["status", "congelada_em"]

    if aprovada:
        conta_id = _gerar_titulo_de_liberacao(liberacao)
        if conta_id is not None:
            liberacao.conta_pagar_ref = conta_id
            campos.append("conta_pagar_ref")

    liberacao.save(update_fields=campos)
    return liberacao


def _gerar_titulo_de_liberacao(liberacao: LiberacaoRetencao) -> int | None:
    """Título próprio, e não uma baixa na medição antiga.

    A tentação é somar o valor liberado ao título da medição que o reteve — e
    seria errado por dois motivos: aquela conta já pode estar quitada (mexer
    nela reabriria documento fechado, exatamente o que a `RevisaoBaixa` do ERP
    existe para impedir), e a retenção costuma voltar meses depois, num
    vencimento próprio. O extrato do empreiteiro mostra duas entradas porque
    houve dois pagamentos.
    """
    from moduloerp.models import ContaPagar

    contrato = liberacao.contrato
    conta = ContaPagar.objects.create(
        tenant_id=liberacao.tenant_id,
        fornecedor_id=contrato.fornecedor_id,
        empreendimento_id=getattr(contrato.obra, "empreendimento_id", None),
        descricao=(
            f"Liberação de retenção ({contrato.get_retencao_natureza_display()}) · "
            f"contrato {contrato.numero} · {contrato.obra.nome_obra} · "
            f"{liberacao.condicao_atendida[:120]}"
        ),
        valor=liberacao.valor,
        data_emissao=timezone.localdate(),
        data_vencimento=liberacao.data,
    )
    return conta.pk


# --- Retificação e leitura do contrato -------------------------------------


@transaction.atomic
def retificar(*, medicao: Medicao, motivo: str, por: str = "") -> Medicao:
    """Abre a medição que corrige uma congelada (§11.5).

    **Nasce vazia, e é de propósito.** Copiar as linhas da original com sinal
    trocado pareceria conveniência e seria uma armadilha: a retificação quase
    nunca é "estorna tudo" — é "o item 4.2 mediu 120 e eram 95". Uma grade
    pré-preenchida com o estorno completo convida a submeter sem ler, e o que se
    submete aqui vira título a pagar.

    O que a retificadora traz da original é o **período** (é o mesmo que está
    sendo corrigido) e o vínculo `retifica`, que é o que mantém as duas
    legíveis lado a lado — o mesmo desenho do estorno do apontamento.
    """
    if medicao.status != Medicao.Status.APROVADA:
        raise ValidationError(
            "Só medição aprovada se retifica. Rascunho se edita; medição "
            "reprovada ou cancelada já não produz efeito."
        )
    if not (motivo or "").strip():
        raise ValidationError("A retificação exige motivo.")
    ja_existe = Medicao.objects.filter(retifica=medicao).exclude(
        status=Medicao.Status.CANCELADA
    ).first()
    if ja_existe is not None:
        raise ValidationError(
            f"A medição {medicao.numero} já está sendo retificada pela "
            f"medição {ja_existe.numero}."
        )

    contrato = medicao.contrato
    proximo = (
        Medicao.todos.filter(contrato=contrato).aggregate(m=Max("numero"))["m"] or 0
    ) + 1
    return Medicao.objects.create(
        tenant_id=contrato.tenant_id,
        contrato=contrato,
        numero=proximo,
        periodo_inicio=medicao.periodo_inicio,
        periodo_fim=medicao.periodo_fim,
        retifica=medicao,
        retencao_percentual_aplicado=medicao.retencao_percentual_aplicado,
        taxa_administracao_aplicada=medicao.taxa_administracao_aplicada,
        apurada_por=por or "",
        observacao=f"Retifica a medição {medicao.numero}: {motivo}",
    )


def saldo_do_contrato(contrato: ContratoObra) -> dict:
    """O cockpit do contrato — derivado inteiro, sem uma coluna guardada (§4.9).

    É a leitura que abre a tela do contrato: contratado (original, aditivado e
    atual), medido nas três faixas, saldo, retenção, deduções e quantos itens já
    fecharam. Uma passada, para a grade de um contrato de 2.000 linhas não virar
    2.000 consultas.
    """
    original = valor_contratado_original(contrato)
    aditivado = valor_dos_aditivos(contrato)
    contratado = valor_contratado(contrato)

    por_status: dict[str, Decimal] = {}
    deducoes_aprovadas = _ZERO
    estocado_valor = _ZERO
    for medicao in contrato.medicoes.all():
        totais = totais_da_medicao(medicao)
        por_status[medicao.status] = (
            por_status.get(medicao.status, _ZERO) + totais["bruto"]
        )
        if medicao.status == Medicao.Status.APROVADA:
            deducoes_aprovadas += totais["total_deducoes"]

    aprovado = por_status.get(Medicao.Status.APROVADA, _ZERO)
    em_escada = por_status.get(Medicao.Status.EM_APROVACAO, _ZERO)
    rascunho = por_status.get(Medicao.Status.RASCUNHO, _ZERO)

    ja_medido = medido_por_item(contrato)
    estoque = estocado_ate(contrato)
    itens = list(contrato.itens.all())
    atual = contratado_atual_por_item(contrato, itens)
    fechados = 0
    for item in itens:
        contratado_item = atual.get(item.pk, item.quantidade_contratada)
        if ja_medido.get(item.pk, _ZERO) >= contratado_item and contratado_item > 0:
            fechados += 1
        estocado_valor += estoque.get(item.pk, _ZERO) * item.preco_unitario

    abertos = contrato.aditivos.filter(
        status__in=(
            AditivoContrato.Status.RASCUNHO, AditivoContrato.Status.EM_APROVACAO,
        )
    ).count()

    return {
        "contrato_id": contrato.pk,
        "regime": contrato.regime,
        "valor_contratado": contratado,
        "valor_original": original,
        "valor_aditivado": aditivado,
        "medido_aprovado": aprovado,
        "medido_em_aprovacao": em_escada,
        "medido_rascunho": rascunho,
        "deducoes_aprovadas": _dinheiro(deducoes_aprovadas),
        "material_estocado": _dinheiro(estocado_valor),
        # O saldo é contra o que ocupa o contrato — aprovado + na escada. O
        # rascunho fica de fora e aparece à parte: ele é intenção, e somá-lo
        # mostraria ao gestor um saldo que some quando ele abre uma medição
        # para estudar.
        "saldo": contratado - aprovado - em_escada,
        "retencao": retencao_disponivel(contrato),
        "itens": len(itens),
        "itens_fechados": fechados,
        "medicoes": contrato.medicoes.count(),
        "aditivos": contrato.aditivos.filter(
            status=AditivoContrato.Status.APROVADO,
        ).count(),
        "aditivos_abertos": abertos,
        "periodo_sugerido": sugerir_periodo(contrato),
    }


def planilha_editavel(contrato: ContratoObra) -> tuple[bool, str]:
    """A planilha contratual ainda aceita edição direta? E, se não, por quê.

    **A régua não é o status do contrato — é se alguém já mediu contra ela.**
    Esta função nasceu errada e foi corrigida no mesmo dia: a primeira escrita
    fechava a planilha assim que o contrato saía de rascunho, e isso criou um
    beco sem saída que o dono encontrou em minutos — contrato vigente **sem
    itens** ficava impossível de preencher, com a tela dizendo *"cadastre os
    itens para poder medir"* e nenhum caminho para fazê-lo. A saída pelo aditivo
    seria pior que o problema: item nascido de aditivo tem contratado original
    zero, e a planilha inteira entraria no contrato como se fosse acréscimo.

    O que o aditivo existe para proteger é o que **já foi usado**: a quantidade
    contra a qual alguém mediu, e que pode ter virado pagamento. Antes da
    primeira medição não há nada a preservar — nenhum número foi calculado sobre
    ela, nenhum título saiu. Depois, mudar a planilha reescreveria o denominador
    de um documento assinado, e aí o caminho é o aditivo, que guarda o que
    mudou, o porquê e quem autorizou.

    Medição **cancelada ou reprovada não fecha a planilha**: ela não ocupa saldo
    e não produziu efeito — é a mesma régua do `_EM_VOO` que governa o
    acumulado.
    """
    if contrato.status in (
        ContratoObra.Status.ENCERRADO, ContratoObra.Status.CANCELADO,
    ):
        return False, (
            f"O contrato está {contrato.get_status_display().lower()} — a "
            f"planilha contratual não muda mais."
        )
    em_voo = contrato.medicoes.filter(status__in=_EM_VOO).count()
    if em_voo:
        return False, (
            f"Este contrato já tem {em_voo} medição(ões) aprovada(s) ou em "
            f"aprovação, calculadas sobre esta planilha. Mudar quantidade, "
            f"preço ou incluir item agora é **aditivo** — é ele que guarda o "
            f"que mudou, o porquê e quem autorizou, e que preserva o contratado "
            f"original."
        )
    return True, ""


def validar_teto_de_itens(contrato: ContratoObra, *, acrescentando: int = 1) -> None:
    """O teto do `planos.py` aplicado onde o item nasce."""
    atual = contrato.itens.count()
    if atual + acrescentando > PDCA_TETO_ITENS_POR_CONTRATO:
        raise ValidationError(
            f"O contrato já tem {_milhar(atual)} itens e o teto do seu plano é "
            f"{_milhar(PDCA_TETO_ITENS_POR_CONTRATO)}."
        )
