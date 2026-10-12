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

import re
import time
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Max, Q, Sum
from django.utils import timezone

from payment.planos import (
    PDCA_CPM_SEGUNDOS,
    PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_PONTOS_CURVA_S,
    PDCA_PROFUNDIDADE_MAXIMA_LOCAL,
    PDCA_PROFUNDIDADE_MAXIMA_WBS,
    PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
    PDCA_TETO_LIGACOES_EXPANDIDAS,
    PDCA_TETO_CAUSAS_POR_TENANT,
    PDCA_TETO_CONFLITOS_REPORTADOS,
    PDCA_TETO_LINHAS_DE_BALANCO,
    PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO,
    PDCA_TETO_LOCAIS_POR_RITMO,
    PDCA_TETO_CPM_SINCRONO,
    PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO,
    PDCA_TETO_DEDUCOES_POR_MEDICAO,
    PDCA_TETO_ITENS_POR_ADITIVO,
    PDCA_TETO_ITENS_POR_CONTRATO,
    PDCA_TETO_ITENS_POR_PROGRAMACAO,
    PDCA_TETO_LINHAS_POR_LOTE,
    PDCA_TETO_LINHAS_POR_MEDICAO,
    PDCA_TETO_LOCAIS_POR_GERACAO,
    PDCA_TETO_LOCAIS_POR_OBRA,
    PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA,
    PDCA_TETO_SEMANAS_PPC,
    PDCA_TETO_VERSOES_POR_CRONOGRAMA,
    PDCA_TETO_ACOES_POR_NC,
    PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO,
    PDCA_TETO_MODELOS_POR_TENANT,
    PDCA_TETO_NCS_ABERTAS_POR_OBRA,
    PDCA_TETO_ANEXOS_POR_OCORRENCIA,
    PDCA_TETO_OCORRENCIAS_NA_FILA,
    PDCA_TETO_PARTICIPANTES_POR_DDS,
    PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA,
    PDCA_TETO_LINHAS_POR_FRENTE,
    PDCA_TETO_OBRAS_NA_CARTEIRA,
    PDCA_TETO_RESULTADOS_POR_ESPECIE,
    PDCA_TETO_CONTRATOS_NO_POSTO,
)

from .models import (
    AcaoAditivo, AditivoContrato, ApontamentoAvanco, Atividade,
    CalendarioTrabalho, CausaNaoCumprimento, ContratoObra, Cronograma,
    DeducaoMedicao, DominioVerificacao, GravidadeNC, ItemModeloVerificacao,
    ItemVerificacao, ModeloVerificacao, NaoConformidade, PlanoAcao,
    ResultadoItem, Verificacao, VerificacaoEficacia,
    ExcecaoCalendario, ItemAditivo, ItemContrato, ItemMedicao, ItemProgramacao,
    LadoContrato, LiberacaoRetencao, LocalObra, Medicao, NivelLocal, OrigemCusto,
    Precedencia, ProgramacaoSemanal, RegimeContrato, Restricao, TipoDeducao,
    TipoRestricao,
    AnexoOcorrencia, ClassificacaoOcorrencia, DialogoSeguranca, Ocorrencia,
    ParticipanteDDS, TipoCAT, TipoOcorrencia,
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


def localidade_dos_feriados(calendario: CalendarioTrabalho, obra=None) -> dict:
    """De **onde** são os feriados deste expediente: `{uf, ibge, cidade, fonte}`.

    O UF/IBGE digitado no expediente vence. Sem eles, vale **o lugar da obra** —
    a do próprio expediente ou, para o expediente da empresa, a do plano que o
    usa —, resolvido pelo endereço como a Agenda resolve (`nucleo.geo`). Era o
    defeito do teste do dono (09/10/2026): o expediente "respeita feriados" mas
    sem UF/IBGE só via o nacional, e a obra em Nazaré/BA perdia o estadual e o
    municipal que a Agenda mostrava. Sem endereço resolvível, só o nacional —
    afirmar feriado de um lugar que não se sabe seria inventar dia parado.
    """
    if calendario.uf or calendario.ibge:
        return {"uf": calendario.uf, "ibge": calendario.ibge, "cidade": "", "fonte": "expediente"}
    obra = getattr(calendario, "obra", None) or obra
    endereco = (getattr(obra, "endereco", "") or "").strip()
    if endereco:
        from nucleo import geo

        achado = geo.resolver(endereco=endereco) or {}
        if achado.get("uf"):
            return {
                "uf": achado.get("uf", ""), "ibge": achado.get("ibge", ""),
                "cidade": achado.get("cidade", ""), "fonte": "obra",
            }
    return {"uf": "", "ibge": "", "cidade": "", "fonte": "nacional"}


def feriados_do_periodo(calendario: CalendarioTrabalho, inicio: date, fim: date,
                        *, obra=None) -> dict:
    """`{data: nome}` no período, no lugar do expediente (ou da obra).

    Os mesmos da Agenda (`modulocalendar.dias_uteis.feriados_da_localidade`):
    lei calculada mesmo com a tabela vazia, município publicado ou projetado.
    """
    if not calendario.considera_feriados:
        return {}
    from modulocalendar.dias_uteis import feriados_da_localidade

    lugar = localidade_dos_feriados(calendario, obra)
    return feriados_da_localidade(inicio, fim, uf=lugar["uf"], ibge=lugar["ibge"])


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


def expedientes_do_plano(cronograma: Cronograma, atividades) -> dict:
    """Os dias em que **não** se trabalha, para o Gantt desenhar o corte.

    O CPM já pula sábado, domingo, feriado e recesso; a barra é que não
    mostrava. Vai ao cliente a regra da semana de cada expediente em uso (o do
    plano e os que alguma atividade escolheu) e as datas avulsas — feriados da
    localidade e exceções — numa janela folgada em volta do plano. O cliente
    resolve "este dia é útil?" com a mesma precedência do `eh_dia_util`:
    exceção > feriado > regra da semana. Os feriados são os do lugar da obra
    (`localidade_dos_feriados`), os mesmos da Agenda.
    """
    ids = {cronograma.calendario_id} | {a.calendario_id for a in atividades}
    ids.discard(None)
    datas = [d for a in atividades for d in (a.inicio_cedo, a.termino_cedo) if d]
    if cronograma.data_inicio:
        datas.append(cronograma.data_inicio)
    resposta = {
        "calendario_do_plano": cronograma.calendario_id,
        "calendarios": {},
    }
    if not ids or not datas:
        return resposta
    # Folga dos dois lados: o Gantt deixa arrastar a barra para fora do plano.
    inicio = min(datas) - timedelta(days=60)
    fim = max(datas) + timedelta(days=180)
    for cal in CalendarioTrabalho.objects.select_related("obra").filter(pk__in=ids):
        lugar = localidade_dos_feriados(cal, cronograma.obra) if cal.considera_feriados else None
        resposta["calendarios"][str(cal.pk)] = {
            "nome": cal.nome,
            "considera_feriados": cal.considera_feriados,
            "localidade": lugar,
            "dias_da_semana": list(cal.dias_da_semana),
            "feriados": [
                {"data": d, "nome": nome}
                for d, nome in sorted(
                    feriados_do_periodo(cal, inicio, fim, obra=cronograma.obra).items())
            ],
            "excecoes": [
                {"data": e.data, "trabalha": e.trabalha, "motivo": e.motivo}
                for e in ExcecaoCalendario.objects.filter(
                    calendario=cal, data__gte=inicio, data__lte=fim,
                ).order_by("data")
            ],
        }
    return resposta


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

    def __init__(self, calendario: CalendarioTrabalho, ancora: date, obra=None):
        self.calendario = calendario
        self.ancora = ancora
        self.obra = obra
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
        self._feriados.update(feriados_do_periodo(self.calendario, inicio, fim, obra=self.obra))
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

    def porque_muda(self, dia: date) -> str | None:
        """Por que este dia foge da regra da semana — o feriado ou a exceção.
        `None` quando quem decide é a própria semana (sábado, domingo)."""
        self._carregar_ate(dia)
        if dia in self._excecoes:
            return "exceção: trabalha" if self._excecoes[dia] else "exceção: parado"
        return self._feriados.get(dia)


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
    return {cid: CalendarioEmMemoria(cal, ancora, obra=cronograma.obra) for cid, cal in usados.items()}


def datas_fora_do_expediente(cronograma: Cronograma, atividades: list[Atividade]) -> dict:
    """As barras que o expediente **de hoje** já não sustenta.

    O CPM grava as datas; o expediente pode mudar depois — o feriado que entrou,
    o recesso, o mutirão de sábado. No rascunho o próximo recálculo resolve; na
    versão vigente ou substituída as datas estão congeladas, e o Gantt seguia
    contando o 12/10 como dia de obra sem dizer nada (achado do dono,
    09/10/2026).

    A conferência é a invariante do próprio CPM: logo depois do cálculo, toda
    folha tem **exatamente** `duracao_dias` dias úteis entre início e término.
    Se hoje a conta dá outra, o expediente mudou dentro daquela barra — e os
    dias que fogem da regra da semana dizem qual feriado ou exceção foi.
    """
    vazio = {"total": 0, "atividades": []}
    if cronograma.calculado_em is None:
        return vazio
    com_filhos = {a.pai_id for a in atividades if a.pai_id}
    folhas = [
        a for a in atividades
        if a.atividade_id not in com_filhos and not a.eh_marco
        and a.inicio_cedo and a.termino_cedo and a.duracao_dias
        and (a.calendario_id or cronograma.calendario_id)
    ]
    if not folhas:
        return vazio
    try:
        calendarios = _calendarios_do_cronograma(cronograma, folhas)
        achadas = []
        for a in folhas:
            cal = calendarios[a.calendario_id or cronograma.calendario_id]
            uteis_hoje = cal.entre(a.inicio_cedo, a.termino_cedo)
            if uteis_hoje == a.duracao_dias:
                continue
            dias = []
            dia = a.inicio_cedo
            while dia <= a.termino_cedo:
                motivo = cal.porque_muda(dia)
                if motivo:
                    dias.append({"data": dia, "motivo": motivo})
                dia += timedelta(days=1)
            achadas.append({
                "atividade": a.atividade_id, "codigo": a.codigo, "nome": a.nome,
                "duracao_dias": a.duracao_dias, "uteis_hoje": uteis_hoje, "dias": dias,
            })
    except ValidationError:
        # Expediente sem dia útil: o recálculo já diz isso com endereço.
        return vazio
    return {"total": len(achadas), "atividades": achadas}


class LigacaoEntreFolhas:
    """Uma seta do grafo do CPM — a gravada, ou uma das que a ligação de fase
    produz. Tem a mesma cara de `Precedencia` para o CPM não distinguir as duas;
    as expandidas levam id negativo, que nunca colide com o do banco."""

    __slots__ = ("precedencia_id", "origem_id", "destino_id", "tipo", "atraso_dias")

    def __init__(self, precedencia_id, origem_id, destino_id, tipo, atraso_dias):
        self.precedencia_id = precedencia_id
        self.origem_id = origem_id
        self.destino_id = destino_id
        self.tipo = tipo
        self.atraso_dias = atraso_dias


def ligacoes_das_folhas(atividades: list[Atividade], precedencias) -> list:
    """A rede como o CPM a enxerga: só setas entre folhas.

    **A ligação de fase** (decisão do dono, 09/10/2026: *"dependências de fases"*)
    é a seta que sai de uma etapa ou chega nela — "a alvenaria começa depois que
    a estrutura termina". No grafo ela vira setas entre as folhas das duas, com a
    semântica do MS Project para tarefa-resumo:

    - **sai do término** (FS, FF): de **todas** as folhas da origem — a etapa só
      termina quando a última termina;
    - **sai do início** (SS, SF): das folhas que **abrem** a etapa (nenhuma
      predecessora dentro dela) — são elas que dão a data de começo;
    - **chega no início** (FS, SS): em **todas** as folhas do destino — nenhuma
      começa antes de a fase anterior liberar;
    - **chega no término** (FF, SF): nas folhas que **fecham** o destino (nenhuma
      sucessora dentro dele).

    *Limite declarado:* "abre" e "fecha" se leem pela rede gravada, não pelas
    datas — uma folha sem predecessora interna mas com restrição de data tardia
    continua contando como abertura.
    """
    filhos: dict[int | None, list[int]] = {}
    for a in atividades:
        filhos.setdefault(a.pai_id, []).append(a.atividade_id)
    ids = {a.atividade_id for a in atividades}

    folhas_de: dict[int, list[int]] = {}

    def folhas(no: int) -> list[int]:
        if no in folhas_de:
            return folhas_de[no]
        pilha, saida = [no], []
        while pilha:
            atual = pilha.pop()
            debaixo = filhos.get(atual)
            if debaixo:
                pilha.extend(debaixo)
            else:
                saida.append(atual)
        folhas_de[no] = saida
        return saida

    precedencias = [p for p in precedencias if p.origem_id in ids and p.destino_id in ids]

    def internas(no: int):
        dentro = set(folhas(no))
        return [
            p for p in precedencias
            if set(folhas(p.origem_id)) <= dentro and set(folhas(p.destino_id)) <= dentro
        ]

    def abertura(no: int) -> list[int]:
        dentro = folhas(no)
        presas = {f for p in internas(no) for f in folhas(p.destino_id)}
        return [f for f in dentro if f not in presas] or dentro

    def fechamento(no: int) -> list[int]:
        dentro = folhas(no)
        presas = {f for p in internas(no) for f in folhas(p.origem_id)}
        return [f for f in dentro if f not in presas] or dentro

    saida: list = []
    proximo = -1
    for p in precedencias:
        origem_folha = not filhos.get(p.origem_id)
        destino_folha = not filhos.get(p.destino_id)
        if origem_folha and destino_folha:
            saida.append(p)
            continue
        sai_do_fim = p.tipo in (Precedencia.Tipo.FS, Precedencia.Tipo.FF)
        chega_no_inicio = p.tipo in (Precedencia.Tipo.FS, Precedencia.Tipo.SS)
        origens = folhas(p.origem_id) if sai_do_fim else abertura(p.origem_id)
        destinos = folhas(p.destino_id) if chega_no_inicio else fechamento(p.destino_id)
        for o in origens:
            for d in destinos:
                if o == d:
                    continue
                saida.append(LigacaoEntreFolhas(proximo, o, d, p.tipo, p.atraso_dias))
                proximo -= 1
        if len(saida) > PDCA_TETO_LIGACOES_EXPANDIDAS:
            raise ValidationError(
                f"As ligações de fase viram mais de {PDCA_TETO_LIGACOES_EXPANDIDAS} setas "
                "entre atividades. Ligue etapas menores, ou as atividades que de fato "
                "seguram a seguinte."
            )
    return saida


def verificar_rede(cronograma: Cronograma, *, nova=None, ignorar: int | None = None) -> None:
    """Recusa a ligação que fecharia um ciclo — conferido no grafo **expandido**,
    porque com ligação de fase o laço pode passar por dentro de uma etapa sem
    nenhuma seta gravada fechá-lo diretamente."""
    atividades = list(cronograma.atividades.only("atividade_id", "pai_id", "codigo", "nome"))
    gravadas = [
        p for p in Precedencia.objects.filter(origem__cronograma=cronograma)
        .only("precedencia_id", "origem_id", "destino_id", "tipo", "atraso_dias")
        if p.pk != ignorar
    ]
    if nova is not None:
        gravadas.append(nova)
    com_filhos = {a.pai_id for a in atividades if a.pai_id}
    folhas = [a for a in atividades if a.atividade_id not in com_filhos]
    _ordem_topologica(folhas, ligacoes_das_folhas(atividades, gravadas))


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
    depois, de baixo para cima. A ligação **de fase** — a seta que sai de uma
    etapa ou chega nela — é expandida antes, em setas entre folhas
    (`ligacoes_das_folhas`); o ciclo e a ligação de uma etapa com o que está
    dentro dela são recusados na escrita (serializer), onde o erro tem endereço.

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

    ligacoes = ligacoes_das_folhas(
        atividades,
        list(Precedencia.objects.filter(
            origem__cronograma=cronograma
        ).only("precedencia_id", "origem_id", "destino_id", "tipo", "atraso_dias")),
    )

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
        # As datas previstas das etapas da obra são as das raízes.
        from . import etapas
        if etapas.cronograma_da_obra(cronograma):
            etapas.agendar(cronograma.obra_id, cronograma.tenant_id)

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
        anteriores = list(
            Cronograma.objects
            .filter(tenant_id=cronograma.tenant_id, obra_id=cronograma.obra_id,
                    status=Cronograma.Status.VIGENTE)
            .exclude(pk=cronograma.pk)
            .values_list("pk", flat=True)
        )
        _levar_restricoes_abertas(anteriores, cronograma)
        (Cronograma.objects
         .filter(pk__in=anteriores)
         .update(status=Cronograma.Status.SUBSTITUIDO))
        cronograma.status = Cronograma.Status.VIGENTE
        cronograma.publicado_em = timezone.now()
        cronograma.publicado_por = (por or "")[:150]
        cronograma.save(update_fields=["status", "publicado_em", "publicado_por"])

    return resultado


def _levar_restricoes_abertas(de_cronogramas: list[int], para: Cronograma) -> int:
    """As travas **abertas** do plano que sai passam ao plano que entra.

    A restrição pende da atividade, e o replanejamento copia a árvore com ids
    novos: sem isto, publicar a v2 deixava o make-ready inteiro preso à v1 —
    a semana montada sobre a v2 não via trava nenhuma e comprometia o que
    estava travado. O pareamento é **pelo código da EAP**, o mesmo com que o
    avanço atravessa as versões. A resolvida fica onde nasceu (é história
    daquela versão); a aberta sem gêmea na versão nova também fica — continua
    na esteira da obra, e quem a resolve é quem sabe que ela morreu.
    """
    if not de_cronogramas:
        return 0
    gemeas = dict(
        Atividade.objects.filter(cronograma=para).values_list("codigo", "atividade_id")
    )
    levadas = 0
    for r in (Restricao.objects
              .filter(atividade__cronograma_id__in=de_cronogramas,
                      status=Restricao.Status.ABERTA)
              .select_related("atividade")):
        destino = gemeas.get(r.atividade.codigo) if r.atividade.codigo else None
        if destino:
            r.atividade_id = destino
            r.save(update_fields=["atividade"])
            levadas += 1
    return levadas


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

    #: **Um rascunho por vez.** A tela abria o vigente depois de replanejar, a
    #: pessoa não via a versão nova, replanejava de novo — e a obra juntava três
    #: rascunhos órfãos, cada um cópia do vigente, nenhum com o trabalho do
    #: outro. Quem já tem um rascunho continua nele (ou o descarta).
    em_aberto = (Cronograma.objects
                 .filter(tenant_id=cronograma.tenant_id, obra_id=cronograma.obra_id,
                         status=Cronograma.Status.RASCUNHO, eh_modelo=False,
                         versao__gt=cronograma.versao)
                 .order_by("-versao").first())
    if em_aberto is not None:
        raise ValidationError(
            f"Já existe a versão {em_aberto.versao} em rascunho para esta obra. "
            f"Continue nela — ou descarte-a — antes de abrir outra."
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
            orcamento_origem_id=cronograma.orcamento_origem_id,
            cronograma_orcamento_em=cronograma.cronograma_orcamento_em,
        )

        copiar_estrutura(cronograma, nova, manter_vinculos_da_obra=True)

    _calcular_se_der(nova)
    return nova


def _calcular_se_der(cronograma: Cronograma) -> None:
    """A cópia nasce **com datas**. Sem isto a versão nova abria com o Gantt
    vazio e só ganhava barras no primeiro gesto que recalculasse — o dono viu o
    plano "zerado antes de alguns tipos de alteração" (09/10/2026). Se o CPM
    recusa (sem expediente, rede grande demais), a versão nasce mesmo assim e a
    tela diz por que o prazo não foi calculado, como diria em qualquer edição."""
    try:
        calcular_cpm(cronograma)
    except ValidationError:
        pass


def copiar_estrutura(origem: Cronograma, destino: Cronograma, *,
                     manter_vinculos_da_obra: bool,
                     anexando: bool = False) -> dict[int, int]:
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

    `anexando=True` é o terceiro cliente (`anexar_modelo`): o destino já tem
    linhas, então a cópia nasce com código temporário e as raízes depois das
    que já existem — quem chama renumera no fim.

    Devolve o mapa `id antigo -> id novo`, que é o que a rede precisa para ser
    religada.
    """
    antigas = list(origem.atividades.all().order_by("profundidade", "atividade_id"))
    traducao: dict[int, int] = {}
    deslocamento = 0
    if anexando:
        maior = destino.atividades.filter(pai__isnull=True).aggregate(m=Max("ordem"))["m"]
        deslocamento = 0 if maior is None else maior + 1
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
            codigo=_temporario() if anexando else velha.codigo, nome=velha.nome,
            ordem=velha.ordem + (deslocamento if anexando and not velha.pai_id else 0),
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
            peso_do_orcamento=velha.peso_do_orcamento and manter_vinculos_da_obra,
            antecedencia_compra_dias=velha.antecedencia_compra_dias,
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

    # O material informado na atividade é parte do plano: vai junto.
    from .models import MaterialDaAtividade

    MaterialDaAtividade.objects.bulk_create([
        MaterialDaAtividade(
            tenant_id=destino.tenant_id, atividade_id=traducao[m.atividade_id],
            item_id=m.item_id, descricao=m.descricao, unidade=m.unidade,
            categoria=m.categoria, quantidade=m.quantidade, custo_unitario=m.custo_unitario,
        )
        for m in MaterialDaAtividade.objects.filter(atividade__cronograma=origem)
        if m.atividade_id in traducao
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
        # A etapa que veio do cronograma do orçamento vale o que a etapa vale lá.
        return (atividade.peso_informado, "orcado" if atividade.peso_do_orcamento else "informado")
    return (None, "")


def peso_do_compromisso(atividade: Atividade) -> tuple[Decimal | None, str]:
    """O peso com que um **cartão da semana** entra no PPC ponderado (§12.3).

    É a escada do `peso_de` com **um degrau a mais no fim**: a duração. A razão
    de o degrau existir aqui e não lá é que as duas contas respondem a perguntas
    diferentes. O avanço do cronograma pergunta *quanto da obra já está feito*, e
    ali duração seria régua errada — semana de espera de cura de concreto não é
    obra feita. O PPC pergunta *quanto do que a equipe assumiu para esta semana
    saiu*, e aí duração é a régua de esforço que **toda** obra tem, mesmo a que
    nunca vinculou uma atividade ao orçamento.

    A ordem é a do dono *(15/09/2026)*: o peso sai do planejamento, e o
    planejamento o tira **do orçamento** — que é onde mora o físico-financeiro —
    ou **do tempo que o planejador digitou**.

      1. `orcado`    — o `ItemOrcado` vinculado, pelo `total_com_bdi`;
      2. `informado` — o `peso_informado` que o planejador pôs na atividade;
      3. `duracao`   — os dias úteis da atividade.

    `(None, "")` quando nenhum degrau responde — o marco, que tem duração zero
    por definição, é o caso comum. **Nulo, e não zero**: zero faria o cartão
    existir no denominador valendo nada, e um serviço assumido que vale nada é
    mentira mais cara do que um serviço sem régua. Quem não tem peso é contado à
    parte na leitura (`sem_peso`), como as folhas sem peso do cronograma.
    """
    valor, origem = peso_de(atividade)
    if valor is not None and valor > 0:
        return (valor, origem)
    if atividade.duracao_dias:
        return (Decimal(atividade.duracao_dias), "duracao")
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

    _calcular_se_der(novo)
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
# 6b. A montagem dentro do posto — inserir, mover, colar, importar, orçamento
# ---------------------------------------------------------------------------
#
# *Decisão do dono, 09/10/2026:* **"hoje só consigo criar tarefa e mais nada.
# Quero fazer tudo."** — começar do orçamento, de um modelo, colando do Excel ou
# do MS Project, ou digitando; arrastar para qualquer lugar; ligar e desligar
# dependências no desenho.
#
# Toda operação daqui cria ou move linhas com **código temporário** e termina
# numa `renumerar_eap`: o código é posição na árvore, e calculá-lo à mão em cada
# gesto é como `1.2` acaba aparecendo duas vezes. A renumeração já tem as duas
# passadas que fazem a troca caber na trava de unicidade.


def _temporario() -> str:
    from uuid import uuid4
    return f"~{uuid4().hex[:16]}"


def _exigir_rascunho(cronograma: Cronograma) -> None:
    if not cronograma.editavel:
        raise ValidationError(
            "Este cronograma não é mais rascunho. Para mudar o plano, replaneje."
        )


def _altura(atividade: Atividade) -> int:
    """Quantos níveis a subárvore ocupa, contando a própria atividade."""
    filhos = list(atividade.filhos.all())
    return 1 + max((_altura(f) for f in filhos), default=0)


def _reprofundar(no: Atividade) -> None:
    for filho in no.filhos.all():
        filho.profundidade = no.profundidade + 1
        filho.save(update_fields=["profundidade"])
        _reprofundar(filho)


def mover_atividade(atividade: Atividade, *, pai: Atividade | None,
                    posicao: int | None = None) -> Atividade:
    """Leva a atividade (com tudo o que está dentro) para debaixo de `pai`, na
    `posicao` entre as irmãs (fim, se omitida) — o gesto de arrastar a linha, de
    recuar com Tab e de subir com Alt+↑. Termina renumerando a EAP."""
    cronograma = atividade.cronograma
    _exigir_rascunho(cronograma)
    if pai is not None:
        if pai.cronograma_id != cronograma.pk:
            raise ValidationError("A atividade de destino é de outro cronograma.")
        if pai.eh_marco:
            raise ValidationError("Um marco é um instante e não agrupa atividades.")
        no = pai
        while no is not None:
            if no.pk == atividade.pk:
                raise ValidationError(
                    "Uma atividade não pode ir para dentro dela mesma."
                )
            no = no.pai
    validar_profundidade_wbs(pai, quantos_niveis=_altura(atividade))

    with transaction.atomic():
        antigo_pai_id = atividade.pai_id
        irmas = list(
            cronograma.atividades.filter(pai=pai).exclude(pk=atividade.pk)
            .order_by("ordem", "codigo", "atividade_id")
        )
        if posicao is None or posicao > len(irmas):
            posicao = len(irmas)
        irmas.insert(max(posicao, 0), atividade)
        for indice, irma in enumerate(irmas):
            if irma.pk != atividade.pk and irma.ordem != indice:
                Atividade.objects.filter(pk=irma.pk).update(ordem=indice)
        atividade.pai = pai
        atividade.ordem = irmas.index(atividade)
        atividade.profundidade = 1 if pai is None else pai.profundidade + 1
        atividade.save(update_fields=["pai", "ordem", "profundidade", "atualizado_em"])
        _reprofundar(atividade)

        # O pai que ficou sem filhos volta a ser folha — e folha precisa de duração.
        if antigo_pai_id and antigo_pai_id != getattr(pai, "pk", None):
            antigo = Atividade.objects.get(pk=antigo_pai_id)
            if (not antigo.filhos.exists() and not antigo.eh_marco
                    and not antigo.duracao_dias):
                antigo.duracao_dias = 1
                antigo.save(update_fields=["duracao_dias"])

        renumerar_eap(cronograma)
    atividade.refresh_from_db()
    return atividade


def inserir_atividade(cronograma: Cronograma, *, pai: Atividade | None,
                      depois_de: Atividade | None = None, nome: str,
                      duracao_dias: int | None = None, eh_marco: bool = False,
                      etapa_id: int | None = None) -> Atividade:
    """Cria uma linha **na posição** — logo abaixo de `depois_de`, ou no fim de
    `pai`. É o Enter da grade: a linha nova nasce onde o olho está."""
    _exigir_rascunho(cronograma)
    validar_teto_de_atividades(cronograma)
    validar_profundidade_wbs(pai)
    if pai is not None and pai.eh_marco:
        raise ValidationError("Um marco é um instante e não agrupa atividades.")
    if depois_de is not None and depois_de.pai_id != getattr(pai, "pk", None):
        raise ValidationError("A linha de referência não está sob o mesmo pai.")
    nome = (nome or "").strip()[:200] or ("Novo marco" if eh_marco else "Nova atividade")
    if not eh_marco and (duracao_dias is None or duracao_dias < 1):
        duracao_dias = 1

    with transaction.atomic():
        nova = Atividade.objects.create(
            tenant_id=cronograma.tenant_id, cronograma=cronograma, pai=pai,
            codigo=_temporario(), nome=nome, ordem=0,
            profundidade=1 if pai is None else pai.profundidade + 1,
            duracao_dias=None if eh_marco else duracao_dias, eh_marco=eh_marco,
            etapa_id=etapa_id,
        )
        irmas = list(
            cronograma.atividades.filter(pai=pai).exclude(pk=nova.pk)
            .order_by("ordem", "codigo", "atividade_id")
        )
        posicao = len(irmas)
        if depois_de is not None:
            for indice, irma in enumerate(irmas):
                if irma.pk == depois_de.pk:
                    posicao = indice + 1
                    break
        irmas.insert(posicao, nova)
        for indice, irma in enumerate(irmas):
            if irma.ordem != indice:
                Atividade.objects.filter(pk=irma.pk).update(ordem=indice)
        renumerar_eap(cronograma)
    nova.refresh_from_db()
    return nova


#: MS Project em português escreve os tipos como TI/II/TT/IT.
_TIPO_EM_PORTUGUES = {"TI": "FS", "II": "SS", "TT": "FF", "IT": "SF"}

_PREDECESSORA = re.compile(
    r"^\s*(?P<ref>[^\s;,+]+?)\s*(?P<tipo>FS|SS|FF|SF|TI|II|TT|IT)?\s*"
    r"(?:(?P<lag>[+-]\s*\d+)\s*(?:d|du|dias?|ed)?)?\s*$",
    re.IGNORECASE,
)


def ler_predecessoras(texto: str) -> list[tuple[str, str, int]]:
    """`"1.2FS+3d; 1.4SS"` → `[("1.2", "FS", 3), ("1.4", "SS", 0)]`.

    Aceita a grafia do MS Project em inglês e em português (`TI+2 dias`), com
    `;` ou `,` entre as ligações. O que não se lê volta como referência com tipo
    vazio, para quem chamou dizer **qual** pedaço não entendeu.
    """
    saida = []
    for pedaco in re.split(r"[;,]", texto or ""):
        if not pedaco.strip():
            continue
        casou = _PREDECESSORA.match(pedaco)
        if not casou:
            saida.append((pedaco.strip(), "", 0))
            continue
        tipo = (casou.group("tipo") or "FS").upper()
        tipo = _TIPO_EM_PORTUGUES.get(tipo, tipo)
        lag = int(casou.group("lag").replace(" ", "")) if casou.group("lag") else 0
        saida.append((casou.group("ref"), tipo, lag))
    return saida


def importar_linhas(cronograma: Cronograma, linhas: list[dict], *,
                    referencia: str = "codigo") -> dict:
    """Cria muitas linhas de uma vez, com hierarquia e rede — o gesto de colar
    uma planilha do Excel e o de abrir um XML do MS Project.

    Cada linha traz `nome` e, opcionais, `nivel` (1 é a raiz; sem ele, o nível
    sai dos pontos do `codigo`), `codigo` (o do arquivo, só para as
    predecessoras se acharem), `duracao_dias`, `eh_marco`, `predecessoras`
    (`"1.2FS+3d; 1.4"`), `nao_comecar_antes_de` e `peso`.

    `referencia="linha"` faz as predecessoras apontarem para o **número da
    linha** colada (a coluna "Predecessoras" do MS Project usa o Id da linha,
    não o código da EAP). As linhas entram **no fim** do plano, e a EAP é
    renumerada no fim — os códigos colados não sobrevivem, as ligações sim.
    Tudo numa transação: ciclo ou linha inválida desfaz o bloco inteiro.
    """
    _exigir_rascunho(cronograma)
    if not linhas:
        raise ValidationError("Nenhuma linha foi enviada.")
    validar_teto_de_atividades(cronograma, acrescentando=len(linhas))

    avisos: list[str] = []
    existentes = {a.codigo: a for a in cronograma.atividades.all()}
    ordem_raiz = (cronograma.atividades.filter(pai__isnull=True)
                  .aggregate(m=Max("ordem"))["m"])
    ordem_raiz = -1 if ordem_raiz is None else ordem_raiz

    criadas: list[tuple[Atividade, dict]] = []
    por_codigo: dict[str, Atividade] = {}
    pilha: list[tuple[int, Atividade]] = []
    contagem_filhos: dict[int, int] = {}

    with transaction.atomic():
        for numero, linha in enumerate(linhas, start=1):
            nome = str(linha.get("nome") or "").strip()[:200]
            if not nome:
                avisos.append(f"Linha {numero}: sem nome, ficou de fora.")
                continue
            codigo_original = str(linha.get("codigo") or "").strip()
            nivel = linha.get("nivel")
            try:
                nivel = int(nivel) if nivel not in (None, "") else None
            except (TypeError, ValueError):
                nivel = None
            if nivel is None:
                nivel = codigo_original.count(".") + 1 if codigo_original else 1
            nivel = max(1, nivel)
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            pai = pilha[-1][1] if pilha else None
            nivel = (pilha[-1][0] + 1) if pilha else 1
            if nivel > PDCA_PROFUNDIDADE_MAXIMA_WBS:
                raise ValidationError(
                    f"Linha {numero} ('{nome}'): a WBS vai até "
                    f"{PDCA_PROFUNDIDADE_MAXIMA_WBS} níveis."
                )

            eh_marco = bool(linha.get("eh_marco"))
            duracao = linha.get("duracao_dias")
            try:
                duracao = int(round(float(str(duracao).replace(",", ".")))) \
                    if duracao not in (None, "") else None
            except (TypeError, ValueError):
                avisos.append(f"Linha {numero}: duração '{duracao}' não é número.")
                duracao = None
            if duracao == 0 and not eh_marco and linha.get("eh_marco") is None:
                eh_marco = True  # duração zero é marco, como no MS Project
            inicio_minimo = linha.get("nao_comecar_antes_de") or None
            if inicio_minimo:
                try:
                    inicio_minimo = date.fromisoformat(str(inicio_minimo)[:10])
                except ValueError:
                    avisos.append(f"Linha {numero}: data '{inicio_minimo}' ignorada.")
                    inicio_minimo = None
            peso = linha.get("peso")
            try:
                peso = Decimal(str(peso).replace(",", ".")) if peso not in (None, "") else None
            except Exception:
                avisos.append(f"Linha {numero}: peso '{peso}' ignorado.")
                peso = None

            if pai is None:
                ordem_raiz += 1
                ordem = ordem_raiz
            else:
                ordem = contagem_filhos.get(pai.pk, 0)
                contagem_filhos[pai.pk] = ordem + 1

            nova = Atividade.objects.create(
                tenant_id=cronograma.tenant_id, cronograma=cronograma, pai=pai,
                codigo=_temporario(), nome=nome, ordem=ordem, profundidade=nivel,
                eh_marco=eh_marco,
                duracao_dias=None if eh_marco else (duracao if duracao and duracao > 0 else None),
                nao_comecar_antes_de=inicio_minimo, peso_informado=peso,
            )
            criadas.append((nova, {"numero": numero, **linha}))
            if codigo_original:
                por_codigo[codigo_original] = nova
            pilha.append((nivel, nova))

        com_filhos = {a.pai_id for a, _ in criadas if a.pai_id}
        for atividade, _linha in criadas:
            if (atividade.pk not in com_filhos and not atividade.eh_marco
                    and not atividade.duracao_dias):
                atividade.duracao_dias = 1
                atividade.save(update_fields=["duracao_dias"])

        por_numero = {linha["numero"]: a for a, linha in criadas}
        ligacoes: list[Precedencia] = []
        vistas: set[tuple[int, int]] = set()
        for atividade, linha in criadas:
            for ref, tipo, lag in ler_predecessoras(str(linha.get("predecessoras") or "")):
                if not tipo:
                    avisos.append(f"Linha {linha['numero']}: '{ref}' não é uma predecessora legível.")
                    continue
                if referencia == "linha":
                    origem = por_numero.get(int(ref)) if ref.isdigit() else None
                else:
                    origem = por_codigo.get(ref) or existentes.get(ref)
                if origem is None:
                    avisos.append(f"Linha {linha['numero']}: a predecessora '{ref}' não existe.")
                    continue
                if origem.pk == atividade.pk or (origem.pk, atividade.pk) in vistas:
                    continue
                vistas.add((origem.pk, atividade.pk))
                ligacoes.append(Precedencia(
                    tenant_id=cronograma.tenant_id, origem=origem, destino=atividade,
                    tipo=tipo, atraso_dias=lag,
                ))
        Precedencia.objects.bulk_create(ligacoes, batch_size=500)
        verificar_rede(cronograma)
        renumerar_eap(cronograma)

    return {
        "criadas": len(criadas),
        "ligacoes": len(ligacoes),
        "avisos": avisos[:50],
        "avisos_total": len(avisos),
    }


def orcamentos_da_obra(cronograma: Cronograma) -> list[dict]:
    """Os orçamentos que podem dar as etapas deste plano — os da mesma obra,
    fora os cancelados, o aprovado primeiro — com quantas etapas cada um já tem
    no tempo (o cronograma físico-financeiro do Orçamento)."""
    from moduloorcamento.models import Orcamento

    if not cronograma.obra_id:
        return []
    ordem = {Orcamento.Status.APROVADO: 0, Orcamento.Status.RASCUNHO: 1,
             Orcamento.Status.SUPERADO: 2}
    lista = (Orcamento.objects
             .filter(tenant_id=cronograma.tenant_id, obra_id=cronograma.obra_id)
             .exclude(status=Orcamento.Status.CANCELADO)
             .annotate(itens_count=Count("itens"), etapas_no_tempo=Count("planos_etapa", distinct=True)))
    ja = cronograma.orcamento_origem_id if cronograma.atividades.filter(peso_do_orcamento=True).exists() else None
    saida = [
        {
            "orcamento_id": o.orcamento_id, "descricao": o.descricao, "versao": o.versao,
            "status": o.status, "status_rotulo": o.get_status_display(),
            "itens": o.itens_count, "etapas_no_tempo": o.etapas_no_tempo,
            "valor_total": o.valor_total,
            "ja_no_plano": o.orcamento_id == ja,
        }
        for o in lista
    ]
    saida.sort(key=lambda o: (ordem.get(o["status"], 9), -o["versao"]))
    return saida


def _etapas_do_orcamento(cronograma: Cronograma, orcamento, duracao_padrao: int) -> list[dict]:
    """As etapas do cronograma do Orçamento, já traduzidas para o plano: a
    duração em dias úteis **do expediente deste plano** (o mesmo do CPM) e o
    início como restrição "não começar antes de"."""
    from moduloorcamento import cronograma as cronograma_do_orcamento

    quadro = cronograma_do_orcamento.etapas_planejadas(orcamento)
    calendario = cronograma.calendario or calendario_da_obra(cronograma.obra, tenant_id=cronograma.tenant_id)
    saida = []
    for etapa in quadro["etapas"]:
        inicio = date.fromisoformat(etapa["inicio"]) if etapa["inicio"] else None
        termino = date.fromisoformat(etapa["termino"]) if etapa["termino"] else None
        if inicio and termino:
            duracao = (dias_uteis(calendario, inicio, termino) if calendario is not None
                       else etapa["dias_uteis"]) or 1
        else:
            duracao = duracao_padrao
        horas = etapa["horas_mao_de_obra"]
        saida.append({
            # `etapa` é a EtapaObra ligada no orçamento — opcional. Sem ela a
            # atividade nasce sem etapa da obra, e o planejador liga aqui.
            "etapa": etapa["etapa"], "nome": etapa["etapa_nome"][:200], "ordem": etapa["ordem"],
            "valor": Decimal(etapa["valor"]), "inicio": inicio, "duracao": max(int(duracao), 1),
            "planejada": etapa["planejada"],
            "observacao": f"Orçado: {horas} Hh de mão de obra." if horas else "",
        })
    return saida


def gerar_do_orcamento(cronograma: Cronograma, *, orcamento_id: int,
                       duracao_padrao: int = 5, simular: bool = False) -> dict:
    """As **etapas** do plano nascem do cronograma físico-financeiro do Orçamento.

    *Decisão do dono, 10/10/2026:* do orçamento vêm **só etapas** — a etapa da
    obra, quando começa (vira "não começar antes de"), quanto dura (os dias
    úteis do período, no expediente deste plano), quanto vale (o peso, em reais,
    marcado `peso_do_orcamento` para contar no avanço financeiro) e o Hh orçado.
    O detalhe — serviços, frentes, sequência — o planejador monta aqui como
    quiser, ligado ou não à planilha. Etapa com valor e ainda sem datas no
    Orçamento entra com `duracao_padrao` e sem restrição de início, e a resposta
    as conta (`sem_plano`).
    """
    from moduloorcamento.models import Orcamento

    _exigir_rascunho(cronograma)
    orcamento = (Orcamento.objects
                 .filter(pk=orcamento_id, tenant_id=cronograma.tenant_id).first())
    if orcamento is None or orcamento.obra_id != cronograma.obra_id:
        raise ValidationError("Este orçamento não é da obra deste plano.")
    if cronograma.atividades.filter(peso_do_orcamento=True).exists():
        raise ValidationError(
            "As etapas do orçamento já estão neste plano. Para trazer uma mudança do "
            "cronograma do orçamento, use \"atualizar do orçamento\"."
        )
    etapas = _etapas_do_orcamento(cronograma, orcamento, max(int(duracao_padrao or 1), 1))
    if not etapas:
        raise ValidationError(
            "Este orçamento não tem etapa com valor. Crie as etapas (grupos de 1º nível) "
            "na planilha do Orçamento."
        )
    resumo = {
        "orcamento": orcamento.orcamento_id, "versao": orcamento.versao,
        "linhas": len(etapas), "planejadas": sum(1 for e in etapas if e["planejada"]),
        "sem_plano": sum(1 for e in etapas if not e["planejada"]),
    }
    if simular:
        return {**resumo, "simulado": True}

    validar_teto_de_atividades(cronograma, acrescentando=len(etapas))
    ordem_raiz = cronograma.atividades.filter(pai__isnull=True).aggregate(m=Max("ordem"))["m"]
    ordem_raiz = -1 if ordem_raiz is None else ordem_raiz
    with transaction.atomic():
        for etapa in etapas:
            ordem_raiz += 1
            Atividade.objects.create(
                tenant_id=cronograma.tenant_id, cronograma=cronograma, pai=None,
                codigo=_temporario(), nome=etapa["nome"], ordem=ordem_raiz, profundidade=1,
                duracao_dias=etapa["duracao"], nao_comecar_antes_de=etapa["inicio"],
                etapa_id=etapa["etapa"], peso_informado=etapa["valor"], peso_do_orcamento=True,
                observacao=etapa["observacao"],
            )
        Cronograma.objects.filter(pk=cronograma.pk).update(
            orcamento_origem=orcamento, cronograma_orcamento_em=orcamento.cronograma_atualizado_em,
        )
        cronograma.orcamento_origem = orcamento
        cronograma.cronograma_orcamento_em = orcamento.cronograma_atualizado_em
        renumerar_eap(cronograma)
    return {**resumo, "simulado": False, "criadas": len(etapas)}


def situacao_do_orcamento(cronograma: Cronograma) -> dict:
    """O aviso do "copia e avisa": o cronograma do orçamento mudou desde que
    este plano trouxe as etapas?

    Duas causas, ditas separadamente porque pedem leituras diferentes: **versão
    nova** do orçamento (uma revisão aprovada substituiu a de origem) e
    **cronograma editado** na mesma versão (o planejador mudou datas lá). O
    plano não muda sozinho — quem decide trazer é o planejador.
    """
    from moduloorcamento.models import Orcamento
    from moduloorcamento.planilha import orcamento_vigente

    # Do banco, e não do cache da relação: o carimbo é justamente o que muda.
    origem = (Orcamento.objects.filter(pk=cronograma.orcamento_origem_id).first()
              if cronograma.orcamento_origem_id else None)
    tem_etapas = cronograma.atividades.filter(peso_do_orcamento=True).exists()
    vigente = orcamento_vigente(cronograma.tenant_id, cronograma.obra_id) if cronograma.obra_id else None
    motivo = None
    if origem is not None and tem_etapas:
        if vigente is not None and vigente.pk != origem.pk and vigente.versao > origem.versao:
            motivo = "nova_versao"
        elif (origem.cronograma_atualizado_em and
              (cronograma.cronograma_orcamento_em is None
               or origem.cronograma_atualizado_em > cronograma.cronograma_orcamento_em)):
            motivo = "cronograma_editado"
    alvo = vigente if motivo == "nova_versao" else origem
    return {
        "tem_etapas_do_orcamento": tem_etapas,
        "origem": origem.pk if origem else None,
        "origem_versao": origem.versao if origem else None,
        "origem_status": origem.status if origem else None,
        "vigente": vigente.pk if vigente else None,
        "vigente_versao": vigente.versao if vigente else None,
        "mudou": motivo is not None,
        "motivo": motivo,
        "atualizar_de": alvo.pk if (motivo and alvo) else None,
        "pode_atualizar": motivo is not None and cronograma.status == Cronograma.Status.RASCUNHO,
    }


def atualizar_do_orcamento(cronograma: Cronograma, *, orcamento_id: int | None = None,
                           duracao_padrao: int = 5) -> dict:
    """Traz para o plano o que mudou no cronograma do orçamento.

    Para cada etapa: a atividade-etapa que já existe recebe o início, a duração
    (se ainda for folha — etapa já detalhada dura o que as filhas duram) e o
    valor novos; a etapa nova entra no fim. A etapa que **saiu** do orçamento
    não é apagada: pode ter avanço apontado, e apagar histórico não é atualizar.
    Ela é devolvida em `fora_do_orcamento` para o planejador decidir.
    """
    from moduloorcamento.models import Orcamento

    _exigir_rascunho(cronograma)
    if orcamento_id is None:
        orcamento_id = situacao_do_orcamento(cronograma)["atualizar_de"] or cronograma.orcamento_origem_id
    orcamento = Orcamento.objects.filter(pk=orcamento_id, tenant_id=cronograma.tenant_id).first()
    if orcamento is None or orcamento.obra_id != cronograma.obra_id:
        raise ValidationError("Este orçamento não é da obra deste plano.")

    etapas = _etapas_do_orcamento(cronograma, orcamento, max(int(duracao_padrao or 1), 1))
    # A atividade-etapa casa pela etapa da obra quando o orçamento a ligou, e
    # pelo nome quando não (etapa só do orçamento).
    existentes = {
        (a.etapa_id or a.nome): a for a in cronograma.atividades.filter(peso_do_orcamento=True)
    }
    com_filhos = set(cronograma.atividades.filter(pai__isnull=False).values_list("pai_id", flat=True))
    atualizadas = criadas = 0
    with transaction.atomic():
        ordem_raiz = cronograma.atividades.filter(pai__isnull=True).aggregate(m=Max("ordem"))["m"]
        ordem_raiz = -1 if ordem_raiz is None else ordem_raiz
        for etapa in etapas:
            atividade = existentes.pop(etapa["etapa"] or etapa["nome"], None)
            if atividade is None:
                ordem_raiz += 1
                validar_teto_de_atividades(cronograma, acrescentando=1)
                Atividade.objects.create(
                    tenant_id=cronograma.tenant_id, cronograma=cronograma, pai=None,
                    codigo=_temporario(), nome=etapa["nome"], ordem=ordem_raiz, profundidade=1,
                    duracao_dias=etapa["duracao"], nao_comecar_antes_de=etapa["inicio"],
                    etapa_id=etapa["etapa"], peso_informado=etapa["valor"], peso_do_orcamento=True,
                    observacao=etapa["observacao"],
                )
                criadas += 1
                continue
            atividade.nao_comecar_antes_de = etapa["inicio"]
            atividade.peso_informado = etapa["valor"]
            campos = ["nao_comecar_antes_de", "peso_informado", "atualizado_em"]
            if atividade.atividade_id not in com_filhos:
                atividade.duracao_dias = etapa["duracao"]
                campos.append("duracao_dias")
            atividade.save(update_fields=campos)
            atualizadas += 1
        Cronograma.objects.filter(pk=cronograma.pk).update(
            orcamento_origem=orcamento, cronograma_orcamento_em=orcamento.cronograma_atualizado_em,
        )
        cronograma.orcamento_origem = orcamento
        cronograma.cronograma_orcamento_em = orcamento.cronograma_atualizado_em
        if criadas:
            renumerar_eap(cronograma)
    _calcular_se_der(cronograma)
    return {
        "orcamento": orcamento.pk, "versao": orcamento.versao,
        "atualizadas": atualizadas, "criadas": criadas,
        "fora_do_orcamento": [{"atividade": a.pk, "nome": a.nome} for a in existentes.values()],
    }


def restaurar_linhas(cronograma: Cronograma, *, pai_id: int | None, posicao: int | None,
                     atividades: list[dict], ligacoes: list[dict]) -> dict:
    """Desfaz uma exclusão: recria a subárvore que a tela fotografou antes de
    apagar, no mesmo lugar, com as ligações — e devolve o mapa `id antigo → id
    novo`, que a pilha de desfazer usa para continuar apontando certo.

    *Decisão do dono, 09/10/2026:* o Ctrl+Z tem de valer "até eu finalizar o
    plano" — e excluir era o gesto que não voltava. Os vínculos que vêm da tela
    (local, etapa, item orçado, expediente, responsável) são **conferidos**
    contra esta obra e esta empresa: o que não é dela volta vazio, e não vira
    referência atravessando a fronteira. *Limite declarado:* as restrições e os
    apontamentos que a exclusão levou não voltam — eles são histórico, e o
    histórico apagado não se reescreve.
    """
    from obras.models import EtapaObra
    from moduloorcamento.models import ItemOrcado
    from rh.models import Funcionario

    _exigir_rascunho(cronograma)
    if not atividades:
        raise ValidationError("Nada para restaurar.")
    validar_teto_de_atividades(cronograma, acrescentando=len(atividades))
    pai = cronograma.atividades.filter(pk=pai_id).first() if pai_id else None
    if pai_id and pai is None:
        raise ValidationError("O lugar de onde a linha saiu não existe mais neste plano.")

    def validos(modelo, ids, **filtro):
        ids = {i for i in ids if i}
        if not ids:
            return set()
        return set(modelo.objects.filter(pk__in=ids, **filtro).values_list("pk", flat=True))

    tenant = cronograma.tenant_id
    locais = validos(LocalObra, [a.get("local") for a in atividades], tenant_id=tenant, obra_id=cronograma.obra_id)
    etapas = validos(EtapaObra, [a.get("etapa") for a in atividades], tenant_id=tenant, obra_id=cronograma.obra_id)
    itens = validos(ItemOrcado, [a.get("item_orcado") for a in atividades],
                    tenant_id=tenant, orcamento__obra_id=cronograma.obra_id)
    calendarios = set(
        CalendarioTrabalho.objects.filter(
            Q(obra__isnull=True) | Q(obra_id=cronograma.obra_id),
            pk__in={a.get("calendario") for a in atividades if a.get("calendario")},
            tenant_id=tenant,
        ).values_list("pk", flat=True)
    )
    pessoas = validos(Funcionario, [a.get("responsavel") for a in atividades], tenant_id=tenant)

    ids_antigos = {int(a["id"]) for a in atividades}
    raizes = [a for a in atividades if a.get("pai") not in ids_antigos]
    if len(raizes) != 1:
        raise ValidationError("A restauração traz uma linha e o que está dentro dela.")

    mapa: dict[int, int] = {}
    with transaction.atomic():
        pendentes = list(atividades)
        while pendentes:
            proximos = []
            for a in pendentes:
                pai_antigo = a.get("pai")
                if a is raizes[0]:
                    novo_pai = pai
                elif pai_antigo in mapa:
                    novo_pai = Atividade.objects.get(pk=mapa[pai_antigo])
                else:
                    proximos.append(a)
                    continue
                duracao = a.get("duracao_dias")
                nova = Atividade.objects.create(
                    tenant_id=tenant, cronograma=cronograma, pai=novo_pai,
                    codigo=_temporario(), nome=str(a.get("nome") or "Atividade")[:200],
                    ordem=int(a.get("ordem") or 0),
                    profundidade=1 if novo_pai is None else novo_pai.profundidade + 1,
                    eh_marco=bool(a.get("eh_marco")),
                    duracao_dias=None if a.get("eh_marco") else (int(duracao) if duracao else 1),
                    nao_comecar_antes_de=(date.fromisoformat(str(a["nao_comecar_antes_de"])[:10])
                                          if a.get("nao_comecar_antes_de") else None),
                    local_id=a.get("local") if a.get("local") in locais else None,
                    etapa_id=a.get("etapa") if a.get("etapa") in etapas else None,
                    item_orcado_id=a.get("item_orcado") if a.get("item_orcado") in itens else None,
                    calendario_id=a.get("calendario") if a.get("calendario") in calendarios else None,
                    responsavel_id=a.get("responsavel") if a.get("responsavel") in pessoas else None,
                    peso_informado=(Decimal(str(a["peso_informado"]))
                                    if a.get("peso_informado") not in (None, "") else None),
                    antecedencia_compra_dias=(int(a["antecedencia_compra_dias"])
                                              if a.get("antecedencia_compra_dias") not in (None, "") else None),
                    observacao=str(a.get("observacao") or ""),
                )
                mapa[int(a["id"])] = nova.pk
            if len(proximos) == len(pendentes):
                raise ValidationError("A árvore enviada não fecha: há linha sem pai.")
            pendentes = proximos

        # A linha de cima volta à posição de onde saiu, entre as irmãs.
        raiz = Atividade.objects.get(pk=mapa[int(raizes[0]["id"])])
        irmas = list(cronograma.atividades.filter(pai=pai).exclude(pk=raiz.pk)
                     .order_by("ordem", "codigo", "atividade_id"))
        irmas.insert(min(max(posicao or 0, 0), len(irmas)), raiz)
        for indice, irma in enumerate(irmas):
            Atividade.objects.filter(pk=irma.pk).update(ordem=indice)

        existentes = set(cronograma.atividades.values_list("pk", flat=True))
        novas_ligacoes = []
        for lig in ligacoes:
            origem = mapa.get(lig.get("origem"), lig.get("origem"))
            destino = mapa.get(lig.get("destino"), lig.get("destino"))
            if origem in existentes and destino in existentes and origem != destino:
                novas_ligacoes.append(Precedencia(
                    tenant_id=tenant, origem_id=origem, destino_id=destino,
                    tipo=lig.get("tipo") or Precedencia.Tipo.FS,
                    atraso_dias=int(lig.get("atraso_dias") or 0),
                ))
        Precedencia.objects.bulk_create(novas_ligacoes, batch_size=500)
        verificar_rede(cronograma)
        renumerar_eap(cronograma)

    return {"mapa": {str(k): v for k, v in mapa.items()}, "ligacoes": len(novas_ligacoes)}


def anexar_modelo(modelo: Cronograma, destino: Cronograma) -> dict:
    """Traz a estrutura de um plano modelo para **dentro** de um rascunho que já
    existe — no fim, sem apagar o que está lá. `aplicar_modelo` cria o primeiro
    plano; este é o caso da obra que já começou a montar e quer o padrão da
    fundação, ou da torre, sem recomeçar."""
    if not modelo.eh_modelo:
        raise ValidationError("Este cronograma não está marcado como modelo.")
    if modelo.pk == destino.pk:
        raise ValidationError("Um plano não se anexa a si mesmo.")
    _exigir_rascunho(destino)
    quantas = modelo.atividades.count()
    validar_teto_de_atividades(destino, acrescentando=quantas)
    with transaction.atomic():
        traducao = copiar_estrutura(
            modelo, destino, manter_vinculos_da_obra=False, anexando=True,
        )
        renumerar_eap(destino)
    return {"criadas": len(traducao)}


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
# 8b. O avanço físico-financeiro é do plano (decisão do dono, 09-10/10/2026)
# ---------------------------------------------------------------------------
#
# *"O cronograma físico-financeiro é do Orçamento; o **avanço** físico-
# financeiro é do PDCA."* O Orçamento planeja quanto cai em cada mês (a grade
# etapa × competência) e acompanha o **custo** consumido. Quanto da obra foi
# **executado** — e quanto isso vale — é o avanço apontado no plano: o previsto
# até hoje pelas datas do CPM, o realizado pelos apontamentos, em % e em reais
# (o valor orçado de cada atividade × o avanço dela).


def _dias_uteis_da_folha(atividade, calendarios, cronograma) -> list[date]:
    calendario = calendarios.get(atividade.calendario_id or cronograma.calendario_id)
    dias: list[date] = []
    if calendario is not None and not atividade.eh_marco:
        comeco = calendario.indice_adiante(atividade.inicio_cedo)
        fim = calendario.indice_atras(atividade.termino_cedo)
        dias = [calendario.data(i) for i in range(comeco, max(fim, comeco) + 1)]
    # Marco e plano sem expediente: o peso inteiro no término, como a curva S.
    return dias or [atividade.termino_cedo]


def avanco_fisico_financeiro(cronograma: Cronograma, *, hoje: date | None = None) -> dict:
    """Etapa a etapa (raiz do plano): previsto até hoje × realizado, em % do
    físico e em reais do orçado, com o desvio. A linha da obra fecha embaixo.

    - **previsto** — cada folha contribui com a fração dos dias úteis dela que
      já passaram (as datas do CPM), ponderada pelo peso;
    - **realizado** — o avanço apontado da folha (a cadeia de versões, a mesma
      leitura do Gantt), ponderado pelo peso;
    - **em reais** — só as folhas ligadas ao orçamento, pelo valor do item. A
      folha sem vínculo pesa no físico e fica fora do dinheiro, e a resposta
      conta quantas são — um R$ que ignorasse 40% do serviço sem dizer seria
      número inventado.
    """
    hoje = hoje or timezone.localdate()
    atividades = list(cronograma.atividades
                      .select_related("item_orcado", "calendario")
                      .order_by("ordem", "codigo", "atividade_id"))
    por_id = {a.atividade_id: a for a in atividades}
    com_filhos = {a.pai_id for a in atividades if a.pai_id}
    folhas = [a for a in atividades if a.atividade_id not in com_filhos]
    calendarios = _calendarios_do_cronograma(cronograma, atividades) if atividades else {}
    avanco = avanco_do_cronograma(cronograma)["por_atividade"] if atividades else {}

    def raiz_de(a):
        vistos = 0
        while a.pai_id and a.pai_id in por_id and vistos < 64:
            a = por_id[a.pai_id]
            vistos += 1
        return a

    zero = Decimal("0")
    contas: dict[int, dict[str, Decimal]] = {}
    sem_peso = sem_data = sem_orcamento = 0
    for a in folhas:
        p, de_onde = peso_de(a)
        if p is None or p <= 0:
            sem_peso += 1
            continue
        conta = contas.setdefault(raiz_de(a).atividade_id, {
            "peso": zero, "previsto": zero, "realizado": zero,
            "valor": zero, "valor_previsto": zero, "valor_realizado": zero,
        })
        if a.inicio_cedo and a.termino_cedo:
            dias = _dias_uteis_da_folha(a, calendarios, cronograma)
            passou = Decimal(sum(1 for d in dias if d <= hoje)) / Decimal(len(dias))
        else:
            sem_data += 1
            passou = zero
        feito = Decimal(str((avanco.get(a.atividade_id) or {}).get("avanco") or 0)) / 100
        conta["peso"] += p
        conta["previsto"] += p * passou
        conta["realizado"] += p * feito
        if de_onde == "orcado":
            conta["valor"] += p
            conta["valor_previsto"] += p * passou
            conta["valor_realizado"] += p * feito
        else:
            sem_orcamento += 1

    def linha(conta: dict[str, Decimal]) -> dict:
        def pct(parte):
            return float(round(parte / conta["peso"] * 100, 2)) if conta["peso"] > 0 else None

        def reais(v):
            return str(v.quantize(Decimal("0.01")))

        return {
            "previsto_pct": pct(conta["previsto"]),
            "realizado_pct": pct(conta["realizado"]),
            "desvio_pct": (None if conta["peso"] <= 0 else
                           float(round((conta["realizado"] - conta["previsto"]) / conta["peso"] * 100, 2))),
            "valor_orcado": reais(conta["valor"]),
            "valor_previsto": reais(conta["valor_previsto"]),
            "valor_realizado": reais(conta["valor_realizado"]),
            "valor_desvio": reais(conta["valor_realizado"] - conta["valor_previsto"]),
        }

    linhas = []
    obra = {k: zero for k in ("peso", "previsto", "realizado", "valor", "valor_previsto", "valor_realizado")}
    planejado = _planejado_do_orcamento(
        cronograma.orcamento_origem_id or _orcamento_das_folhas(folhas), hoje,
    )

    def contra_o_planejado(etapa_id, realizado: Decimal) -> dict:
        if planejado is None or (etapa_id is not None and etapa_id not in planejado["por_etapa"]):
            return {"valor_planejado": None, "valor_desvio_planejado": None}
        valor = (planejado["ate_hoje"] if etapa_id is None
                 else planejado["por_etapa"][etapa_id])
        return {
            "valor_planejado": str(valor.quantize(Decimal("0.01"))),
            "valor_desvio_planejado": str((realizado - valor).quantize(Decimal("0.01"))),
        }

    for raiz in (a for a in atividades if a.pai_id is None):
        conta = contas.get(raiz.atividade_id)
        if conta is None:
            continue
        for k in obra:
            obra[k] += conta[k]
        linhas.append({
            "atividade": raiz.atividade_id, "codigo": raiz.codigo, "nome": raiz.nome,
            "etapa": raiz.etapa_id, **linha(conta),
            **contra_o_planejado(raiz.etapa_id or -1, conta["valor_realizado"]),
        })

    return {
        "cronograma": cronograma.pk,
        "status": cronograma.status,
        "hoje": hoje,
        "linhas": linhas,
        "obra": {**linha(obra), **contra_o_planejado(None, obra["valor_realizado"])},
        "tem_dinheiro": obra["valor"] > 0,
        "folhas_sem_peso": sem_peso,
        "folhas_sem_data": sem_data,
        "folhas_sem_orcamento": sem_orcamento,
        #: O **planejado** é o cronograma físico-financeiro do Orçamento (as
        #: parcelas etapa × competência). Nulo quando o orçamento não tem
        #: cronograma — e a tela diz isso, em vez de comparar com zero.
        "planejado": None if planejado is None else {
            "orcamento": planejado["orcamento"],
            "total": str(planejado["total"].quantize(Decimal("0.01"))),
            "ate_hoje": str(planejado["ate_hoje"].quantize(Decimal("0.01"))),
            "mensal": planejado["mensal"],
        },
    }


def _orcamento_das_folhas(folhas) -> int | None:
    """O orçamento que o plano usa — o dos itens ligados, pelo maior valor."""
    valor: dict[int, Decimal] = {}
    for a in folhas:
        if a.item_orcado_id and a.item_orcado is not None:
            chave = a.item_orcado.orcamento_id
            valor[chave] = valor.get(chave, Decimal("0")) + (a.item_orcado.total_com_bdi or 0)
    return max(valor, key=valor.get) if valor else None


def _planejado_do_orcamento(orcamento_id, hoje: date) -> dict | None:
    """O cronograma físico-financeiro do Orçamento até hoje, por etapa e por mês.

    A competência inteira conta quando já passou; a corrente conta **pro rata**
    pelos dias corridos — comparar no dia 5 com o mês inteiro planejado diria
    que a obra está atrasada só porque o mês não acabou.
    """
    if orcamento_id is None:
        return None
    from calendar import monthrange

    from moduloorcamento.models import ParcelaEtapa

    # A parcela é do grupo do orçamento; a etapa da obra é o vínculo opcional
    # dele. Grupo sem vínculo conta no total e no mês, mas não em etapa alguma.
    parcelas = list(ParcelaEtapa.objects.filter(orcamento_id=orcamento_id)
                    .values("grupo__etapa_id", "competencia", "valor_previsto"))
    for p in parcelas:
        p["etapa_id"] = p.pop("grupo__etapa_id")
    if not parcelas:
        return None
    este_mes = hoje.replace(day=1)
    fracao = Decimal(hoje.day) / Decimal(monthrange(hoje.year, hoje.month)[1])
    por_etapa: dict[int, Decimal] = {}
    por_mes: dict[date, Decimal] = {}
    total = ate_hoje = Decimal("0")
    for p in parcelas:
        valor = p["valor_previsto"] or Decimal("0")
        mes = p["competencia"].replace(day=1)
        vale = valor if mes < este_mes else (valor * fracao if mes == este_mes else Decimal("0"))
        total += valor
        ate_hoje += vale
        if p["etapa_id"] is not None:
            por_etapa[p["etapa_id"]] = por_etapa.get(p["etapa_id"], Decimal("0")) + vale
        por_mes[mes] = por_mes.get(mes, Decimal("0")) + valor
    mensal, acumulado = [], Decimal("0")
    for mes in sorted(por_mes):
        acumulado += por_mes[mes]
        mensal.append({
            "mes": mes,
            "valor": str(por_mes[mes].quantize(Decimal("0.01"))),
            "acumulado": str(acumulado.quantize(Decimal("0.01"))),
            "pct_acumulado": float(round(acumulado / total * 100, 2)) if total > 0 else 0.0,
        })
    return {"orcamento": orcamento_id, "por_etapa": por_etapa, "total": total,
            "ate_hoje": ate_hoje, "mensal": mensal}


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
        .exclude(medicao_id__in=_fora_da_conta(contrato, excluir_medicao_id))
        .values("item_contrato_id")
        .annotate(total=Sum("quantidade"))
    )
    return {linha["item_contrato_id"]: linha["total"] or _ZERO for linha in linhas}


def _fora_da_conta(contrato: ContratoObra, excluir_medicao_id: int | None) -> set[int]:
    """As medições que **não** somam no acumulado, além das que o status já tira.

    A retificadora guarda a medição corrigida **inteira** *(decisão do dono,
    11/10/2026)*: ela substitui a original, não soma a ela. Enquanto sobe a
    escada, a original ainda está aprovada — e contar as duas mediria o mesmo
    período duas vezes. Por isso a original de toda retificadora em aprovação
    sai da conta, e a de quem está sendo calculado também (a retificadora é
    medida contra o contrato **sem** a medição que ela corrige).
    """
    fora = set(
        contrato.medicoes
        .filter(status=Medicao.Status.EM_APROVACAO, retifica__isnull=False)
        .values_list("retifica_id", flat=True)
    )
    if excluir_medicao_id is not None:
        fora.add(excluir_medicao_id)
        original = (
            Medicao.todos.filter(pk=excluir_medicao_id)
            .values_list("retifica_id", flat=True).first()
        )
        if original:
            fora.add(original)
    return fora


def posicao_da_medicao(medicao: Medicao) -> int:
    """O lugar da medição na corrente do contrato.

    A retificadora nasce com o próximo número livre, mas fala do período da que
    corrige — e é esse o lugar dela para o estoque de material ("o que a
    anterior declarava"). Retificadora de retificadora sobe a corrente.
    """
    while medicao.retifica_id is not None:
        medicao = medicao.retifica
    return medicao.numero


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
        .exclude(medicao_id__in=_fora_da_conta(contrato, excluir_medicao_id))
    )
    # A posição de cada medição na corrente — a retificadora ocupa a da que
    # corrige (`posicao_da_medicao`), resolvida aqui de uma vez por contrato.
    corrente = {
        pk: (numero, retifica_id)
        for pk, numero, retifica_id in Medicao.todos.filter(contrato=contrato)
        .values_list("pk", "numero", "retifica_id")
    }

    def posicao(pk: int) -> int:
        numero, original = corrente[pk]
        while original is not None and original in corrente:
            numero, original = corrente[original]
        return numero

    saldo: dict[int, Decimal] = {}
    ultimo: dict[int, int] = {}
    for item_id, medicao_id, estocada in consulta.values_list(
        "item_contrato_id", "medicao_id", "quantidade_estocada",
    ):
        numero = posicao(medicao_id)
        if antes_de is not None and numero >= antes_de:
            continue
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
        antes_de=posicao_da_medicao(medicao) if medicao is not None else None,
        excluir_medicao_id=excluir,
    )
    gravado = {
        linha.item_contrato_id: linha
        for linha in (medicao.itens.all() if medicao is not None else [])
    }
    # A retificadora grava a medição corrigida **inteira**; a tela mostra, ao
    # lado, o que a original mediu — o quadro original | corrigido | diferença.
    # `None` fora de retificadora.
    na_original = (
        {l.item_contrato_id: l for l in medicao.retifica.itens.all()}
        if medicao is not None and medicao.retifica_id is not None else None
    )

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
            "quantidade_na_original": (
                None if na_original is None else (
                    na_original[item.pk].quantidade if item.pk in na_original else _ZERO
                )
            ),
            "estocada_na_original": (
                None if na_original is None else (
                    na_original[item.pk].quantidade_estocada
                    if item.pk in na_original else _ZERO
                )
            ),
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
        contrato.medicoes.filter(status__in=(*_VIVAS, Medicao.Status.RETIFICADA), retifica__isnull=True)
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
        .filter(status__in=(*_EM_VOO, Medicao.Status.RETIFICADA), retifica__isnull=True)
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


def _bruto_sem_reajuste(medicao: Medicao) -> Decimal:
    contrato = medicao.contrato
    if contrato.regime == RegimeContrato.ADMINISTRACAO:
        custo = medicao.custo_reembolsavel or _ZERO
        taxa = medicao.taxa_administracao_aplicada or _ZERO
        return _dinheiro(custo + (custo * taxa / Decimal("100")))
    anterior = estocado_ate(contrato, antes_de=posicao_da_medicao(medicao), excluir_medicao_id=medicao.pk)
    total = _ZERO
    for item in medicao.itens.all():
        delta = item.quantidade_estocada - anterior.get(item.item_contrato_id, _ZERO)
        total += (item.quantidade + delta) * item.preco_unitario
    return _dinheiro(total)


def recalcular_reajuste(medicao: Medicao) -> Medicao:
    """Aplica a fórmula paramétrica do contrato ao bruto do período e **grava**.

    *Decisão do dono, 10/10/2026:* reajuste é ato de contrato — o mesmo motor
    (`nucleo/reajuste.py`) para o empreiteiro e para o contratante. Grava em vez
    de derivar na leitura porque depende do índice publicado no dia: a medição
    aprovada não muda de valor quando a série é revisada. Roda ao criar, ao
    reescrever a grade e de novo no último degrau da aprovação — que é quando o
    índice provisório pode já ter virado definitivo.

    Contrato sem parcelas de reajuste é a preço fixo: zero, sem memória.
    """
    from nucleo import reajuste as motor

    contrato = medicao.contrato
    parcelas = [(p.indice, p.peso, p.rotulo)
                for p in contrato.parcelas_reajuste.select_related("indice")]
    if not parcelas or contrato.reajuste_data_base is None:
        valor, memoria, provisorio = _ZERO, {}, False
    else:
        try:
            memoria = motor.reajuste_do_periodo(
                valor=_bruto_sem_reajuste(medicao), inicio=medicao.periodo_inicio,
                fim=medicao.periodo_fim, parcela_fixa=contrato.reajuste_parcela_fixa,
                parcelas=parcelas, data_base=contrato.reajuste_data_base,
                periodicidade_meses=contrato.reajuste_periodicidade_meses or 12,
                casas=contrato.reajuste_casas or 4,
            )
        except motor.ReajusteInvalido as erro:
            raise ValidationError(str(erro))
        valor, provisorio = Decimal(memoria["valor"]), memoria["provisorio"]
    Medicao.objects.filter(pk=medicao.pk).update(
        valor_reajuste=valor, reajuste_memoria=memoria, reajuste_provisorio=provisorio,
    )
    medicao.valor_reajuste, medicao.reajuste_memoria, medicao.reajuste_provisorio = valor, memoria, provisorio
    return medicao


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
    geral = medicao.retencao_percentual_aplicado
    #: Σ valor da linha × (retenção própria − geral): o que a retenção por item
    #: muda sobre a conta geral. Zero quando nenhum item tem regra própria — e
    #: aí a retenção é exatamente a de sempre (`base × geral`).
    ajuste_por_item = _ZERO

    if contrato.regime == RegimeContrato.ADMINISTRACAO:
        custo = medicao.custo_reembolsavel or _ZERO
        taxa = medicao.taxa_administracao_aplicada or _ZERO
        bruto = custo + (custo * taxa / Decimal("100"))
    else:
        anterior = estocado_ate(
            contrato, antes_de=posicao_da_medicao(medicao), excluir_medicao_id=medicao.pk,
        )
        for item in medicao.itens.all():
            executado += item.quantidade * item.preco_unitario
            delta = item.quantidade_estocada - anterior.get(
                item.item_contrato_id, _ZERO,
            )
            estoque += delta * item.preco_unitario
            if item.retencao_percentual is not None and item.retencao_percentual != geral:
                ajuste_por_item += (
                    (item.quantidade + delta) * item.preco_unitario
                    * (item.retencao_percentual - geral)
                )
        bruto = executado + estoque

    bruto = _dinheiro(bruto)
    # O reajuste soma ao bruto antes da retenção e das deduções: a caução e o
    # imposto incidem sobre o que o período vale **reajustado**.
    reajuste = _dinheiro(medicao.valor_reajuste or _ZERO)
    base = bruto + reajuste
    retencao = _dinheiro((base * geral + ajuste_por_item) / Decimal("100"))

    deducoes = []
    total_deducoes = _ZERO
    for deducao in medicao.deducoes.all():
        valor = valor_da_deducao(deducao, base)
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

    liquido = base - retencao - _dinheiro(total_deducoes)
    #: **O líquido é o valor líquido da medição, não a diferença** *(achado do
    #: dono, 11/10/2026)*. A retificadora guarda a medição corrigida inteira, então
    #: o líquido dela já é o que vale; a original viaja ao lado só para a tela
    #: montar a conciliação (antes | corrigido | diferença).
    original = None
    if medicao.retifica_id is not None:
        antes = totais_da_medicao(medicao.retifica)
        original = {
            "medicao_id": medicao.retifica_id,
            "numero": medicao.retifica.numero,
            "bruto_reajustado": antes["bruto_reajustado"],
            "retencao": antes["retencao"],
            "total_deducoes": antes["total_deducoes"],
            "liquido": antes["liquido"],
        }

    return {
        "executado": _dinheiro(executado),
        "material_estocado": _dinheiro(estoque),
        "bruto": bruto,
        "reajuste": reajuste,
        "reajuste_provisorio": bool(medicao.reajuste_provisorio),
        "bruto_reajustado": base,
        "retencao": retencao,
        "retencao_percentual": medicao.retencao_percentual_aplicado,
        #: Algum item reteve diferente do percentual geral (regra do aditivo).
        "retencao_por_item": ajuste_por_item != 0,
        "deducoes": deducoes,
        "total_deducoes": _dinheiro(total_deducoes),
        "liquido": liquido,
        "original": original,
        "diferenca_liquido": (
            None if original is None else liquido - original["liquido"]
        ),
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
    retencao_do_item = dict(contrato.itens.values_list("pk", "retencao_percentual"))
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
            retencao_percentual=retencao_do_item.get(item_id),
            origem=(
                ItemMedicao.Origem.AVANCO
                if escolhidas is None or quantidade == linha["quantidade_proposta"]
                else ItemMedicao.Origem.MANUAL
            ),
        ))
    if a_gravar:
        ItemMedicao.objects.bulk_create(a_gravar)
    return recalcular_reajuste(medicao)


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
            linha.preco_unitario, linha.observacao, linha.retencao_percentual,
        )
        for linha in medicao.itens.all()
    }

    medicao.itens.all().delete()
    a_gravar = []
    for linha in linhas:
        quantidade = Decimal(str(linha.get("quantidade", 0) or 0))
        estocada = Decimal(str(linha.get("quantidade_estocada", 0) or 0))
        item_id = linha["item_contrato_id"]
        if quantidade < 0:
            # A retificadora guarda a medição corrigida inteira (11/10/2026):
            # medir para menos é escrever o número certo, não uma linha negativa.
            raise ValidationError(
                f"Item {validos[item_id].codigo}: quantidade negativa. Para "
                f"corrigir uma medição aprovada, retifique-a e escreva a "
                f"quantidade certa."
            )
        if quantidade == 0 and estocada == 0:
            continue
        proposta, percentual, preco, observacao, retencao = memoria.get(
            item_id, (None, None, None, "", validos[item_id].retencao_percentual),
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
            retencao_percentual=retencao,
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
    recalcular_reajuste(medicao)
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
        if medicao.retifica_id is not None:
            # A retificadora guarda a medição corrigida inteira: ela corrige
            # alguma coisa quando as linhas ou os descontos diferem dos da
            # original. Zerar tudo é correção válida (a medição não devia existir).
            if not _retificadora_muda_algo(medicao):
                problemas.append(
                    "A retificadora não corrige nada: quantidades e descontos "
                    "estão iguais aos da medição original."
                )
        elif not medicao.itens.exists():
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
        contrato, antes_de=posicao_da_medicao(medicao), excluir_medicao_id=medicao.pk,
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
    # **Só quando o bruto é positivo.** O bruto negativo é o período em que o
    # material estocado foi aplicado ou devolvido — ali o líquido negativo é o
    # resultado certo, e `gerar_titulo_de_medicao` não emite título nenhum.
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


def _retificadora_muda_algo(retificadora: Medicao) -> bool:
    def linhas(m: Medicao) -> dict:
        return {
            l.item_contrato_id: (l.quantidade, l.quantidade_estocada)
            for l in m.itens.all() if l.quantidade or l.quantidade_estocada
        }

    def descontos(m: Medicao) -> list:
        return sorted(
            tuple(str(x) for x in (d.tipo, d.descricao, d.percentual, d.base_calculo, d.valor))
            for d in m.deducoes.all()
        )

    original = retificadora.retifica
    return (
        linhas(retificadora) != linhas(original)
        or descontos(retificadora) != descontos(original)
        or retificadora.custo_reembolsavel != original.custo_reembolsavel
    )


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
        recalcular_reajuste(medicao)
        validar_medicao(medicao)

    medicao.status = (
        Medicao.Status.APROVADA if aprovada else Medicao.Status.REPROVADA
    )
    medicao.congelada_em = timezone.now()
    campos = ["status", "congelada_em"]

    if aprovada:
        if medicao.retifica_id is not None:
            campos += _fechar_retificacao(medicao)
        else:
            conta_id = gerar_titulo_de_medicao(medicao)
            if conta_id is not None:
                campo = _campo_do_titulo(medicao)
                setattr(medicao, campo, conta_id)
                campos.append(campo)

    medicao.save(update_fields=campos)
    return medicao


def _campo_do_titulo(medicao: Medicao) -> str:
    return ("conta_receber_ref" if medicao.contrato.lado == LadoContrato.RECEITA
            else "conta_pagar_ref")


def _fechar_retificacao(retificadora: Medicao) -> list[str]:
    """A retificadora aprovada **substitui** a original — e o título vai junto.

    *Decisões do dono, 11/10/2026:*

    - a original vira `RETIFICADA` (legível, fora de toda soma): só a
      retificadora vale, e o contrato nunca mostra duas medições aprovadas para
      o mesmo período;
    - **título da original em aberto** → cancelado, e nasce o da retificadora
      com o líquido **inteiro** da medição corrigida;
    - **título já pago (inteiro ou em parte)** → nada se apaga, porque existe uma
      `Transacao` em cima dele. Nasce o **título da diferença** e o ERP recebe um
      aviso de **nível 3** (`funcoesnotificacoes`):
        * corrigida maior → complemento a pagar (a receber, na receita);
        * corrigida menor e o título ainda tem saldo → o saldo cai primeiro (não
          se paga o que não é devido);
        * o que sobra pago a mais → devolução, no título do sentido inverso,
          contra a mesma contraparte — quando ela existe dos dois lados do
          cadastro (fornecedor ↔ cliente, pelo CNPJ/CPF). Sem ela, o aviso diz
          quanto cobrar e de quem.

    Devolve os campos da retificadora que mudaram.
    """
    from nucleo.auditoria import registrar_auditoria

    original = retificadora.retifica
    Medicao.objects.filter(pk=original.pk).update(status=Medicao.Status.RETIFICADA)
    original.status = Medicao.Status.RETIFICADA

    campo = _campo_do_titulo(retificadora)
    titulo = titulo_da_medicao(original)
    pago = titulo is not None and (
        titulo.valor_pago > 0 or titulo.status in ("QUITADO", "PARCIAL")
    )

    if not pago:
        if titulo is not None and titulo.status != "CANCELADO":
            titulo.status = "CANCELADO"
            titulo.save(update_fields=["status"])
            registrar_auditoria(
                acao="cancelar", instance=titulo, usuario=None,
                detalhes={
                    "origem": "pdca.medicao.retificar",
                    "medicao": original.pk,
                    "retificadora": retificadora.pk,
                    "valor": str(titulo.valor),
                },
            )
        conta_id = gerar_titulo_de_medicao(retificadora, avisar=False)
        novo = (
            f"o novo, {conta_id}, é de R$ {totais_da_medicao(retificadora)['liquido']}"
            if conta_id is not None else "a medição corrigida não tem valor a lançar"
        )
        avisar_erp(
            retificadora.contrato,
            titulo=(
                f"Medição {original.numero} retificada pela {retificadora.numero} "
                f"(contrato {retificadora.contrato.numero}) — título trocado"
            ),
            mensagem=(
                (f"O título {titulo.pk} (R$ {titulo.valor}) foi cancelado; "
                 if titulo is not None and titulo.status == "CANCELADO" else "")
                + f"{novo}."
            ),
        )
        if conta_id is None:
            return []
        setattr(retificadora, campo, conta_id)
        return [campo]

    corrigido = totais_da_medicao(retificadora)["liquido"]
    diferenca = _dinheiro(corrigido - titulo.valor)
    abatido = _ZERO
    complemento_id = devolucao_id = None
    resto = _ZERO
    if diferenca > 0:
        complemento_id = gerar_titulo_de_medicao(
            retificadora, valor=diferenca, avisar=False,
            rotulo=f"complemento da retificação da medição {original.numero}",
        )
    elif diferenca < 0:
        abatido = min(-diferenca, max(_dinheiro(titulo.saldo_aberto), _ZERO))
        if abatido > 0:
            valor_antes = titulo.valor
            titulo.valor = titulo.valor - abatido
            mudou = ["valor"]
            if titulo.saldo_aberto <= 0:
                titulo.status = "QUITADO"
                mudou.append("status")
            titulo.save(update_fields=mudou)
            registrar_auditoria(
                acao="editar", instance=titulo, usuario=None,
                detalhes={
                    "origem": "pdca.medicao.retificar",
                    "medicao": original.pk,
                    "retificadora": retificadora.pk,
                    "valor_antes": str(valor_antes),
                    "valor_depois": str(titulo.valor),
                },
            )
        resto = -diferenca - abatido
        if resto > 0:
            devolucao_id = _gerar_devolucao(retificadora, resto)

    # O título que fala por esta medição: o complemento, ou o original mantido.
    setattr(retificadora, campo, complemento_id or titulo.pk)
    campos = [campo]
    if devolucao_id is not None:
        inverso = ("conta_pagar_ref" if campo == "conta_receber_ref"
                   else "conta_receber_ref")
        setattr(retificadora, inverso, devolucao_id)
        campos.append(inverso)

    _avisar_erp_de_retificacao_paga(
        retificadora, titulo, corrigido=corrigido, diferenca=diferenca,
        abatido=abatido, resto=resto, complemento_id=complemento_id,
        devolucao_id=devolucao_id,
    )
    return campos


def _gerar_devolucao(retificadora: Medicao, valor: Decimal) -> int | None:
    """O pago a mais, no título do sentido inverso — ou `None` sem contraparte.

    Fornecedor e cliente são cadastros diferentes; o elo é o documento (CNPJ/CPF).
    Inventar um cadastro do outro lado criaria um cliente sem e-mail nem
    endereço, que é pior do que o aviso pedindo o lançamento.
    """
    import re

    from moduloerp.models import ContaPagar, ContaReceber

    def digitos(texto) -> str:
        return re.sub(r"\D", "", texto or "")

    contrato = retificadora.contrato
    comum = _comum_do_titulo(
        retificadora, valor=valor,
        descricao=(
            f"Devolução · medição {retificadora.retifica.numero} retificada pela "
            f"{retificadora.numero} · contrato {contrato.numero} · "
            f"{contrato.obra.nome_obra}"
        ),
    )
    if contrato.lado == LadoContrato.RECEITA:
        from fornecedores.models import Fornecedor

        doc = digitos(getattr(contrato.cliente, "cpf_cnpj", ""))
        alvo = next((
            f for f in Fornecedor.objects.filter(tenant_id=contrato.tenant_id)
            .only("pk", "cnpj").iterator()
            if doc and digitos(f.cnpj) == doc
        ), None)
        if alvo is None:
            return None
        return ContaPagar.objects.create(fornecedor=alvo, **comum).pk

    from clientes.models import Cliente

    doc = digitos(getattr(contrato.fornecedor, "cnpj", ""))
    alvo = next((
        c for c in Cliente.objects.filter(tenant_id=contrato.tenant_id)
        .only("pk", "cpf_cnpj").iterator()
        if doc and digitos(c.cpf_cnpj) == doc
    ), None)
    if alvo is None:
        return None
    return ContaReceber.objects.create(cliente=alvo, **comum).pk


def avisar_erp(contrato: ContratoObra, *, titulo: str, mensagem: str,
               nivel: int | None = None) -> None:
    """O PDCA mexeu num título do ERP — avisa quem dá baixa nele.

    *Regra do dono (11/10/2026): alteração que interfere em outro módulo tem
    notificação.* Emitir, cancelar ou reduzir um título é exatamente isso.
    """
    from nucleo.models import Notificacao
    from nucleo.notificacoes import avisar_quem_pode

    receita = contrato.lado == LadoContrato.RECEITA
    avisar_quem_pode(
        tenant_id=contrato.tenant_id,
        permissao="erp.conta_receber.baixar" if receita else "erp.conta_pagar.baixar",
        titulo=titulo, mensagem=mensagem,
        url="/app/erp/contas-a-receber" if receita else "/app/erp/contas-a-pagar",
        nivel=nivel or Notificacao.Nivel.SABER,
    )


def _avisar_erp_de_retificacao_paga(retificadora: Medicao, titulo, *, corrigido,
                                    diferenca, abatido, resto, complemento_id,
                                    devolucao_id) -> None:
    """Aviso de **nível 3** ao financeiro: a medição já paga foi corrigida.

    Vai a quem tem `baixar` no título — a permissão que decide o que fazer com
    ele. Cada frase diz o que **já foi lançado** e o que falta fazer; o link
    abre as contas no ERP.
    """
    from nucleo.models import Notificacao

    receita = retificadora.contrato.lado == LadoContrato.RECEITA
    pago = "recebidos" if receita else "pagos"
    partes = [
        f"A medição {retificadora.retifica.numero} do contrato "
        f"{retificadora.contrato.numero} já tinha R$ {titulo.valor_pago} {pago} "
        f"e foi retificada pela medição {retificadora.numero}. Líquido corrigido: "
        f"R$ {corrigido} (o título {titulo.pk} era de R$ {titulo.valor + abatido})."
    ]
    if diferenca == 0:
        partes.append("O valor do título confere — nada a lançar.")
    if complemento_id is not None:
        partes.append(
            f"Gerado o título {complemento_id} de R$ {diferenca}: complemento a "
            f"{'receber' if receita else 'pagar'}."
        )
    if abatido > 0:
        partes.append(
            f"O título {titulo.pk} caiu R$ {abatido} — o saldo em aberto não é mais devido."
        )
    if resto > 0:
        if devolucao_id is not None:
            partes.append(
                f"Gerado o título {devolucao_id} de R$ {resto}: devolução a "
                f"{'pagar ao cliente' if receita else 'receber do fornecedor'}."
            )
        else:
            partes.append(
                f"R$ {resto} {pago} a mais: a contraparte não está cadastrada como "
                f"{'fornecedor' if receita else 'cliente'} — cadastre e lance a devolução."
            )
    avisar_erp(
        retificadora.contrato,
        titulo=(
            f"Medição {retificadora.retifica.numero} já paga foi retificada "
            f"(contrato {retificadora.contrato.numero}) — conferir no financeiro"
        ),
        mensagem=" ".join(partes), nivel=Notificacao.Nivel.AGIR_JA,
    )


def titulo_da_medicao(medicao: Medicao):
    """A `ContaPagar` que esta medição gerou, ou `None`.

    **Importa tarde**, pela mesma razão do `gerar_titulo_de_medicao`: a §7 da
    planta diz que o PDCA não paga, e o seam é frouxo para que a fronteira seja
    atravessável nos dois sentidos — ou em nenhum, na instalação que não
    contrate o ERP.

    Título que o seam aponta e que sumiu do banco devolve `None`, e isso é caso
    real: a `ContaPagar` herda `Excluivel` e pode ter ido para a lixeira por
    fora. Quem chama trata como "não há título", que é a verdade.
    """
    receita = medicao.contrato.lado == LadoContrato.RECEITA
    ref = medicao.conta_receber_ref if receita else medicao.conta_pagar_ref
    if not ref:
        return None
    try:
        from moduloerp.models import ContaPagar, ContaReceber
    except ImportError:  # instalação sem o módulo financeiro
        return None
    modelo = ContaReceber if receita else ContaPagar
    return modelo.objects.filter(tenant_id=medicao.tenant_id, pk=ref).first()


def estado_do_titulo(medicao: Medicao) -> dict | None:
    """O que a tela precisa saber do título **antes** de oferecer o cancelamento.

    É a metade de leitura da regra do `cancelar_medicao`: sem isto, o botão
    "Cancelar" só descobriria que o título já foi pago **depois** de o gestor
    clicar, e a recusa chegaria como um erro em vez de um aviso. O aviso na tela
    e a trava no servidor têm de sair do **mesmo** lugar, senão divergem na
    primeira mudança de regra.
    """
    conta = titulo_da_medicao(medicao)
    if conta is None:
        return None
    return {
        "conta_pagar": conta.pk,
        #: Do lado da receita o título é a receber — a tela muda o rótulo.
        "lado": medicao.contrato.lado,
        "status": conta.status,
        "status_rotulo": conta.get_status_display(),
        "valor": conta.valor,
        "valor_pago": conta.valor_pago,
        "saldo_aberto": conta.saldo_aberto,
        "data_vencimento": conta.data_vencimento,
        #: A pergunta que decide o botão: cancelar a medição pode levar o título
        #: junto, ou o dinheiro já saiu e só a retificadora conserta.
        "pode_cancelar": (
            conta.valor_pago <= 0
            and conta.status not in ("QUITADO", "PARCIAL", "CANCELADO")
        ),
    }


def gerar_titulo_de_medicao(medicao: Medicao, *, valor: Decimal | None = None,
                           rotulo: str = "", avisar: bool = True) -> int | None:
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
    from moduloerp.models import ContaPagar, ContaReceber

    totais = totais_da_medicao(medicao)
    if (totais["liquido"] if valor is None else valor) <= 0:
        # Medição que não paga nada não gera título. É caso real — a
        # retificadora que zera uma medição anterior —, e um `ContaPagar` de
        # R$ 0,00 seria documento que ninguém consegue baixar nem explicar.
        return None

    contrato = medicao.contrato
    parcelas = f" · {rotulo}" if rotulo else ""
    if medicao.retifica_id is not None and not rotulo:
        parcelas += f" · retifica a medição {medicao.retifica.numero}"
    if valor is None and totais["retencao"] > 0:
        parcelas += (
            f" · retenção R$ {totais['retencao']} "
            f"({medicao.retencao_percentual_aplicado}%)"
        )
    if valor is None and totais["total_deducoes"] > 0:
        rotulos = ", ".join(
            sorted({d["tipo_rotulo"] for d in totais["deducoes"]})
        )
        parcelas += f" · deduções R$ {totais['total_deducoes']} ({rotulos})"
    if valor is None and totais["reajuste"] != 0:
        parcelas = (f" · reajuste R$ {totais['reajuste']}"
                    + (" (índice provisório)" if totais["reajuste_provisorio"] else "") + parcelas)

    comum = _comum_do_titulo(
        medicao,
        valor=totais["liquido"] if valor is None else valor,
        descricao=(
            f"Medição {medicao.numero} · contrato {contrato.numero} · "
            f"{contrato.obra.nome_obra} · período "
            f"{medicao.periodo_inicio:%d/%m/%Y}–{medicao.periodo_fim:%d/%m/%Y}"
            + parcelas
        ),
    )
    # Do lado da receita a medição é faturada ao contratante: conta a receber.
    if contrato.lado == LadoContrato.RECEITA:
        conta_id = ContaReceber.objects.create(cliente_id=contrato.cliente_id, **comum).pk
    else:
        conta_id = ContaPagar.objects.create(fornecedor_id=contrato.fornecedor_id, **comum).pk
    if avisar:
        avisar_erp(
            contrato,
            titulo=f"Medição {medicao.numero} do contrato {contrato.numero} virou título",
            mensagem=(
                f"Título {conta_id} de R$ {comum['valor']} a "
                f"{'receber de' if contrato.lado == LadoContrato.RECEITA else 'pagar a'} "
                f"{contrato.parte_nome}, vencendo em {comum['data_vencimento']:%d/%m/%Y}."
            ),
        )
    return conta_id


def _comum_do_titulo(medicao: Medicao, *, valor: Decimal, descricao: str) -> dict:
    contrato = medicao.contrato
    return {
        "tenant_id": medicao.tenant_id,
        "empreendimento_id": getattr(contrato.obra, "empreendimento_id", None),
        "obra_id": contrato.obra_id,  # D.1.4: a medição já sabe de qual obra é
        "descricao": descricao,
        "valor": valor,
        "data_emissao": timezone.localdate(),
        "data_vencimento": timezone.localdate() + timedelta(
            days=contrato.prazo_pagamento_dias or 0
        ),
    }


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
                  retencao_percentual_nova: Decimal | None = None,
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
        retencao_percentual_nova=retencao_percentual_nova,
        criado_por=por or "",
    )
    if itens:
        reescrever_itens_do_aditivo(aditivo=aditivo, itens=itens)
    return aditivo


#: O que o cabeçalho do aditivo em rascunho aceita mudar.
_CAMPOS_DO_CABECALHO = (
    "objeto", "justificativa", "data_assinatura", "nova_data_fim",
    "retencao_percentual_nova",
)


def editar_aditivo(*, aditivo: AditivoContrato, **campos) -> AditivoContrato:
    """O cabeçalho do rascunho — objeto, justificativa, datas e a retenção nova.

    *Achado do dono, 11/10/2026:* o aditivo nascia só com objeto e
    justificativa, e depois "não tinha como fazer nada". Agora ele se monta
    como um contrato: o cabeçalho aqui, as linhas em `reescrever_itens_do_aditivo`.
    """
    if aditivo.status != AditivoContrato.Status.RASCUNHO:
        raise ValidationError(
            f"Só o rascunho se edita (este aditivo está "
            f"{aditivo.get_status_display().lower()})."
        )
    mudou = []
    for campo in _CAMPOS_DO_CABECALHO:
        if campo in campos:
            setattr(aditivo, campo, campos[campo])
            mudou.append(campo)
    if "justificativa" in campos and not (aditivo.justificativa or "").strip():
        raise ValidationError("O aditivo exige justificativa.")
    if mudou:
        aditivo.save(update_fields=mudou)
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
            retencao_percentual=(
                None if linha.get("retencao_percentual") is None
                else Decimal(str(linha["retencao_percentual"]))
            ),
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
    if not linhas and aditivo.nova_data_fim is None and aditivo.retencao_percentual_nova is None:
        problemas.append(
            "O aditivo não muda nada: sem linhas, sem nova data de fim e sem nova retenção."
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
                retencao_percentual=linha.retencao_percentual,
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
        # A regra de retenção própria da linha vale para qualquer ação — o item
        # novo já nasceu com ela, acima.
        if (linha.retencao_percentual is not None
                and linha.acao != AcaoAditivo.INCLUSAO and linha.item_contrato_id):
            ItemContrato.objects.filter(pk=linha.item_contrato_id).update(
                retencao_percentual=linha.retencao_percentual,
            )

    mudou = []
    if aditivo.nova_data_fim is not None:
        contrato.data_fim = aditivo.nova_data_fim
        mudou.append("data_fim")
    if aditivo.retencao_percentual_nova is not None:
        # A cláusula muda daqui para frente: a medição copia o percentual no
        # dia em que nasce, então as já abertas seguem com o de antes.
        contrato.retencao_percentual = aditivo.retencao_percentual_nova
        mudou.append("retencao_percentual")
    if mudou:
        contrato.save(update_fields=[*mudou, "atualizado_em"])

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
            campo = ("conta_receber_ref" if liberacao.contrato.lado == LadoContrato.RECEITA
                     else "conta_pagar_ref")
            setattr(liberacao, campo, conta_id)
            campos.append(campo)

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
    from moduloerp.models import ContaPagar, ContaReceber

    contrato = liberacao.contrato
    comum = {
        "tenant_id": liberacao.tenant_id,
        "empreendimento_id": getattr(contrato.obra, "empreendimento_id", None),
        "obra_id": contrato.obra_id,  # D.1.4: a medição já sabe de qual obra é
        "descricao": (
            f"Liberação de retenção ({contrato.get_retencao_natureza_display()}) · "
            f"contrato {contrato.numero} · {contrato.obra.nome_obra} · "
            f"{liberacao.condicao_atendida[:120]}"
        ),
        "valor": liberacao.valor,
        "data_emissao": timezone.localdate(),
        "data_vencimento": liberacao.data,
    }
    # Do lado da receita é a caução que o contratante devolve: a receber.
    if contrato.lado == LadoContrato.RECEITA:
        conta_id = ContaReceber.objects.create(cliente_id=contrato.cliente_id, **comum).pk
    else:
        conta_id = ContaPagar.objects.create(fornecedor_id=contrato.fornecedor_id, **comum).pk
    avisar_erp(
        contrato,
        titulo=f"Retenção liberada no contrato {contrato.numero} virou título",
        mensagem=f"Título {conta_id} de R$ {liberacao.valor}, vencendo em {liberacao.data:%d/%m/%Y}.",
    )
    return conta_id


# --- Cancelamento: retirar o documento E o título que ele gerou -------------


@transaction.atomic
def cancelar_medicao(*, medicao: Medicao, motivo: str = "", por: str = "",
                     usuario=None) -> dict:
    """Retira a medição — **e leva o título do ERP junto**.

    **O defeito que isto conserta.** O `cancelar/` mexia só no PDCA: a medição
    virava `CANCELADA` e a `ContaPagar` que ela gerou continuava aberta no
    financeiro, com a descrição apontando para uma medição que não existe mais.
    O empreiteiro recebia por um boletim retirado, e a conciliação só percebia
    quando alguém fosse explicar o título — quer dizer, no fim do mês, quando já
    tinha sido pago.

    **As três portas, e por que elas são diferentes:**

    - **rascunho / em aprovação** — não há título. Cancelar é retirar o
      documento antes de ele produzir efeito, e sempre pôde;
    - **aprovada com título ainda ABERTO** — cancela os dois no mesmo gesto e na
      mesma transação. É o caso que estava quebrado, e é o comum: a medição
      aprovada de manhã que se descobre errada à tarde;
    - **aprovada com título pago (parcial ou quitado)** — **recusa**, e manda
      retificar *(decisão do dono, 15/09/2026)*. O dinheiro que saiu do caixa
      não se apaga cancelando o papel que o justificou: existe uma `Transacao`
      lançada, e um título cancelado com baixa em cima é um buraco que a
      conciliação não fecha nunca. A medição **retificadora** é o caminho — ela
      corrige o valor por um documento novo, que é como o resto desta casa já
      conserta o que virou dinheiro.

    **Motivo obrigatório quando havia título.** É a mesma régua da retificação e
    da reabertura da semana: o que produziu efeito no mundo não se desfaz em
    silêncio. Cancelar um rascunho não pede motivo — não houve efeito.
    """
    if medicao.status in (Medicao.Status.CANCELADA, Medicao.Status.REPROVADA):
        raise ValidationError(
            f"A medição já está {medicao.get_status_display().lower()} e não "
            f"se cancela de novo — ela já não produz efeito."
        )

    era_aprovada = medicao.status == Medicao.Status.APROVADA
    if medicao.retifica_id is not None:
        if era_aprovada:
            raise ValidationError(
                f"A medição {medicao.numero} já substituiu a medição "
                f"{medicao.retifica.numero} e mexeu no financeiro. Para corrigir de "
                f"novo, retifique esta — a correção da correção também é documento."
            )
        # *Decisão do dono, 11/10/2026:* retificadora retirada antes de valer não
        # deixa rastro — nunca produziu título nem efeito, e guardá-la como
        # "cancelada" era só lixo no contrato. A escada dela vai junto (a
        # `GenericRelation` apaga os pedidos).
        pk, numero = medicao.pk, medicao.numero
        medicao.delete()
        return {
            "medicao": pk, "numero": numero, "status": "excluida",
            "excluida": True, "titulo_cancelado": None, "era_aprovada": False,
        }
    titulo = titulo_da_medicao(medicao) if era_aprovada else None
    motivo = (motivo or "").strip()

    if era_aprovada and not motivo:
        raise ValidationError(
            "Cancelar uma medição aprovada exige motivo por escrito. Ela já "
            "virou título a pagar, e o financeiro precisa da frase que explica "
            "por que o título sumiu."
        )

    if titulo is not None:
        #: **O título pago tranca a porta.** `valor_pago > 0` cobre a baixa
        #: parcial, que é o caso traiçoeiro: o status ainda é `PARCIAL`, o
        #: título parece vivo, e já saiu dinheiro.
        if titulo.valor_pago > 0 or titulo.status in ("QUITADO", "PARCIAL"):
            raise ValidationError(
                f"O título {titulo.pk} desta medição já recebeu "
                f"R$ {titulo.valor_pago} de baixa "
                f"({titulo.get_status_display().lower()}). Medição que já foi "
                f"paga não se cancela: o dinheiro saiu do caixa e existe uma "
                f"transação lançada em cima dele. Para corrigir o valor, abra "
                f"uma medição retificadora — ela aponta para esta, e a soma das "
                f"duas dá o número certo."
            )
        if titulo.status != "CANCELADO":
            titulo.status = "CANCELADO"
            titulo.save(update_fields=["status"])
            from nucleo.auditoria import registrar_auditoria

            #: Auditoria dos dois lados: o cancelamento do título é evento
            #: financeiro da mesma família da baixa, e a origem dele está noutro
            #: módulo. Sem esta linha, quem lê o log do ERP vê um título sumir
            #: sem ator nem porquê.
            registrar_auditoria(
                acao="cancelar", instance=titulo, usuario=usuario,
                detalhes={
                    "origem": "pdca.medicao.cancelar",
                    "medicao": medicao.pk,
                    "valor": str(titulo.valor),
                    "motivo": motivo[:500],
                },
            )
            avisar_erp(
                medicao.contrato,
                titulo=(
                    f"Título {titulo.pk} cancelado — medição {medicao.numero} do "
                    f"contrato {medicao.contrato.numero} foi retirada"
                ),
                mensagem=f"R$ {titulo.valor}. Motivo: {motivo}",
            )

    medicao.status = Medicao.Status.CANCELADA
    medicao.congelada_em = timezone.now()
    campos = ["status", "congelada_em"]
    if motivo:
        medicao.observacao = (
            f"{medicao.observacao}\n" if medicao.observacao else ""
        ) + f"Cancelada por {por or 'usuário'}: {motivo}"
        campos.append("observacao")
    medicao.save(update_fields=campos)

    return {
        "medicao": medicao.pk,
        "status": medicao.status,
        "titulo_cancelado": titulo.pk if titulo is not None else None,
        "era_aprovada": era_aprovada,
    }


# --- Retificação e leitura do contrato -------------------------------------


@transaction.atomic
def retificar(*, medicao: Medicao, motivo: str, por: str = "") -> Medicao:
    """Abre a medição que corrige uma aprovada (§11.5) — **a medição inteira**.

    *Decisão do dono, 11/10/2026:* a retificadora **substitui** a original. Nasce
    como cópia dela — linhas, estoque, descontos, custo, retenção e taxa do dia
    em que a original foi feita (a correção é do mesmo período) — e o gestor
    corrige o que estava errado. Aprovada, a original vira `RETIFICADA` e sai de
    toda soma (`_fechar_retificacao`); só uma medição vale por período.

    Enquanto a retificadora não é aprovada, a original continua valendo — e se
    ela for retirada antes disso, é apagada de vez (`cancelar_medicao`).
    """
    if medicao.status != Medicao.Status.APROVADA:
        raise ValidationError(
            "Só medição aprovada se retifica. Rascunho se edita; medição "
            "reprovada, cancelada ou já retificada não vale mais."
        )
    if not (motivo or "").strip():
        raise ValidationError("A retificação exige motivo.")
    ja_existe = Medicao.objects.filter(retifica=medicao).exclude(
        status__in=(Medicao.Status.CANCELADA, Medicao.Status.REPROVADA)
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
    nova = Medicao.objects.create(
        tenant_id=contrato.tenant_id,
        contrato=contrato,
        numero=proximo,
        periodo_inicio=medicao.periodo_inicio,
        periodo_fim=medicao.periodo_fim,
        retifica=medicao,
        retencao_percentual_aplicado=medicao.retencao_percentual_aplicado,
        custo_reembolsavel=medicao.custo_reembolsavel,
        taxa_administracao_aplicada=medicao.taxa_administracao_aplicada,
        custo_origem=medicao.custo_origem,
        valor_reajuste=medicao.valor_reajuste,
        reajuste_memoria=medicao.reajuste_memoria,
        reajuste_provisorio=medicao.reajuste_provisorio,
        apurada_por=por or "",
        observacao=f"Retifica a medição {medicao.numero}: {motivo}",
    )
    ItemMedicao.objects.bulk_create([
        ItemMedicao(
            tenant_id=nova.tenant_id, medicao=nova,
            item_contrato_id=linha.item_contrato_id,
            quantidade=linha.quantidade,
            quantidade_estocada=linha.quantidade_estocada,
            quantidade_proposta=linha.quantidade_proposta,
            preco_unitario=linha.preco_unitario,
            percentual_avanco_periodo=linha.percentual_avanco_periodo,
            retencao_percentual=linha.retencao_percentual,
            origem=linha.origem,
            observacao=linha.observacao,
        )
        for linha in medicao.itens.all()
    ])
    DeducaoMedicao.objects.bulk_create([
        DeducaoMedicao(
            tenant_id=nova.tenant_id, medicao=nova, tipo=d.tipo,
            descricao=d.descricao, base_calculo=d.base_calculo,
            percentual=d.percentual, valor=d.valor,
        )
        for d in medicao.deducoes.all()
    ])

    return nova


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
    liquido_aprovado = _ZERO
    estocado_valor = _ZERO
    for medicao in contrato.medicoes.all():
        totais = totais_da_medicao(medicao)
        bruto = totais["bruto"]
        if medicao.retifica_id is not None and medicao.status != Medicao.Status.APROVADA:
            # A retificadora que ainda não vale só **muda** o que a original
            # mede — somar a corrigida inteira contaria o período duas vezes.
            bruto -= totais_da_medicao(medicao.retifica)["bruto"]
        por_status[medicao.status] = por_status.get(medicao.status, _ZERO) + bruto
        if medicao.status == Medicao.Status.APROVADA:
            deducoes_aprovadas += totais["total_deducoes"]
            # A retificada está fora (status próprio): a retificadora já é a
            # medição corrigida inteira.
            liquido_aprovado += totais["liquido"]

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
        "liquido_aprovado": liquido_aprovado,
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
        "medicoes": contrato.medicoes.filter(retifica__isnull=True).count(),
        "aditivos": contrato.aditivos.filter(
            status=AditivoContrato.Status.APROVADO,
        ).count(),
        "aditivos_abertos": abertos,
        "periodo_sugerido": sugerir_periodo(contrato),
    }


def ficha_do_contrato(contrato: ContratoObra) -> dict:
    """**A ficha do contrato** — tudo o que aconteceu com ele, numa leitura.

    *Achado do dono, 11/10/2026:* "deveria poder ver os detalhes do contrato,
    não só uma medição". O saldo já vem na carteira; o que faltava é o que mora
    fora do PDCA e o que é história:

    - **o financeiro** — os títulos que as medições geraram no ERP, quanto já
      saiu e quanto falta (um título é contado uma vez, mesmo quando a
      retificadora aponta para o da original já pago);
    - **a linha do tempo** — medições (inclusive a retificada, que aponta para
      a que a substituiu), aditivos e liberações de retenção, em ordem.
    """
    eventos: list[dict] = []
    titulos: dict[int, dict] = {}
    substituta: dict[int, int] = {}
    medicoes = list(contrato.medicoes.select_related("retifica").order_by("numero"))
    for m in medicoes:
        if m.retifica_id is not None and m.status in _EM_VOO:
            substituta[m.retifica_id] = m.numero

    for m in medicoes:
        totais = totais_da_medicao(m)
        titulo = None
        if m.status in (Medicao.Status.APROVADA, Medicao.Status.RETIFICADA):
            titulo = estado_do_titulo(m)
            if titulo is not None:
                titulos[titulo["conta_pagar"]] = titulo
        eventos.append({
            "tipo": "medicao",
            "id": m.pk,
            "numero": m.numero,
            "data": (m.congelada_em or m.apurada_em).date(),
            "rotulo": f"Medição {m.numero}",
            "detalhe": (
                f"{m.periodo_inicio:%d/%m/%Y} a {m.periodo_fim:%d/%m/%Y}"
                + (f" · retifica a {m.retifica.numero}" if m.retifica_id else "")
                + (f" · substituída pela {substituta[m.pk]}" if m.pk in substituta else "")
            ),
            "status": m.status,
            "status_rotulo": m.get_status_display(),
            "bruto": totais["bruto"],
            "liquido": totais["liquido"],
            "titulo": titulo,
        })

    for a in contrato.aditivos.all():
        resumo = resumo_do_aditivo(a)
        eventos.append({
            "tipo": "aditivo",
            "id": a.pk,
            "numero": a.numero,
            "data": a.data_assinatura or a.criado_em.date(),
            "rotulo": f"Aditivo {a.numero}",
            "detalhe": a.objeto[:140],
            "status": a.status,
            "status_rotulo": a.get_status_display(),
            "bruto": resumo["liquido"],
            "liquido": resumo["liquido"],
            "titulo": None,
        })

    for lib in contrato.liberacoes.all():
        eventos.append({
            "tipo": "liberacao",
            "id": lib.pk,
            "numero": None,
            "data": lib.data,
            "rotulo": "Liberação de retenção",
            "detalhe": lib.condicao_atendida[:140],
            "status": lib.status,
            "status_rotulo": lib.get_status_display(),
            "bruto": lib.valor,
            "liquido": lib.valor,
            "titulo": None,
        })

    eventos.sort(key=lambda e: (e["data"], e["tipo"] != "aditivo", e["numero"] or 0))
    vivos = [t for t in titulos.values() if t["status"] != "CANCELADO"]

    # Os itens com o medido de cada um — o mesmo acumulado da trava da medição
    # (aprovadas e em escada, a retificada fora).
    itens = list(contrato.itens.all())
    atual = contratado_atual_por_item(contrato, itens)
    medido = medido_por_item(contrato)
    linhas = []
    for item in sorted(itens, key=lambda i: (i.ordem, i.codigo)):
        contratado = atual.get(item.pk, item.quantidade_contratada)
        ja = medido.get(item.pk, _ZERO)
        linhas.append({
            "item_contrato_id": item.pk,
            "codigo": item.codigo,
            "descricao": item.descricao,
            "unidade": item.unidade,
            "preco_unitario": item.preco_unitario,
            "contratado": contratado,
            "medido": ja,
            "saldo": contratado - ja,
            "percentual": (
                _dinheiro(ja * Decimal("100") / contratado) if contratado else None
            ),
            "valor_contratado": _dinheiro(contratado * item.preco_unitario),
            "valor_medido": _dinheiro(ja * item.preco_unitario),
        })

    return {
        "contrato_id": contrato.pk,
        "lado": contrato.lado,
        "itens": linhas,
        "financeiro": {
            "titulos": len(vivos),
            "emitido": _dinheiro(sum((t["valor"] for t in vivos), _ZERO)),
            "pago": _dinheiro(sum((t["valor_pago"] for t in vivos), _ZERO)),
            "em_aberto": _dinheiro(sum(
                (max(t["saldo_aberto"], _ZERO) for t in vivos), _ZERO,
            )),
        },
        "linha_do_tempo": eventos,
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
    # A retificadora corrige uma medição; não é uma medição a mais.
    em_voo = contrato.medicoes.filter(status__in=_EM_VOO, retifica__isnull=True).count()
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


def ativar_contrato(contrato: ContratoObra) -> ContratoObra:
    """Rascunho → vigente. *Achado do dono, 10/10/2026:* "o contrato de
    medição fica em rascunho eternamente" — o status só mudava pela API, e
    contrato em rascunho não aceita medição.

    Vigente precisa do que a medição usa: no **unitário**, ao menos um item na
    planilha; no **global** e na **administração**, o valor fechado (a
    constraint do model já o exige). A planilha continua editável depois — a
    trava dela é a primeira medição, não o status (`planilha_editavel`).
    """
    if contrato.status != ContratoObra.Status.RASCUNHO:
        raise ValidationError(
            f"O contrato já está {contrato.get_status_display().lower()}."
        )
    if contrato.regime == RegimeContrato.UNITARIO and not contrato.itens.exists():
        raise ValidationError(
            "O contrato por preço unitário mede item a item: monte a planilha antes "
            "de torná-lo vigente."
        )
    if contrato.regime != RegimeContrato.UNITARIO and not contrato.valor_global:
        raise ValidationError("Informe o valor fechado do contrato antes de torná-lo vigente.")
    contrato.status = ContratoObra.Status.VIGENTE
    contrato.save(update_fields=["status", "atualizado_em"])
    return contrato


def fontes_da_planilha(contrato: ContratoObra) -> dict:
    """De onde a planilha contratual pode puxar itens — **pronto para escolher**.

    *Decisão do dono, 10/10/2026:* os itens vêm "do orçamento, das atividades do
    plano, colar do Excel ou digitar". Aqui vão as duas primeiras listas: os
    itens analíticos do orçamento vigente da obra (descrição, unidade,
    quantidade e preço unitário com BDI) e as atividades folha do plano em
    vigor. O que já está no contrato vem marcado, para a tela não oferecer de
    novo. As mesmas listas servem ao seletor de vínculo de cada linha.
    """
    from moduloorcamento.models import ItemOrcado
    from moduloorcamento.planilha import orcamento_vigente

    from .etapas import plano_em_vigor

    ja_orcados = set(contrato.itens.exclude(item_orcado=None).values_list("item_orcado_id", flat=True))
    ja_atividades = set(contrato.itens.exclude(atividade=None).values_list("atividade_id", flat=True))

    orcamento = orcamento_vigente(contrato.tenant_id, contrato.obra_id)
    itens_orcados = []
    if orcamento is not None:
        for item in (ItemOrcado.objects
                     .filter(orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO)
                     .order_by("ordem", "codigo_eap", "item_orcado_id")):
            quantidade = item.quantidade or _ZERO
            preco = (item.total_com_bdi / quantidade) if quantidade else _ZERO
            itens_orcados.append({
                "item_orcado": item.pk, "codigo": item.codigo_eap, "descricao": item.descricao,
                "unidade": item.unidade, "quantidade": quantidade,
                "preco_unitario": preco.quantize(Decimal("0.0001")),
                "ja_no_contrato": item.pk in ja_orcados,
            })

    plano = plano_em_vigor(contrato.obra_id, contrato.tenant_id)
    atividades = []
    if plano is not None:
        com_filhos = set(plano.atividades.exclude(pai=None).values_list("pai_id", flat=True))
        for a in plano.atividades.filter(eh_marco=False).order_by("ordem", "codigo"):
            if a.pk in com_filhos:
                continue
            atividades.append({
                "atividade": a.pk, "codigo": a.codigo, "nome": a.nome,
                "ja_no_contrato": a.pk in ja_atividades,
            })
    return {
        "orcamento": None if orcamento is None else {"id": orcamento.pk, "descricao": str(orcamento)},
        "itens_orcados": itens_orcados,
        "plano": None if plano is None else {"id": plano.pk, "versao": plano.versao},
        "atividades": atividades,
    }


@transaction.atomic
def incluir_na_planilha(contrato: ContratoObra, linhas: list[dict]) -> list[ItemContrato]:
    """Muitas linhas de uma vez — do orçamento, do plano ou coladas do Excel.

    Tudo ou nada, e a recusa diz a linha: um código repetido (no contrato ou no
    próprio lote), quantidade zero, vínculo de outra obra. O teto do plano vale
    para o lote inteiro.
    """
    aberta, motivo = planilha_editavel(contrato)
    if not aberta:
        raise ValidationError(motivo)
    if not linhas:
        raise ValidationError("Nenhuma linha para incluir.")
    validar_teto_de_itens(contrato, acrescentando=len(linhas))

    existentes = set(contrato.itens.values_list("codigo", flat=True))
    vistos: set[str] = set()
    problemas: list[str] = []
    ordem = (contrato.itens.aggregate(m=Max("ordem"))["m"] or 0)
    novos = []
    from moduloorcamento.models import ItemOrcado

    for n, linha in enumerate(linhas, start=1):
        codigo = str(linha.get("codigo") or "").strip()[:40]
        descricao = str(linha.get("descricao") or "").strip()[:255]
        try:
            quantidade = Decimal(str(linha.get("quantidade_contratada") or "0").replace(",", "."))
            preco = Decimal(str(linha.get("preco_unitario") or "0").replace(",", "."))
        except Exception:  # noqa: BLE001 — número ilegível vira recusa com a linha
            problemas.append(f"Linha {n}: quantidade ou preço ilegível.")
            continue
        if not codigo or not descricao:
            problemas.append(f"Linha {n}: falta o código ou a descrição.")
            continue
        if codigo in existentes or codigo in vistos:
            problemas.append(f"Linha {n}: o item {codigo} já está na planilha.")
            continue
        if quantidade <= 0:
            problemas.append(f"Linha {n} ({codigo}): a quantidade precisa ser maior que zero.")
            continue
        if preco < 0:
            problemas.append(f"Linha {n} ({codigo}): preço negativo não é item — é aditivo de supressão.")
            continue
        item_orcado_id = linha.get("item_orcado") or None
        atividade_id = linha.get("atividade") or None
        if item_orcado_id and not ItemOrcado.objects.filter(
            pk=item_orcado_id, orcamento__obra_id=contrato.obra_id,
        ).exists():
            problemas.append(f"Linha {n} ({codigo}): o item orçado não é desta obra.")
            continue
        if atividade_id and not Atividade.objects.filter(
            pk=atividade_id, cronograma__obra_id=contrato.obra_id,
        ).exists():
            problemas.append(f"Linha {n} ({codigo}): a atividade não é desta obra.")
            continue
        vistos.add(codigo)
        ordem += 1
        novos.append(ItemContrato(
            tenant_id=contrato.tenant_id, contrato=contrato, codigo=codigo,
            descricao=descricao, unidade=str(linha.get("unidade") or "").strip()[:20],
            quantidade_contratada=quantidade, preco_unitario=preco, ordem=ordem,
            item_orcado_id=item_orcado_id, atividade_id=atividade_id,
        ))
    if problemas:
        raise ValidationError(problemas)
    return ItemContrato.objects.bulk_create(novos)


# ---------------------------------------------------------------------------
# 12. O Last Planner (PDCA.5) — make-ready, compromisso e causa
# ---------------------------------------------------------------------------
# As três seções abaixo implementam o ciclo semanal do LPS, e a ordem delas é a
# ordem em que a reunião acontece: primeiro se olha o que trava (12.1), depois
# se assume o que vai sair (12.2), e no fim da semana se julga e se aprende
# (12.3). O PPC é derivado no ponto de leitura, nunca gravado — §4.9 da planta.

# --- 12.1 O catálogo de causas ----------------------------------------------

#: As causas de fábrica. Cobrem o que a literatura do LPS registra como
#: recorrente em obra brasileira, e existem para que a primeira semana de uso já
#: produza ranking — um catálogo vazio faria a primeira reunião inventar rótulos
#: livres, que é exatamente o que o modelo existe para impedir.
#:
#: **O código é estável e o nome é editável.** O tenant renomeia "MAT-FALTA" para
#: o vocabulário da casa dele; o que não muda é o código, porque é por ele que a
#: comparação entre obras (e, um dia, entre empresas na Esfera de Rede) se faz.
CAUSAS_DE_FABRICA: tuple[tuple[str, str, str], ...] = (
    # (codigo, nome, categoria)
    ("PLAN-MAL-DIM", "Serviço mal dimensionado no plano", "planejamento"),
    ("PLAN-PRE-REQ", "Pré-requisito não concluído", "planejamento"),
    ("PLAN-MUDANCA", "Mudança de prioridade na semana", "planejamento"),
    # D192 — a semana perdida por interdição de segurança caía em `EXTERNO`, ao
    # lado da chuva, e o ranking empurrava para "não foi culpa nossa" o caso em
    # que foi. Liberar a frente com segurança é trabalho do make-ready, e por
    # isso a causa mora em planejamento — e não num nono valor de categoria,
    # que mexeria no eixo de todo gráfico de PPC já publicado.
    ("SEG-INTERD", "Frente interditada por risco de segurança", "planejamento"),
    ("MO-FALTA", "Falta de efetivo", "mao_de_obra"),
    ("MO-PRODUT", "Produtividade abaixo da prevista", "mao_de_obra"),
    ("MO-ABSENT", "Absenteísmo", "mao_de_obra"),
    ("MAT-FALTA", "Material não chegou", "material"),
    ("MAT-ERRADO", "Material errado ou fora de especificação", "material"),
    ("EQP-INDISP", "Equipamento indisponível", "equipamento"),
    ("EQP-QUEBRA", "Quebra de equipamento", "equipamento"),
    ("PROJ-FALTA", "Projeto não liberado ou incompleto", "projeto"),
    ("PROJ-ALTER", "Alteração de projeto", "projeto"),
    ("EXT-CLIMA", "Chuva ou condição climática", "externo"),
    ("EXT-CLIENTE", "Decisão pendente do cliente", "externo"),
    ("EXT-ORGAO", "Liberação de órgão externo", "externo"),
    ("QUA-RETRAB", "Retrabalho por não-conformidade", "qualidade"),
)


def semear_causas_de_fabrica(tenant_id) -> int:
    """Põe o catálogo de fábrica no tenant. Idempotente.

    Chamada no primeiro uso da programação (e não numa migration de dados)
    porque tenant novo nasce depois da migration, e um catálogo que só existisse
    para quem já estava no banco deixaria o cliente seguinte sem ranking.
    """
    existentes = set(
        CausaNaoCumprimento.objects.filter(tenant_id=tenant_id)
        .values_list("codigo", flat=True)
    )
    novas = [
        CausaNaoCumprimento(
            tenant_id=tenant_id, codigo=codigo, nome=nome,
            categoria=categoria, de_fabrica=True,
        )
        for codigo, nome, categoria in CAUSAS_DE_FABRICA
        if codigo not in existentes
    ]
    if novas:
        CausaNaoCumprimento.objects.bulk_create(novas)
    return len(novas)


def validar_teto_de_causas(tenant_id, *, acrescentando: int = 1) -> None:
    """O catálogo só serve enquanto for escolhível — §5.5j do `planos.py`."""
    atual = CausaNaoCumprimento.objects.filter(tenant_id=tenant_id).count()
    if atual + acrescentando > PDCA_TETO_CAUSAS_POR_TENANT:
        raise ValidationError(
            f"O catálogo de causas do seu plano vai até "
            f"{_milhar(PDCA_TETO_CAUSAS_POR_TENANT)} itens, e você já tem "
            f"{_milhar(atual)}. Desative as causas que não se usam mais — elas "
            f"continuam legíveis no histórico — em vez de acrescentar novas: "
            f"uma lista que ninguém percorre até o fim faz o ranking de causas "
            f"deixar de ranquear."
        )


# --- 12.2 O make-ready: a restrição ------------------------------------------


def restricoes_abertas_por_atividade(atividade_ids: list[int],
                                     *, tenant_id) -> dict[int, int]:
    """`{atividade_id: quantas travas abertas}` — **em uma consulta**.

    Existe como agregado, e não como propriedade da atividade, porque quem
    pergunta isso é o quadro inteiro de uma vez: 300 cartões perguntando cada um
    "estou travado?" seriam 300 consultas para desenhar uma parede.
    """
    if not atividade_ids:
        return {}
    linhas = (
        Restricao.objects.filter(
            tenant_id=tenant_id,
            atividade_id__in=atividade_ids,
            status=Restricao.Status.ABERTA,
        )
        .values("atividade_id")
        .annotate(n=Count("restricao_id"))
    )
    return {linha["atividade_id"]: linha["n"] for linha in linhas}


def validar_teto_de_restricoes(obra_id, *, tenant_id,
                               acrescentando: int = 1) -> None:
    """O *constraint log* existe para ser zerado — §5.5j do `planos.py`."""
    atual = Restricao.objects.filter(
        tenant_id=tenant_id,
        status=Restricao.Status.ABERTA,
        atividade__cronograma__obra_id=obra_id,
    ).count()
    if atual + acrescentando > PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA:
        raise ValidationError(
            f"Esta obra já tem {_milhar(atual)} restrições abertas, e o teto do "
            f"seu plano é {_milhar(PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA)}. O "
            f"log de restrição é para zerar, não para acumular: remova ou "
            f"cancele as que já não travam nada antes de abrir mais."
        )


@transaction.atomic
def remover_restricao(*, restricao: Restricao, por: str = "",
                      nota: str = "") -> Restricao:
    """O ato que conclui o make-ready — **e ele exige dizer como**.

    A `nota_remocao` é obrigatória de propósito. Uma restrição que some sem
    explicação deixa a reunião seguinte sem saber se ela foi resolvida ou
    esquecida, e é dessa nota que sai a única leitura que faz o log valer a pena:
    *como esta obra costuma destravar a si mesma*.
    """
    if restricao.status != Restricao.Status.ABERTA:
        raise ValidationError(
            f"Esta restrição está {restricao.get_status_display().lower()} — só "
            f"uma restrição aberta pode ser removida."
        )
    if not (nota or "").strip():
        raise ValidationError(
            "Diga como a restrição foi removida. Sem isso, a reunião da semana "
            "que vem não sabe se ela foi resolvida ou apenas esquecida."
        )
    restricao.status = Restricao.Status.REMOVIDA
    restricao.removida_em = timezone.now()
    restricao.removida_por = por or ""
    restricao.nota_remocao = nota.strip()
    restricao.save(update_fields=[
        "status", "removida_em", "removida_por", "nota_remocao",
    ])
    return restricao


@transaction.atomic
def reabrir_restricao(*, restricao: Restricao, por: str = "") -> Restricao:
    """A trava que voltou: removida → **aberta de novo**.

    O material que "chegou" era o errado, o clique em *Resolvida* foi na linha
    errada. Desfazer a remoção é corrigir o log, não reescrevê-lo: a reabertura
    fica carimbada (quem, quando, quantas vezes) e a nota da remoção anterior
    continua lá — é ela que explica por que alguém achou que estava resolvida.

    Só a **removida** volta. A cancelada foi declarada "não era restrição";
    trazê-la de volta é registrar uma nova.
    """
    if restricao.status != Restricao.Status.REMOVIDA:
        raise ValidationError(
            f"Esta restrição está {restricao.get_status_display().lower()} — só "
            f"uma restrição resolvida pode voltar a ser aberta."
        )
    obra_id = getattr(getattr(restricao.atividade, "cronograma", None), "obra_id", None)
    if obra_id:
        validar_teto_de_restricoes(obra_id, tenant_id=restricao.tenant_id)
    restricao.status = Restricao.Status.ABERTA
    restricao.reaberta_em = timezone.now()
    restricao.reaberta_por = por or ""
    restricao.vezes_reaberta = (restricao.vezes_reaberta or 0) + 1
    restricao.save(update_fields=[
        "status", "reaberta_em", "reaberta_por", "vezes_reaberta",
    ])
    return restricao


#: Os tipos de restrição que se destravam **comprando** — e o tipo de demanda
#: que cada um abre no Suprimentos. Equipamento é quase sempre locação e mão de
#: obra é empreitada: as duas são contratação de serviço, não compra de insumo.
TIPOS_QUE_VIRAM_COMPRA = {
    TipoRestricao.MATERIAL: "material",
    TipoRestricao.EQUIPAMENTO: "servico",
    TipoRestricao.MAO_DE_OBRA: "servico",
}


@transaction.atomic
def gerar_demanda_scm(*, restricao: Restricao, quantidade=None,
                      unidade: str = "", solicitante=None) -> int:
    """Restrição de material → **`Demanda` no SCM**. O seam da §6, vivo.

    **Importa tarde, pela mesma razão do título no ERP:** a §7 da planta diz que
    o PDCA *não compra nem cota*. Uma importação no topo faria o planejamento
    deixar de carregar numa instalação que não contrate o SCM — e o seam existe
    para ser atravessável nos dois sentidos, ou em nenhum.

    **Só o que se destrava comprando** (`TIPOS_QUE_VIRAM_COMPRA`): material,
    equipamento (locação) e mão de obra (empreitada). Restrição de projeto não
    vira compra (vira RFI, que é da Prancheta), e restrição de clima não vira
    nada. Oferecer o botão em todas faria a demanda virar lixeira de pendência.

    **Uma restrição gera uma demanda.** Chamar de novo devolve a que já existe:
    o botão fica na tela e alguém clica duas vezes, e duas demandas para a mesma
    falta produzem duas cotações e, no fim, duas compras do mesmo material.
    """
    from moduloscm.models import Demanda, ItemDemanda

    if restricao.demanda_scm_id:
        return restricao.demanda_scm_id
    if restricao.tipo not in TIPOS_QUE_VIRAM_COMPRA:
        raise ValidationError(
            f"Restrição de {restricao.get_tipo_display().lower()} não vira "
            f"compra. Só material, equipamento e mão de obra geram demanda no "
            f"Suprimentos — o resto se destrava com projeto, decisão ou licença, "
            f"e forçar uma demanda aqui encheria a fila de compras de pendência "
            f"que ninguém compra."
        )
    if restricao.status != Restricao.Status.ABERTA:
        raise ValidationError(
            "Só restrição aberta vira demanda — a que já foi removida não "
            "trava mais nada."
        )

    atividade = restricao.atividade
    obra = getattr(getattr(atividade, "cronograma", None), "obra", None)
    demanda = Demanda.objects.create(
        tenant_id=restricao.tenant_id,
        tipo=TIPOS_QUE_VIRAM_COMPRA[restricao.tipo],
        status=Demanda.Status.RASCUNHO,
        origem=Demanda.Origem.RESTRICAO,
        solicitante=solicitante if getattr(solicitante, "pk", None) else None,
        observacao=(
            f"Restrição #{restricao.restricao_id} · "
            f"{restricao.get_tipo_display()} · atividade "
            f"{atividade.codigo or atividade.pk} — {atividade.nome}"
            + (f" · obra {obra.nome_obra}" if obra else "")
            + (f" · prazo {restricao.prazo:%d/%m/%Y}" if restricao.prazo else "")
        ),
    )
    ItemDemanda.objects.create(
        tenant_id=restricao.tenant_id,
        demanda=demanda,
        descricao_servico=restricao.descricao[:255],
        # `1` quando ninguém digitou: a demanda nasce em rascunho e quem compra
        # ajusta o número. Gravar zero faria a cotação sair pedindo nada.
        quantidade=quantidade if quantidade is not None else Decimal("1"),
        unidade=unidade or "",
    )
    restricao.demanda_scm = demanda
    restricao.save(update_fields=["demanda_scm"])
    from nucleo.models import Notificacao
    from nucleo.notificacoes import avisar_quem_pode

    avisar_quem_pode(
        tenant_id=restricao.tenant_id, permissao="scm.demanda.edit",
        titulo=f"Demanda {demanda.pk} aberta pelo plano da obra — restrição de {restricao.get_tipo_display().lower()}",
        mensagem=(
            f"{restricao.descricao[:200]} · atividade {atividade.codigo or atividade.pk}"
            + (f" · obra {obra.nome_obra}" if obra else "")
            + (f" · precisa até {restricao.prazo:%d/%m/%Y}" if restricao.prazo else "")
            + ". Nasceu em rascunho: confira a quantidade e publique."
        ),
        url="/app/scm", nivel=Notificacao.Nivel.DECIDIR,
    )
    return demanda.pk


# --- 12.3 O compromisso da semana, o PPC e o ranking -------------------------


def segunda_da_semana(dia: date) -> date:
    """A segunda-feira da semana de `dia`.

    A semana do LPS começa na segunda por convenção do método, e não por
    preferência de locale: a reunião de programação é de segunda, e o ciclo que
    ela abre é o de segunda a domingo. Ancorar na segunda é o que torna
    `semana_inicio` uma chave natural em vez de um intervalo qualquer.
    """
    return dia - timedelta(days=dia.weekday())


@transaction.atomic
def abrir_programacao(*, obra, semana_inicio: date, por: str = "",
                      tenant_id=None) -> ProgramacaoSemanal:
    """Abre (ou devolve) a programação daquela semana, em rascunho.

    **Idempotente por semana**, e é o `UniqueConstraint` que garante isso no
    banco: duas programações da mesma semana seriam dois compromissos
    concorrentes sobre o mesmo período, e o PPC não saberia qual contar.
    """
    inicio = segunda_da_semana(semana_inicio)
    tid = tenant_id if tenant_id is not None else obra.tenant_id
    existente = ProgramacaoSemanal.objects.filter(
        tenant_id=tid, obra=obra, semana_inicio=inicio,
    ).first()
    if existente:
        return existente
    # O catálogo de causas precisa existir **antes** do primeiro encerramento, e
    # semear aqui é o que garante que a primeira reunião já tenha de onde
    # escolher. É idempotente, então custar uma consulta por abertura é barato.
    semear_causas_de_fabrica(tid)
    return ProgramacaoSemanal.objects.create(
        tenant_id=tid, obra=obra,
        semana_inicio=inicio, semana_fim=inicio + timedelta(days=6),
        criada_por=por or "",
    )


def validar_teto_de_itens_da_programacao(programacao: ProgramacaoSemanal, *,
                                         acrescentando: int = 1) -> None:
    """A parede tem de caber na vista — §5.5j do `planos.py`."""
    atual = programacao.itens.count()
    if atual + acrescentando > PDCA_TETO_ITENS_POR_PROGRAMACAO:
        raise ValidationError(
            f"Uma programação semanal do seu plano comporta "
            f"{_milhar(PDCA_TETO_ITENS_POR_PROGRAMACAO)} compromissos, e esta "
            f"já tem {_milhar(atual)}. O quadro é uma parede de reunião: acima "
            f"disso ninguém mais o lê inteiro, e compromisso que não se lê não "
            f"se cobra."
        )


def validar_pode_comprometer(atividade: Atividade, *, tenant_id) -> None:
    """**A regra que separa o LPS de uma lista de tarefas** (planta §4.3).

    Atividade com restrição aberta não entra na programação. Sem esta trava, o
    quadro vira lista de desejos: o time assume o que sabe estar travado, o PPC
    despenca, e a causa registrada toda semana é a mesma restrição que ninguém
    removeu — o LPS medindo o próprio fracasso em vez de evitá-lo.
    """
    abertas = list(
        Restricao.objects.filter(
            tenant_id=tenant_id, atividade=atividade,
            status=Restricao.Status.ABERTA,
        ).values_list("tipo", "descricao")[:5]
    )
    if not abertas:
        return
    lista = "; ".join(
        f"{dict(TipoRestricao.choices).get(tipo, tipo)}: {desc[:60]}"
        for tipo, desc in abertas
    )
    raise ValidationError(
        f"«{atividade.nome}» tem {len(abertas)} restrição(ões) aberta(s) e não "
        f"pode ser comprometida — {lista}. Remova a trava primeiro: assumir um "
        f"serviço que se sabe travado é o que faz o PPC medir o próprio "
        f"fracasso em vez de evitá-lo."
    )


@transaction.atomic
def comprometer(*, programacao: ProgramacaoSemanal, por: str = "") -> dict:
    """Rascunho → **comprometida**: o time assumiu, e a lista fecha.

    **Depois disto não entra item novo.** É a propriedade que dá sentido ao PPC:
    acrescentar compromisso depois de a semana andar é escrever a aposta depois
    do resultado, e um PPC assim mede apenas quem soube editar a lista a tempo.

    As restrições são conferidas **de novo aqui**, e não só na inclusão do item:
    entre montar o quadro na segunda e assumi-lo pode ter aparecido uma trava, e
    assumir por cima dela é o erro que o make-ready existe para evitar.
    """
    if programacao.status != ProgramacaoSemanal.Status.RASCUNHO:
        raise ValidationError(
            f"Esta programação está "
            f"{programacao.get_status_display().lower()} — só um rascunho pode "
            f"ser comprometido."
        )
    itens = list(programacao.itens.select_related("atividade"))
    if not itens:
        raise ValidationError(
            "Não dá para se comprometer com uma semana vazia. Puxe pelo menos "
            "um serviço do plano para o quadro."
        )
    travados = []
    for item in itens:
        try:
            validar_pode_comprometer(item.atividade, tenant_id=programacao.tenant_id)
        except ValidationError as erro:
            travados.append(erro.messages[0] if erro.messages else str(erro))
    if travados:
        raise ValidationError(travados)

    programacao.status = ProgramacaoSemanal.Status.COMPROMETIDA
    programacao.comprometida_em = timezone.now()
    programacao.comprometida_por = por or ""
    programacao.save(update_fields=[
        "status", "comprometida_em", "comprometida_por",
    ])
    return {"programacao": programacao.pk, "compromissos": len(itens)}


class EncerramentoSemCausa(ValidationError):
    """Há compromisso que não saiu e ficou sem causa — o aviso antes de bloquear.

    Carrega o que falta, para a tela mostrar os nomes e, a quem pode, oferecer
    «encerrar assim mesmo». `pode` diz se quem pediu tem essa alçada."""

    def __init__(self, itens, *, pode: bool):
        self.itens = [
            {"item": i.pk, "atividade": i.atividade.nome,
             "percentual": str(i.percentual_concluido)}
            for i in itens
        ]
        self.pode = pode
        nomes = ", ".join(f"«{d['atividade']}»" for d in self.itens)
        super().__init__(
            f"{len(self.itens)} compromisso(s) que não saíram estão sem causa: {nomes}. "
            + ("Você pode encerrar assim mesmo — a causa fica como «Sem causa informada»."
               if pode else
               "Informe a causa de cada um para encerrar, ou peça a quem tem a alçada.")
        )


@transaction.atomic
def encerrar(*, programacao: ProgramacaoSemanal, por: str = "",
             hoje: date | None = None, pode_antecipar: bool = False,
             motivo_antecipado: str = "", arrastar: bool = True,
             aceitar_sem_causa: bool = False,
             pode_aceitar_sem_causa: bool = False) -> dict:
    """Comprometida → **encerrada**: cada item julgado, e o PPC passa a existir.

    **Recusa encerrar com item por julgar.** O `cumprido` nulo é "ainda não
    julgado" (§ modelo), e encerrar com nulos produziria um PPC cujo
    denominador ninguém sabe: contar o nulo como falha puniria a equipe por um
    julgamento que não se fez, e ignorá-lo inflaria o índice.

    **E recusa encerrar a semana que ainda não acabou** *(decisão do dono,
    15/09/2026)*. Antes bastava o status: na segunda-feira de manhã dava para
    julgar os cinco compromissos como "não saiu" e fechar — com a semana inteira
    pela frente. O índice que sai daí não mede confiabilidade de plano nenhum, e
    entra na série indistinguível dos outros pontos.

    Não é porta trancada, é **porta com chave e assinatura**: quem tem
    `pdca.programacao.encerrar_antecipado` passa, **dando motivo por escrito**, e
    a semana fica marcada (`encerrada_antes_do_fim`). O caso real existe — a obra
    que para na quinta de um feriado prolongado e faz a retrospectiva antes de
    todo mundo sumir —, e trancar de todo faria o time julgar de memória na
    semana seguinte, que é pior do que julgar cedo.

    **Encerrar arrasta o que não saiu.** É a última coisa que a função faz, e a
    razão está em `arrastar_pendentes`: serviço que não saiu não deixou de ser
    preciso, e obrigar o time a reencontrá-lo na WBS na segunda seguinte apaga o
    fato de ele estar na segunda semana consecutiva — que é justamente o que a
    reunião precisa ver.
    """
    if programacao.status != ProgramacaoSemanal.Status.COMPROMETIDA:
        raise ValidationError(
            f"Esta programação está "
            f"{programacao.get_status_display().lower()} — só uma programação "
            f"comprometida pode ser encerrada."
        )
    por_julgar = programacao.itens.filter(cumprido__isnull=True)
    # O que já tem avanço digitado e ficou sem causa (ver `julgar_itens`) é outra
    # coisa que o que ninguém julgou: o primeiro pode fechar com a ressalva.
    sem_causa = list(por_julgar.filter(percentual_concluido__isnull=False)
                     .select_related("atividade"))
    pendentes = por_julgar.filter(percentual_concluido__isnull=True).count()
    if pendentes:
        raise ValidationError(
            f"Ainda há {pendentes} compromisso(s) sem julgamento. Diga de cada "
            f"um se saiu ou não — e, quando não saiu, por quê: é dessa resposta "
            f"que sai o ranking que muda a obra, e não do índice."
        )
    if sem_causa:
        if not aceitar_sem_causa:
            raise EncerramentoSemCausa(sem_causa, pode=pode_aceitar_sem_causa)
        if not pode_aceitar_sem_causa:
            raise ValidationError(
                "Encerrar a semana com compromisso sem causa exige a permissão "
                "'pdca.programacao.encerrar_sem_causa'. Informe a causa de cada "
                "um, ou peça a quem a tem."
            )

    hoje = hoje or timezone.localdate()
    antecipado = programacao.semana_fim > hoje
    motivo = (motivo_antecipado or "").strip()
    if antecipado:
        faltam = (programacao.semana_fim - hoje).days
        if not pode_antecipar:
            raise ValidationError(
                f"Esta semana só termina em "
                f"{programacao.semana_fim:%d/%m/%Y} — faltam {faltam} dia(s). "
                f"Encerrar agora julga como fracasso o que ainda tem prazo para "
                f"acontecer, e o PPC que sair daí entra na série valendo o mesmo "
                f"que os outros. Se a obra realmente para antes (feriado "
                f"prolongado, paralisação), quem tem "
                f"'pdca.programacao.encerrar_antecipado' encerra dando o motivo."
            )
        if not motivo:
            raise ValidationError(
                f"Encerrar {faltam} dia(s) antes do fim da semana exige motivo "
                f"por escrito. É a frase que a reunião seguinte lê para saber "
                f"por que aquele ponto da série foi apurado mais cedo."
            )

    if sem_causa:
        # A decisão de seguir foi de quem tem a alçada; o ranking mostra a falta
        # como tal — «Sem causa informada» — em vez de esconder ou inventar.
        causa, _ = CausaNaoCumprimento.objects.get_or_create(
            tenant_id=programacao.tenant_id, codigo="SEM-CAUSA",
            defaults={"nome": "Sem causa informada", "ativo": False, "de_fabrica": True,
                      "categoria": CausaNaoCumprimento.Categoria.PLANEJAMENTO},
        )
        for item in sem_causa:
            item.cumprido = False
            item.causa = causa
            item.nota = (f"{item.nota}\n" if item.nota else "") + (
                f"Semana encerrada por {por or 'usuário'} sem a causa informada."
            )
        ItemProgramacao.objects.bulk_update(sem_causa, ["cumprido", "causa", "nota"])

    programacao.status = ProgramacaoSemanal.Status.ENCERRADA
    programacao.encerrada_em = timezone.now()
    programacao.encerrada_por = por or ""
    programacao.encerrada_antes_do_fim = antecipado
    programacao.motivo_encerramento_antecipado = motivo if antecipado else ""
    programacao.save(update_fields=[
        "status", "encerrada_em", "encerrada_por",
        "encerrada_antes_do_fim", "motivo_encerramento_antecipado",
    ])

    resultado = ppc_de(programacao)
    resultado["arrasto"] = (
        arrastar_pendentes(programacao=programacao, por=por)
        if arrastar else None
    )
    return resultado


@transaction.atomic
def arrastar_pendentes(*, programacao: ProgramacaoSemanal,
                       por: str = "") -> dict:
    """**O que não saiu continua de pé** — os compromissos falhados seguem para
    a semana seguinte, em rascunho *(decisão do dono, 15/09/2026)*.

    Antes a semana encerrada era um fim de linha: o cartão "não saiu" ficava no
    quadro de trás e a semana seguinte nascia vazia. Quem quisesse continuar a
    armação de pilares tinha de reencontrá-la na WBS e puxá-la à mão — e o que
    se perdia nesse caminho não era o clique, era **o fato de aquele compromisso
    estar na segunda semana seguida**. É esse fato, e não o índice, que faz a
    reunião perguntar o que está travando.

    **O que o cartão arrastado leva junto:**

    - o que **ficou por fazer**, e não o que foi prometido. A semana que assumiu
      20 pontos e apontou 12 arrasta 8: é o item parcialmente concluído, que é
      caso comum e até aqui não tinha como ser dito. Previsto nulo continua nulo
      — compromisso binário ("concretar a laje") não ganha número inventado;
    - `arrastado_de` e `vezes_arrastado`, que é o contador do padrão: quatro
      semanas arrastado não é o mesmo problema que uma, e ninguém veria isso
      cruzando quadros à mão;
    - o responsável e o local. **Não leva a nota nem a causa**: aquelas são o
      julgamento da semana que passou, e o cartão novo nasce por julgar.

    **Não arrasta para semana já assumida.** Se a seguinte já saiu do rascunho,
    a função devolve o que faria sem fazer: acrescentar compromisso a um quadro
    comprometido é escrever a aposta depois do resultado, que é a regra que dá
    sentido ao PPC.

    **Arrasta mesmo o que está travado**, e é deliberado. O cartão que não saiu
    por falta de material volta com a restrição ainda aberta — e `comprometer`
    vai recusar a semana enquanto ela estiver lá. É o desenho certo: a trava
    aparece no quadro da reunião, no lugar em que alguém decide removê-la, em
    vez de o serviço sumir e a trava ficar invisível até a semana seguinte.

    **Idempotente**: rodar duas vezes não duplica cartão — o serviço que já está
    no quadro da semana seguinte é pulado, pela mesma chave
    (atividade, local) que a `UniqueConstraint` do modelo protege.
    """
    if programacao.status != ProgramacaoSemanal.Status.ENCERRADA:
        raise ValidationError(
            f"Só uma semana encerrada arrasta pendências — esta está "
            f"{programacao.get_status_display().lower()}. O que não saiu só se "
            f"sabe depois do julgamento."
        )

    falhados = list(
        programacao.itens.filter(cumprido=False).select_related("atividade")
        .order_by("ordem", "item_programacao_id")
    )
    if not falhados:
        return {"arrastados": 0, "ja_no_quadro": 0, "sem_espaco": 0,
                "programacao_destino": None, "destino_fechado": False}

    destino = abrir_programacao(
        obra=programacao.obra,
        semana_inicio=programacao.semana_inicio + timedelta(days=7),
        por=por,
        tenant_id=programacao.tenant_id,
    )
    if not destino.esta_aberta_para_montagem:
        return {
            "arrastados": 0, "ja_no_quadro": 0, "sem_espaco": len(falhados),
            "programacao_destino": destino.pk, "destino_fechado": True,
        }

    ja_la = set(
        destino.itens.values_list("atividade_id", "local_id")
    )
    apontado = avanco_apontado_dos_itens(programacao)
    espaco = PDCA_TETO_ITENS_POR_PROGRAMACAO - destino.itens.count()
    proxima_ordem = (
        destino.itens.aggregate(m=Max("ordem"))["m"] or 0
    )

    arrastados = 0
    repetidos = 0
    sem_espaco = 0
    for item in falhados:
        if (item.atividade_id, item.local_id) in ja_la:
            repetidos += 1
            continue
        if espaco <= 0:
            sem_espaco += 1
            continue
        proxima_ordem += 1
        ItemProgramacao.objects.create(
            tenant_id=destino.tenant_id,
            programacao=destino,
            atividade=item.atividade,
            local_id=item.local_id,
            responsavel=item.responsavel,
            percentual_previsto=_resto_previsto(item, apontado.get(item.pk)),
            arrastado_de=item,
            vezes_arrastado=item.vezes_arrastado + 1,
            ordem=proxima_ordem,
        )
        ja_la.add((item.atividade_id, item.local_id))
        espaco -= 1
        arrastados += 1

    return {
        "arrastados": arrastados,
        "ja_no_quadro": repetidos,
        "sem_espaco": sem_espaco,
        "programacao_destino": destino.pk,
        "destino_fechado": False,
    }


def _resto_previsto(item: ItemProgramacao,
                    apontado: Decimal | None) -> Decimal | None:
    """Quanto do compromisso **ficou por fazer** — o previsto menos o apontado.

    Nulo continua nulo: compromisso sem número é binário de propósito, e inventar
    um para o arrasto seria pior do que não ter. Apontado maior que o previsto
    devolve nulo também — a atividade andou mais do que se prometeu e mesmo assim
    não foi dada por cumprida, então quanto falta é pergunta para a reunião, não
    para uma subtração.
    """
    if item.percentual_previsto is None:
        return None
    if apontado is None:
        return item.percentual_previsto
    resto = item.percentual_previsto - apontado
    return resto if resto > 0 else None


def avanco_apontado_dos_itens(programacao: ProgramacaoSemanal) -> dict[int, Decimal]:
    """`{item_programacao_id: pontos que o campo apontou na semana}` — **numa consulta**.

    **O compromisso é binário; a execução não é.** O Last Planner julga "saiu" ou
    "não saiu" de propósito — é a definição do PPC, e contar 80% como 0,8
    destruiria o que ele mede (ver `ppc_de`). Mas a obra que assumiu 20 pontos e
    entregou 12 **fez 12**, e jogar esse número fora tem dois custos: a equipe vê
    o sistema dizer que ela não fez nada, e quem julga julga de memória.

    Este agregado é a ponte: o número não entra no PPC, ele fica **ao lado** do
    compromisso, como prova. É o mesmo dado que a PDCA.2 já apura — não se digita
    nada de novo, e é por isso que ele é confiável: veio do campo, apontado no dia.

    **Como o local entra na conta:** item com `local` conta só o apontamento
    daquele local; item sem `local` é a atividade inteira e conta tudo. Somar os
    dois casos faria o mesmo apontamento pesar em dois cartões.
    """
    itens = list(programacao.itens.all())
    if not itens:
        return {}

    linhas = (
        ApontamentoAvanco.objects
        .filter(
            tenant_id=programacao.tenant_id,
            atividade_id__in={i.atividade_id for i in itens},
            data__gte=programacao.semana_inicio,
            data__lte=programacao.semana_fim,
        )
        .values("atividade_id", "local_id")
        .annotate(total=Sum("percentual"))
    )
    por_atividade: dict[int, Decimal] = {}
    por_atividade_local: dict[tuple[int, int], Decimal] = {}
    for linha in linhas:
        total = linha["total"] or _ZERO
        por_atividade[linha["atividade_id"]] = (
            por_atividade.get(linha["atividade_id"], _ZERO) + total
        )
        if linha["local_id"] is not None:
            por_atividade_local[(linha["atividade_id"], linha["local_id"])] = total

    resultado: dict[int, Decimal] = {}
    for item in itens:
        if item.local_id is not None:
            valor = por_atividade_local.get((item.atividade_id, item.local_id))
        else:
            valor = por_atividade.get(item.atividade_id)
        #: `None` e zero são coisas diferentes, e a tela precisa das duas: nulo é
        #: "o campo não apontou nada nesta semana" (pode ser que não tenha
        #: apontado, não que não tenha feito); zero é "apontou e estornou".
        if valor is not None:
            resultado[item.pk] = valor
    return resultado


@transaction.atomic
def reabrir(*, programacao: ProgramacaoSemanal, por: str = "",
            motivo: str = "") -> dict:
    """Desce **um** degrau na semana, com motivo obrigatório.

    Existe porque a semana encerrada era um beco. `julgar_itens` só aceita
    programação comprometida, então um julgamento errado — "saiu" no que não
    saiu, a causa trocada na pressa da reunião — ficava para sempre. E o que
    estraga não é o índice: é o **ranking de causas**, que é o que decide o que a
    empresa muda. Uma causa errada contada durante um ano manda a obra consertar
    o problema que ela não tem.

    **Um degrau por vez, e não um "voltar para rascunho".** De `ENCERRADA` volta
    para `COMPROMETIDA` — que é onde se rejulga, mantendo o que já foi julgado
    para a pessoa corrigir só o que está errado. De `COMPROMETIDA` volta para
    `RASCUNHO`, que é onde o quadro recebe e devolve cartão. Quem quer as duas
    coisas reabre duas vezes, e **cada uma fica registrada** — porque descer dois
    degraus de uma vez é exatamente o gesto que merece dois registros.

    **Voltar ao rascunho APAGA os julgamentos**, e isso é dito antes. Rascunho
    quer dizer *a semana ainda não foi assumida*, e um julgamento pendurado numa
    semana que ninguém assumiu não é um dado — é entulho que o próximo
    encerramento contaria. Como o `ppc` é `null` até encerrar, o que se perde ao
    sair de `COMPROMETIDA` é rascunho de julgamento; o que se perde vindo de
    `ENCERRADA` é um julgamento que valeu, e por isso o caminho tem de passar por
    duas reaberturas, cada uma com a sua frase.

    **Sem prazo, de propósito** — ver a docstring dos campos no modelo: erro
    achado tarde é o mais caro de não poder consertar, e a retificadora da
    medição, que mexe em dinheiro, também não tem prazo. O que protege o
    histórico é a correção **aparecer**, não a porta trancada.
    """
    if not (motivo or "").strip():
        raise ValidationError(
            "Diga por que a semana está sendo reaberta. O PPC dela já foi lido "
            "por alguém — mudar o número sem deixar a razão escrita contraria "
            "em silêncio a reunião que olhou para ele."
        )
    if programacao.status == ProgramacaoSemanal.Status.RASCUNHO:
        raise ValidationError(
            "Esta semana já é um rascunho: o quadro está aberto e recebe cartão. "
            "Não há degrau abaixo deste."
        )

    de = programacao.status
    if de == ProgramacaoSemanal.Status.ENCERRADA:
        para = ProgramacaoSemanal.Status.COMPROMETIDA
        #: O encerramento é desfeito; o julgamento **fica**, para quem reabriu
        #: corrigir o item errado em vez de refazer a semana inteira.
        programacao.encerrada_em = None
        programacao.encerrada_por = ""
        apagados = 0
    else:
        para = ProgramacaoSemanal.Status.RASCUNHO
        apagados = programacao.itens.exclude(cumprido__isnull=True).count()
        #: `causa` sai junto, senão a `CheckConstraint` do item recusaria a
        #: linha (cumprido nulo com causa preenchida é o estado que ela proíbe).
        programacao.itens.update(cumprido=None, causa=None)
        programacao.comprometida_em = None
        programacao.comprometida_por = ""

    programacao.status = para
    programacao.reaberta_em = timezone.now()
    programacao.reaberta_por = por or ""
    programacao.motivo_reabertura = motivo.strip()
    programacao.vezes_reaberta = (programacao.vezes_reaberta or 0) + 1
    programacao.save(update_fields=[
        "status", "encerrada_em", "encerrada_por",
        "comprometida_em", "comprometida_por",
        "reaberta_em", "reaberta_por", "motivo_reabertura", "vezes_reaberta",
    ])
    return {
        "programacao": programacao.pk,
        "de": de, "para": para,
        "julgamentos_apagados": apagados,
        "vezes_reaberta": programacao.vezes_reaberta,
    }


#: Os rótulos das bases de peso, para a tela dizer de onde saiu o índice sem
#: traduzir código. `igual` é a base do quadro em que nenhum cartão tem peso —
#: e é, letra por letra, o PPC clássico de contar cartões.
ROTULO_BASE_PESO = {
    "orcado": "valor orçado",
    "informado": "peso do planejador",
    "duracao": "duração",
    "igual": "contagem de cartões",
}


def pesos_da_programacao(programacao: ProgramacaoSemanal) -> dict:
    """Os pesos congelados do quadro, prontos para a divisão do PPC.

    **Uma consulta**, e devolve o que o índice e a tela precisam: quanto pesa o
    assumido, quanto pesa o cumprido, quantos cartões ficaram sem régua e de
    quais fontes os pesos vieram.

    **Quadro em que nenhum cartão tem peso cai na base `igual`** — cada cartão
    vale 1, que é o PPC clássico. Sem essa queda, a obra que ainda não vinculou
    o cronograma ao orçamento e não digitou duração ficaria com "sem apuração"
    para sempre, e o índice que ela tinha antes teria sumido sem aviso.
    """
    linhas = list(
        programacao.itens.values("cumprido", "peso", "peso_origem")
    )
    com_peso = [
        linha for linha in linhas
        if linha["peso"] is not None and linha["peso"] > 0
    ]
    if com_peso:
        base_total = sum((linha["peso"] for linha in com_peso), _ZERO)
        base_cumprida = sum(
            (linha["peso"] for linha in com_peso if linha["cumprido"] is True),
            _ZERO,
        )
        bases = sorted({linha["peso_origem"] for linha in com_peso if linha["peso_origem"]})
    else:
        #: Ninguém tem régua: cada cartão vale 1 e o índice volta a ser a
        #: contagem. É a mesma resposta honesta do `folhas_sem_peso` — o número
        #: existe, e a resposta diz em cima de quê ele foi feito.
        base_total = Decimal(len(linhas))
        base_cumprida = Decimal(
            sum(1 for linha in linhas if linha["cumprido"] is True)
        )
        bases = ["igual"] if linhas else []
    return {
        "peso_total": base_total,
        "peso_cumprido": base_cumprida,
        #: Quantos compromissos não têm como ser pesados — marco, atividade sem
        #: duração nem vínculo. Eles contam em `comprometidos` e ficam **fora**
        #: da divisão, e a tela mostra o número ao lado do índice: 90% apurado
        #: sobre 2 de 11 cartões é bonito e mente (a régua do §5.4).
        "sem_peso": len(linhas) - len(com_peso) if com_peso else 0,
        "bases": bases,
    }


def ppc_de(programacao: ProgramacaoSemanal) -> dict:
    """O **PPC** — derivado, nunca gravado (§4.9), e **ponderado**.

    A pergunta do Last Planner continua a mesma — *daquilo que o time disse que
    ia fazer, quanto saiu?* —, e o que mudou foi a unidade da resposta.

    **Por que deixou de contar cartões** *(decisão do dono, 15/09/2026)*. A
    contagem dizia que assumir a concretagem da laje e assumir a limpeza do
    canteiro valem o mesmo: a semana que entrega a laje e perde a limpeza
    marcava os mesmos 50% da que entrega a limpeza e perde a laje, e essas duas
    semanas não são a mesma semana para ninguém que esteja na obra. Agora o
    numerador e o denominador são **peso**, e o peso sai do planejamento — do
    orçamento, do peso informado ou da duração, nessa ordem
    (`peso_do_compromisso`).

    **A série histórica anterior foi recalculada junto**, e isso é consequência
    aceita da decisão: as semanas encerradas antes desta mudança não têm peso
    gravado e caem na base `igual`, que reproduz exatamente o índice que elas já
    mostravam. O que muda de verdade é a comparação entre uma semana velha
    (`igual`) e uma nova (`orcado`) — e é por isso que a base viaja na resposta
    em vez de ficar implícita.

    **Enquanto a semana não encerra, `ppc` é `None`** — e a tela mostra "sem
    apuração", nunca 0%. É a régua de dado honesto da §5.4 aplicada ao índice:
    uma semana comprometida na segunda-feira tem zero cumpridos por construção,
    e exibir "PPC 0%" seria fabricar um fracasso que ainda não aconteceu.
    """
    agregado = programacao.itens.aggregate(
        total=Count("item_programacao_id"),
        cumpridos=Count("item_programacao_id", filter=Q(cumprido=True)),
        falhados=Count("item_programacao_id", filter=Q(cumprido=False)),
        pendentes=Count("item_programacao_id", filter=Q(cumprido__isnull=True)),
        #: Quanto a equipe **prometeu** avançar na semana, somando os cartões que
        #: puseram número. Nulo quando nenhum pôs — muito compromisso de LPS é
        #: binário ("concretar a laje"), e obrigar um número faria o time
        #: inventar um.
        previsto=Sum("percentual_previsto"),
        #: Quantos cartões vieram arrastados da semana anterior. É o número que
        #: a reunião olha antes do índice: uma semana com metade do quadro
        #: arrastado não tem problema de execução, tem problema de make-ready.
        arrastados=Count("item_programacao_id", filter=Q(vezes_arrastado__gt=0)),
    )
    total = agregado["total"] or 0
    encerrada = programacao.status == ProgramacaoSemanal.Status.ENCERRADA
    pesos = pesos_da_programacao(programacao)
    ppc = None
    if encerrada and total and pesos["peso_total"] > 0:
        ppc = (
            pesos["peso_cumprido"] * 100 / pesos["peso_total"]
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {
        "programacao": programacao.pk,
        "semana_inicio": programacao.semana_inicio,
        "semana_fim": programacao.semana_fim,
        "status": programacao.status,
        "comprometidos": total,
        "cumpridos": agregado["cumpridos"] or 0,
        "nao_cumpridos": agregado["falhados"] or 0,
        "por_julgar": agregado["pendentes"] or 0,
        "ppc": ppc,
        #: O denominador, dito em voz alta — a mesma régua do
        #: `realizado_cobertura` do Orçamento: quem lê o índice vê de quantos
        #: compromissos ele saiu, e não precisa confiar no número sozinho.
        "apurado": encerrada,
        #: **E se ele já foi corrigido, isso também é dito.** Um PPC rejulgado
        #: depois de a reunião ter olhado para ele não pode passar por número
        #: virgem: quem lembra de 60% precisa saber que virou 45% porque a
        #: semana foi reaberta, e não porque a memória falhou. É o que faz a
        #: correção ser correção em vez de reescrita da história.
        "vezes_reaberta": programacao.vezes_reaberta or 0,
        "motivo_reabertura": programacao.motivo_reabertura or "",
        #: **E se ela foi encerrada antes de acabar, isso também é dito.** Um
        #: ponto apurado na terça não é comparável com um apurado no domingo, e
        #: a série tem de desenhá-lo diferente — ver §12.3, `encerrar`.
        "encerrada_antes_do_fim": programacao.encerrada_antes_do_fim,
        "motivo_encerramento_antecipado": (
            programacao.motivo_encerramento_antecipado or ""
        ),
        #: --- Em cima de quê o índice foi feito ------------------------------
        #:
        #: O PPC é ponderado, e o peso tem procedência: valor orçado, peso do
        #: planejador, duração — ou `igual`, o quadro em que nenhum cartão tem
        #: régua e cada um vale 1. **A base viaja junto porque muda o que o
        #: número significa**: 70% pesado por dinheiro e 70% contando cartões
        #: são duas frases diferentes, e uma série que mistura as duas sem dizer
        #: é uma série que mente devagar.
        #:
        #: Vem como lista porque o quadro pode misturar: metade dos cartões
        #: vinculada ao orçamento e metade valendo duração. A tela avisa quando
        #: há mais de uma — e é aviso, não erro: a obra que está vinculando o
        #: cronograma ao orçamento aos poucos passa semanas nesse estado.
        "peso_bases": pesos["bases"],
        "peso_total": pesos["peso_total"],
        "peso_cumprido": pesos["peso_cumprido"],
        #: Compromissos que não têm como ser pesados (marco, atividade sem
        #: duração nem vínculo). Contam em `comprometidos` e ficam fora da
        #: divisão — a régua do `folhas_sem_peso` do avanço.
        "sem_peso": pesos["sem_peso"],
        #: --- A execução, que é coisa DIFERENTE do cumprimento ---------------
        #:
        #: **Nunca entra no PPC, e por isso vem com nome próprio.** O índice
        #: pergunta se o compromisso saiu — sim ou não —, e o peso decide quanto
        #: cada "sim" vale. Contar 80% de execução como 0,8 de cumprimento é
        #: outra coisa: faria o time aprender a prometer demais e mostrar sempre
        #: uns 70%, e o PPC deixaria de medir a **confiabilidade do plano**, que
        #: é a única coisa que ele mede.
        #:
        #: Mas a obra que assumiu 20 pontos e entregou 12 fez 12, e a equipe
        #: precisa ver isso registrado — senão o sistema parece dizer que ela não
        #: fez nada. Estes dois números respondem *quanto do prometido andou*, e
        #: a tela tem de mostrá-los **separados do PPC**, nunca somados a ele.
        #: São eles, também, que viram o previsto do cartão arrastado: o que
        #: ficou por fazer segue para a semana seguinte (ver `arrastar_pendentes`).
        "pontos_previstos": agregado["previsto"],
        "pontos_apontados": (
            sum(avanco_apontado_dos_itens(programacao).values()) or None
        ) if total else None,
        #: Quantos cartões desta semana vieram arrastados da anterior.
        "arrastados": agregado["arrastados"] or 0,
    }


def serie_ppc(*, obra_id, tenant_id, limite: int | None = None) -> list[dict]:
    """A série histórica de PPC da obra — **só semanas encerradas**.

    É a leitura que dá sentido ao índice: um PPC isolado não diz nada, e a
    tendência ao longo de dez semanas diz tudo. Semana aberta fica de fora pelo
    mesmo motivo do `None` acima — ela ainda não tem índice.

    O teto vem do `planos.py` (§5.5j) e é o irmão do da curva S: acima dele o
    eixo deixa de ser legível.
    """
    teto = min(limite or PDCA_TETO_SEMANAS_PPC, PDCA_TETO_SEMANAS_PPC)
    programacoes = list(
        ProgramacaoSemanal.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id,
            status=ProgramacaoSemanal.Status.ENCERRADA,
        )
        .only(
            "programacao_id", "semana_inicio", "vezes_reaberta",
            "encerrada_antes_do_fim",
        )
        .order_by("-semana_inicio")[:teto]
    )
    if not programacoes:
        return []

    #: **Os itens de todas as semanas numa consulta só.** A soma tem de ser a
    #: mesma do `ppc_de` — ponto de série que discorda do ponto da tela é o
    #: defeito que o D138 já custou caro na grade de medição —, e ela é
    #: ponderada, o que o `Sum` anotado não resolve sozinho: o cartão sem peso
    #: fica fora da divisão e o quadro sem peso nenhum cai na base `igual`.
    #: Com o teto de 104 semanas × 300 cartões, é uma leitura de projeção
    #: estreita, sem objeto de modelo.
    por_semana: dict[int, list[dict]] = {p.pk: [] for p in programacoes}
    for linha in ItemProgramacao.objects.filter(
        tenant_id=tenant_id, programacao_id__in=list(por_semana),
    ).values("programacao_id", "cumprido", "peso", "peso_origem"):
        por_semana[linha["programacao_id"]].append(linha)

    serie = []
    for prog in programacoes:
        linhas = por_semana.get(prog.pk, [])
        if not linhas:
            # Semana encerrada sem item é impossível pelo `comprometer`, mas o
            # comando de bancada entra por outra porta — e dividir por zero na
            # leitura seria a pior hora de descobrir isso.
            continue
        com_peso = [
            linha for linha in linhas
            if linha["peso"] is not None and linha["peso"] > 0
        ]
        if com_peso:
            base = sum((linha["peso"] for linha in com_peso), _ZERO)
            feito = sum(
                (linha["peso"] for linha in com_peso
                 if linha["cumprido"] is True),
                _ZERO,
            )
            bases = sorted({
                linha["peso_origem"] for linha in com_peso if linha["peso_origem"]
            })
        else:
            base = Decimal(len(linhas))
            feito = Decimal(sum(1 for l in linhas if l["cumprido"] is True))
            bases = ["igual"]
        if base <= 0:
            continue
        serie.append({
            "programacao": prog.pk,
            "semana_inicio": prog.semana_inicio,
            "comprometidos": len(linhas),
            "cumpridos": sum(1 for l in linhas if l["cumprido"] is True),
            "ppc": (feito * 100 / base).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP,
            ),
            #: A base viaja com o ponto: a série que mistura semanas pesadas por
            #: dinheiro com semanas contadas por cartão continua legível porque
            #: cada ponto diz de onde veio (ver `ppc_de`).
            "peso_bases": bases,
            #: A barra do ponto reaberto é desenhada diferente — a série é o que
            #: a diretoria lê, e um ponto corrigido tem de se anunciar ali.
            "vezes_reaberta": prog.vezes_reaberta or 0,
            #: E o ponto apurado antes de a semana acabar, pelo mesmo motivo.
            "encerrada_antes_do_fim": prog.encerrada_antes_do_fim,
        })
    serie.reverse()
    return serie


def ranking_de_causas(*, obra_id, tenant_id, desde: date | None = None,
                      ate: date | None = None) -> dict:
    """**O "Act"** — por que os compromissos desta obra não saem.

    O PPC diz *quanto* falhou; só isto diz *o quê* mudar, e é a razão de a causa
    vir de catálogo fechado: com texto livre, "chuva", "choveu" e "clima" viram
    três linhas com um terço do peso cada, e a causa que lidera não aparece.

    Devolve as causas ordenadas por frequência **e** o corte por categoria — que
    é a leitura que decide com quem é a conversa da semana. Saber que falta de
    material lidera é meia informação; saber que a maioria das falhas aponta
    para fora da equipe (projeto, fornecedor, cliente) é o que tira a reunião de
    dentro do canteiro e a leva para a mesa da contratante.
    """
    itens = ItemProgramacao.objects.filter(
        tenant_id=tenant_id,
        cumprido=False,
        programacao__obra_id=obra_id,
        programacao__status=ProgramacaoSemanal.Status.ENCERRADA,
    )
    if desde:
        itens = itens.filter(programacao__semana_inicio__gte=desde)
    if ate:
        itens = itens.filter(programacao__semana_inicio__lte=ate)

    por_causa = list(
        itens.values("causa_id", "causa__codigo", "causa__nome",
                     "causa__categoria")
        .annotate(n=Count("item_programacao_id"))
        .order_by("-n", "causa__codigo")
    )
    total = sum(linha["n"] for linha in por_causa)

    por_categoria: dict[str, int] = {}
    for linha in por_causa:
        chave = linha["causa__categoria"] or "sem_categoria"
        por_categoria[chave] = por_categoria.get(chave, 0) + linha["n"]

    rotulos = dict(CausaNaoCumprimento.Categoria.choices)
    return {
        "total_falhas": total,
        "causas": [
            {
                "causa": linha["causa_id"],
                "codigo": linha["causa__codigo"],
                "nome": linha["causa__nome"],
                "categoria": linha["causa__categoria"],
                "ocorrencias": linha["n"],
                "percentual": (
                    Decimal(linha["n"]) * 100 / Decimal(total)
                ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                if total else Decimal("0.0"),
            }
            for linha in por_causa
        ],
        "categorias": [
            {
                "categoria": chave,
                "rotulo": str(rotulos.get(chave, chave)),
                "ocorrencias": n,
                "percentual": (
                    Decimal(n) * 100 / Decimal(total)
                ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                if total else Decimal("0.0"),
            }
            for chave, n in sorted(
                por_categoria.items(), key=lambda par: -par[1]
            )
        ],
    }


def candidatos_da_semana(*, programacao: ProgramacaoSemanal) -> list[dict]:
    """A **área de rascunho** do quadro (planta §5.2): o que o plano diz que
    deveria estar acontecendo nesta semana.

    É sugestão, não imposição — o Last Planner existe justamente porque o plano
    de meses atrás não sabe da obra de hoje. O que a lista faz é poupar o time
    de procurar na WBS; o que ela **não** faz é entrar no quadro sozinha.

    Cada candidato já vem com `restricoes_abertas` e `ja_no_quadro`, porque são
    as duas perguntas que decidem se o cartão pode ser puxado — e resolvê-las
    cartão a cartão seriam duas consultas por linha.
    """
    cronograma = (
        Cronograma.objects.filter(
            tenant_id=programacao.tenant_id, obra_id=programacao.obra_id,
            status=Cronograma.Status.VIGENTE,
        ).first()
    )
    if cronograma is None:
        return []

    atividades = list(
        Atividade.objects.filter(
            tenant_id=programacao.tenant_id, cronograma=cronograma,
            # Só folha: a sintética é o intervalo dos filhos, e comprometer-se
            # com ela seria comprometer-se com a soma de coisas que já estão no
            # quadro cada uma por si. É a mesma recusa que o apontamento faz.
            filhos__isnull=True,
            # As datas do plano são as do CPM (`inicio_cedo`/`termino_cedo`); o
            # recorte é toda atividade que **atravessa** a semana, e não só a que
            # começa nela — serviço de três semanas precisa aparecer nas três.
            inicio_cedo__lte=programacao.semana_fim,
            termino_cedo__gte=programacao.semana_inicio,
        ).order_by("inicio_cedo", "codigo")[
            : PDCA_TETO_ITENS_POR_PROGRAMACAO
        ]
    )
    ids = [a.pk for a in atividades]
    travas = restricoes_abertas_por_atividade(
        ids, tenant_id=programacao.tenant_id
    )
    #: **A qualidade na tela do Last Planner** (PDCA.7). Não é decoração: o
    #: cartão que a equipe está prestes a assumir pode ser um serviço com
    #: defeito aberto, e descobrir isso ao chegar na frente é o que produz o
    #: compromisso que já nasce quebrado. Uma consulta por quadro, não uma por
    #: cartão — a mesma régua das travas acima.
    defeitos = ncs_abertas_por_atividade(ids, tenant_id=programacao.tenant_id)
    ja_no_quadro = set(
        programacao.itens.values_list("atividade_id", flat=True)
    )
    return [
        {
            "atividade": a.pk,
            "codigo": a.codigo,
            "nome": a.nome,
            "inicio_previsto": a.inicio_cedo,
            "fim_previsto": a.termino_cedo,
            "critica": getattr(a, "critica", False),
            "restricoes_abertas": travas.get(a.pk, 0),
            "ncs_abertas": defeitos.get(a.pk, 0),
            "ja_no_quadro": a.pk in ja_no_quadro,
        }
        for a in atividades
    ]


def andamento_dos_itens(programacao: ProgramacaoSemanal) -> dict[int, dict]:
    """`{item: {atual, inicio, meta}}` — o que o julgamento por % precisa saber.

    - `atual`: o acumulado da atividade hoje (a cadeia de versões, pelo código,
      a mesma conta do `avanco_da_atividade`);
    - `inicio`: o acumulado quando a semana começou — o atual menos o que se
      apontou dentro dela;
    - `meta`: onde a atividade tinha de chegar. Com avanço prometido, início +
      prometido; sem ele, o compromisso era **concluir** — 100%.

    Uma consulta por versão do plano, não uma por cartão.
    """
    itens = list(programacao.itens.select_related("atividade__cronograma"))
    if not itens:
        return {}
    por_cronograma: dict[int, list] = {}
    for item in itens:
        por_cronograma.setdefault(item.atividade.cronograma_id, []).append(item)

    resposta: dict[int, dict] = {}
    for grupo in por_cronograma.values():
        cadeia = _cadeia_de_versoes(grupo[0].atividade.cronograma)
        codigos = {i.atividade.codigo for i in grupo}
        base = ApontamentoAvanco.objects.filter(
            atividade__cronograma_id__in=cadeia, atividade__codigo__in=codigos,
        )
        atual = dict(base.values("atividade__codigo")
                     .annotate(t=Sum("percentual")).values_list("atividade__codigo", "t"))
        na_semana = dict(base.filter(data__gte=programacao.semana_inicio,
                                     data__lte=programacao.semana_fim)
                         .values("atividade__codigo")
                         .annotate(t=Sum("percentual")).values_list("atividade__codigo", "t"))
        for item in grupo:
            codigo = item.atividade.codigo
            agora = atual.get(codigo) or _ZERO
            inicio = agora - (na_semana.get(codigo) or _ZERO)
            if item.percentual_previsto is not None:
                meta = min(Decimal("100"), inicio + item.percentual_previsto)
            else:
                meta = Decimal("100")
            resposta[item.pk] = {"atual": agora, "inicio": inicio, "meta": meta}
    return resposta


@transaction.atomic
def julgar_itens(*, programacao: ProgramacaoSemanal,
                 julgamentos: list[dict], por: str = "") -> dict:
    """Julga vários compromissos numa transação — o gesto do fim da semana.

    Vem em lote porque é assim que a reunião acontece: percorre-se o quadro
    inteiro de uma vez. Item a item, uma reunião de 40 cartões seriam 40
    requisições, e a que falhasse no meio deixaria a semana meio julgada.

    A regra de causa é conferida **aqui e no banco** (a `CheckConstraint` do
    modelo): aqui para a mensagem ser legível, lá porque o comando de bancada e
    a importação entram por outras portas.

    **Pelo % concluído** *(decisão do dono, 09/10/2026)*. Quem julga diz quanto
    da atividade está pronto; o servidor:

    1. lança a **diferença** para o acumulado como apontamento de avanço — o
       físico da obra anda com o julgamento, sem digitar duas vezes. Menor que
       o acumulado é recusado: o livro é append-only, e corrigir apontamento é
       estorno com motivo;
    2. decide o `cumprido` do PPC contra a meta da semana
       (`andamento_dos_itens`). O "saiu / não saiu" deixa de ser digitado.

    A linha sem `percentual_concluido` segue o caminho binário de antes — é o
    que o comando de bancada e a tela antiga mandam.
    """
    if programacao.status != ProgramacaoSemanal.Status.COMPROMETIDA:
        raise ValidationError(
            f"Só uma programação comprometida se julga — esta está "
            f"{programacao.get_status_display().lower()}."
        )
    por_id = {
        item.pk: item
        for item in programacao.itens.all()
    }
    causas_validas = set(
        CausaNaoCumprimento.objects.filter(
            tenant_id=programacao.tenant_id
        ).values_list("causa_id", flat=True)
    )
    erros: list[str] = []
    avisos: list[str] = []
    a_gravar: list[ItemProgramacao] = []
    a_apontar: list[tuple[ItemProgramacao, Decimal]] = []
    andamento = (andamento_dos_itens(programacao)
                 if any(l.get("percentual_concluido") is not None for l in julgamentos)
                 else {})
    for linha in julgamentos:
        item = por_id.get(linha.get("item"))
        if item is None:
            erros.append(
                f"O compromisso {linha.get('item')} não é desta semana."
            )
            continue
        cumprido = linha.get("cumprido")
        causa_id = linha.get("causa")
        concluido = linha.get("percentual_concluido")
        if concluido is not None:
            concluido = Decimal(str(concluido))
            conta = andamento.get(item.pk, {"atual": _ZERO, "meta": Decimal("100")})
            if concluido < 0 or concluido > 100:
                erros.append(f"«{item.atividade.nome}»: o concluído vai de 0 a 100%.")
                continue
            if concluido < conta["atual"]:
                erros.append(
                    f"«{item.atividade.nome}» já tem {conta['atual']:.2f}% apontado — o "
                    f"concluído não pode ser menor. Se o apontamento está errado, "
                    f"estorne-o no avanço da atividade."
                )
                continue
            if item.atividade.eh_marco and concluido not in (_ZERO, Decimal("100")):
                erros.append(
                    f"«{item.atividade.nome}» é um marco: 0% (não aconteceu) ou 100%."
                )
                continue
            cumprido = concluido >= conta["meta"]
            if cumprido:
                causa_id = None
            if concluido > conta["atual"]:
                a_apontar.append((item, concluido - conta["atual"]))
            item.percentual_concluido = concluido
        if cumprido is None:
            erros.append(f"Diga se «{item.atividade.nome}» saiu ou não.")
            continue
        if not cumprido and not causa_id:
            # **Avisa, não impede de salvar** *(dono, 11/10/2026)*. O avanço
            # digitado é registrado; o compromisso fica "por julgar" (cumprido
            # nulo, que o banco aceita) até a causa chegar. Quem trava é o
            # `encerrar`, que recusa semana com item por julgar.
            avisos.append(
                f"«{item.atividade.nome}» "
                + (f"ficou em {concluido:.0f}%, abaixo da meta de "
                   f"{andamento[item.pk]['meta']:.0f}%, "
                   if concluido is not None and item.pk in andamento else "não saiu ")
                + "e ainda não tem causa. O avanço foi salvo; a causa é necessária "
                "para encerrar a semana — é dela que sai o ranking que muda a obra."
            )
            item.cumprido = None
            item.causa_id = None
            item.nota = (linha.get("nota") or item.nota or "")[:2000]
            a_gravar.append(item)
            continue
        if cumprido and causa_id:
            erros.append(
                f"«{item.atividade.nome}» está marcado como cumprido e com "
                f"causa de falha. Uma coisa ou outra."
            )
            continue
        if causa_id and causa_id not in causas_validas:
            erros.append(f"A causa {causa_id} não existe no seu catálogo.")
            continue
        item.cumprido = bool(cumprido)
        item.causa_id = causa_id or None
        item.nota = (linha.get("nota") or item.nota or "")[:2000]
        a_gravar.append(item)
    if erros:
        raise ValidationError(erros)

    # O avanço que o julgamento disse — a diferença, com a data dentro da
    # semana para entrar na prova "apontou" do cartão. Dois cartões da mesma
    # atividade (locais diferentes) não lançam a mesma diferença duas vezes.
    lancado: dict[str, Decimal] = {}
    data = min(timezone.localdate(), programacao.semana_fim)
    apontamentos = 0
    for item, delta in a_apontar:
        codigo = item.atividade.codigo
        delta -= lancado.get(codigo, _ZERO)
        if delta <= 0:
            continue
        registrar_apontamento(
            atividade=item.atividade, percentual=delta, data=data,
            local=item.local, observacao=(
                f"Julgamento da semana {programacao.semana_inicio:%d/%m}: "
                f"{item.percentual_concluido:.0f}% concluído."
            ),
            por=por, sincronizar=False,
        )
        lancado[codigo] = lancado.get(codigo, _ZERO) + delta
        apontamentos += 1
    if apontamentos:
        sincronizar_percentual_das_etapas(a_apontar[0][0].atividade.cronograma)

    if a_gravar:
        ItemProgramacao.objects.bulk_update(
            a_gravar, ["cumprido", "causa", "nota", "percentual_concluido"]
        )
    return {"julgados": len(a_gravar) - len(avisos), "apontamentos": apontamentos, "por_julgar": (
        programacao.itens.filter(cumprido__isnull=True).count()
    ), "avisos": avisos}


# ---------------------------------------------------------------------------
# 13. A linha de balanço (PDCA.6) — ritmo, sincronia de equipes e gargalo
# ---------------------------------------------------------------------------
# **O gesto é inverso ao do Gantt** (planta §5.2). Lá o eixo Y é a WBS e a barra
# diz *quanto tempo*; aqui o eixo Y é **localização** e a reta diz *a que ritmo o
# serviço sobe a obra*. A inclinação é a informação, e é por isso que a LOB acha
# o que o Gantt esconde: duas retas que **se cruzam** são duas equipes no mesmo
# lugar ao mesmo tempo, e num Gantt de 800 barras isso não tem forma visível.
#
# **Não há tabela nova** (§4.9). A LOB é derivada de `Atividade` × `LocalObra`:
# a atividade já carrega `local` desde a PDCA.1, e a hierarquia construtiva já
# ordena o eixo Y desde a PDCA.0. Criar um `PacoteRitmo` guardando a inclinação
# criaria a segunda verdade — ela envelheceria no instante em que alguém
# arrastasse uma barra no Gantt, e a mesma obra passaria a ter dois ritmos.
#
# **O serviço é o pai na WBS.** "Alvenaria" é a sintética; "Alvenaria — Pav 3" é
# a folha com `local`. Agrupar por pai não é conveniência: é a mesma convenção de
# sintética × analítica que a §4 usa para tudo, e é o que permite a mesma
# atividade ser barra no Gantt e ponto na reta sem um segundo cadastro.


def _locais_em_ordem(obra_id, *, tenant_id) -> list[LocalObra]:
    """A árvore de locais achatada em ordem de leitura — **o eixo Y da LOB**.

    Profundidade primeiro, seguindo `ordem` entre irmãos: torre, seus pavimentos,
    as unidades de cada um. É a ordem em que a obra sobe, e é o que faz o 10º
    pavimento aparecer acima do 9º — ordenar por código poria "P10" antes de
    "P9" e a reta do serviço desceria no meio do gráfico.

    Uma consulta só; a árvore é montada em memória porque o teto do eixo (§5.5k)
    já garante que ela cabe. A recursão é segura pelo mesmo motivo por que a do
    gerador de locais é: `PDCA_PROFUNDIDADE_MAXIMA_LOCAL` (§5.5c) fecha a árvore
    em 8 níveis **na escrita**, então não há caminho por onde uma hierarquia
    profunda entre e estoure a pilha na leitura.
    """
    todos = list(
        LocalObra.objects.filter(tenant_id=tenant_id, obra_id=obra_id, ativo=True)
        .order_by("profundidade", "ordem", "codigo")
    )
    filhos: dict[int | None, list[LocalObra]] = {}
    for local in todos:
        filhos.setdefault(local.pai_id, []).append(local)
    for lista in filhos.values():
        lista.sort(key=lambda l: (l.ordem, l.codigo))

    ordenados: list[LocalObra] = []

    def descer(pai_id):
        for local in filhos.get(pai_id, []):
            ordenados.append(local)
            descer(local.local_id)

    descer(None)
    return ordenados


def _ritmo(pontos: list[dict]) -> dict:
    """A inclinação da reta, dita de duas formas — **e nenhuma inventada**.

    `locais_por_semana` é como o planejador fala ("subimos um pavimento a cada
    quatro dias"); `dias_por_local` é o número que ele digita ao desenhar a
    linha. As duas são a mesma conta pelos dois lados, e vêm juntas porque a tela
    mostra uma e o formulário pede a outra.

    **Um ponto só não tem ritmo.** Uma reta precisa de dois pontos, e devolver
    zero — ou o inverso da duração, que é a tentação — diria que o serviço tem
    ritmo quando o que existe é um serviço em um lugar. `None`, e a tela escreve
    "sem ritmo".
    """
    if len(pontos) < 2:
        return {"dias_por_local": None, "locais_por_semana": None}
    primeiro = min(p["inicio"] for p in pontos)
    ultimo = max(p["inicio"] for p in pontos)
    vao = (ultimo - primeiro).days
    if vao <= 0:
        # Todos começam no mesmo dia: não é ritmo, é paralelismo total — e
        # dividir por zero aqui seria a pior hora de descobrir isso.
        return {"dias_por_local": Decimal("0.0"), "locais_por_semana": None}
    dias = (Decimal(vao) / Decimal(len(pontos) - 1)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP,
    )
    por_semana = (Decimal(7) / dias).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP,
    ) if dias > 0 else None
    return {"dias_por_local": dias, "locais_por_semana": por_semana}


def _conflitos(pontos_por_local: dict[int, list[dict]],
               rotulo_do_local: dict[int, str]) -> list[dict]:
    """**Duas equipes no mesmo lugar ao mesmo tempo** — o que a LOB existe para achar.

    O cruzamento de duas retas é o *sinal visual*; o fato é este: no mesmo local,
    dois serviços diferentes com janelas que se sobrepõem. Conferir o fato, e não
    a geometria, é o que faz o alerta continuar certo quando o eixo muda de
    escala ou quando duas retas se tocam sem se cruzar.

    **Serviços diferentes**, e não atividades diferentes: duas folhas do mesmo
    serviço no mesmo local ao mesmo tempo são a mesma equipe trabalhando, que é
    legítimo (duas frentes do mesmo empreiteiro). O choque é entre ofícios.
    """
    achados: list[dict] = []
    for local_id, pontos in pontos_por_local.items():
        if len(pontos) < 2:
            continue
        ordenados = sorted(pontos, key=lambda p: p["inicio"])
        for i, a in enumerate(ordenados):
            for b in ordenados[i + 1:]:
                if b["inicio"] > a["fim"]:
                    break            # ordenados por início: os seguintes também não tocam
                if a["servico_id"] == b["servico_id"]:
                    continue
                inicio = max(a["inicio"], b["inicio"])
                fim = min(a["fim"], b["fim"])
                achados.append({
                    "local": local_id,
                    "local_rotulo": rotulo_do_local.get(local_id, ""),
                    "servico_a": a["servico"],
                    "servico_b": b["servico"],
                    "atividade_a": a["atividade"],
                    "atividade_b": b["atividade"],
                    "inicio": inicio,
                    "fim": fim,
                    "dias": (fim - inicio).days + 1,
                })
                if len(achados) >= PDCA_TETO_CONFLITOS_REPORTADOS:
                    return achados
    achados.sort(key=lambda c: (-c["dias"], c["inicio"]))
    return achados


def linha_de_balanco(cronograma: Cronograma, *, tenant_id=None) -> dict:
    """A LOB inteira, derivada — eixo, retas, ritmo, gargalo e choques.

    **Diz o que NÃO está mostrando.** `atividades_sem_local` é o número de folhas
    que ficaram de fora por não terem endereço, e ele vem no corpo de propósito:
    um gráfico que desenha 3 de 40 serviços sem avisar é pior que gráfico
    nenhum — quem olha conclui que a obra tem três frentes. É a mesma régua do
    denominador declarado do PPC (§5.5j) e da cobertura do orçamento (PDCA.1).
    """
    tid = tenant_id if tenant_id is not None else cronograma.tenant_id

    folhas = list(
        Atividade.objects.filter(
            tenant_id=tid, cronograma=cronograma, filhos__isnull=True,
        )
        .select_related("local", "pai")
        .order_by("ordem", "codigo")
    )
    com_local = [
        a for a in folhas
        if a.local_id and a.inicio_cedo and a.termino_cedo
    ]
    sem_local = len(folhas) - len(com_local)

    ordem_dos_locais = _locais_em_ordem(cronograma.obra_id, tenant_id=tid)
    usados = {a.local_id for a in com_local}
    eixo = [l for l in ordem_dos_locais if l.local_id in usados][
        :PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO
    ]
    indice = {l.local_id: i for i, l in enumerate(eixo)}
    rotulo = {l.local_id: f"{l.codigo} · {l.nome}" for l in eixo}

    por_servico: dict[int, dict] = {}
    pontos_por_local: dict[int, list[dict]] = {}
    for a in com_local:
        if a.local_id not in indice:
            continue                     # local além do teto do eixo
        #: O serviço é o **pai**; a folha sem pai é serviço de si mesma — é o
        #: caso do plano raso, e recusá-lo deixaria a LOB vazia justamente na
        #: obra pequena, que é onde ela é mais fácil de ler.
        servico_id = a.pai_id or a.atividade_id
        servico = por_servico.setdefault(servico_id, {
            "servico": servico_id,
            "codigo": a.pai.codigo if a.pai_id else a.codigo,
            "nome": a.pai.nome if a.pai_id else a.nome,
            "pontos": [],
        })
        ponto = {
            "atividade": a.atividade_id,
            "codigo": a.codigo,
            "nome": a.nome,
            "local": a.local_id,
            "local_rotulo": rotulo.get(a.local_id, ""),
            "y": indice[a.local_id],
            "inicio": a.inicio_cedo,
            "fim": a.termino_cedo,
            "critica": a.critica,
        }
        servico["pontos"].append(ponto)
        pontos_por_local.setdefault(a.local_id, []).append({
            **ponto, "servico_id": servico_id,
            "servico": servico["nome"],
        })

    linhas = []
    for dados in por_servico.values():
        dados["pontos"].sort(key=lambda p: p["y"])
        linhas.append({**dados, **_ritmo(dados["pontos"])})
    #: Ordenado pelo primeiro local em que o serviço aparece: a leitura da LOB é
    #: de baixo para cima, e o serviço que abre a obra tem de ser o primeiro da
    #: legenda. Desempate pelo código, para a ordem não dançar entre chamadas.
    linhas.sort(key=lambda s: (s["pontos"][0]["y"] if s["pontos"] else 0, s["codigo"]))
    servicos_cortados = max(0, len(linhas) - PDCA_TETO_LINHAS_DE_BALANCO)
    linhas = linhas[:PDCA_TETO_LINHAS_DE_BALANCO]

    #: **O gargalo é o serviço mais lento, e ele dita o ritmo de todos.** É a
    #: leitura que a LOB tem e o Gantt não: acelerar qualquer outro não adianta
    #: nada, porque o trem anda na velocidade do vagão mais lento.
    candidatos = [s for s in linhas if s["locais_por_semana"] is not None]
    gargalo = min(
        candidatos, key=lambda s: s["locais_por_semana"],
    )["servico"] if candidatos else None

    return {
        "cronograma": cronograma.pk,
        "obra": cronograma.obra_id,
        "eixo": [
            {
                "local": l.local_id, "codigo": l.codigo, "nome": l.nome,
                "nivel": l.nivel, "profundidade": l.profundidade, "y": i,
            }
            for i, l in enumerate(eixo)
        ],
        "linhas": linhas,
        "gargalo": gargalo,
        "conflitos": _conflitos(pontos_por_local, rotulo),
        #: O que ficou de fora, dito em voz alta — ver a docstring.
        "atividades_sem_local": sem_local,
        "locais_alem_do_teto": max(
            0, len({l.local_id for l in ordem_dos_locais if l.local_id in usados})
            - len(eixo),
        ),
        #: E os serviços que o teto do gráfico cortou. Pela mesma razão: com
        #: trinta retas sobrepostas ninguém enxerga qual cruza qual, então o
        #: corte é deliberado — mas um corte silencioso faria o planejador
        #: concluir que o plano tem 40 frentes quando tem 60. **A lista de
        #: choques continua inteira**: o conflito é fato do plano, e escondê-lo
        #: porque a reta dele não coube seria esconder o problema junto com o
        #: desenho.
        "servicos_alem_do_teto": servicos_cortados,
    }


def validar_teto_de_locais_do_ritmo(quantos: int) -> None:
    """Um gesto de desenhar a linha é uma transação — §5.5k do `planos.py`."""
    if quantos > PDCA_TETO_LOCAIS_POR_RITMO:
        raise ValidationError(
            f"Um traço da linha de balanço alcança até "
            f"{_milhar(PDCA_TETO_LOCAIS_POR_RITMO)} locais, e você pediu "
            f"{_milhar(quantos)}. Gerar mais que isso de uma vez cria um plano "
            f"que ninguém revisa antes de publicar — desenhe a torre, confira, "
            f"e desenhe a seguinte."
        )


@transaction.atomic
def gerar_ritmo(*, cronograma: Cronograma, locais: list[int], inicio: date,
                duracao_por_local: int, ritmo_dias: int | None = None,
                pai_id: int | None = None, nome: str = "", codigo: str = "",
                simular: bool = False, tenant_id=None) -> dict:
    """**Desenhar a linha** — o gesto que a planta §5.2 põe no lugar do arrastar.

    Recebe o serviço, a sequência de locais e o ritmo, e produz a fileira de
    atividades com as precedências que fazem a equipe **andar** de um local para
    o seguinte. O planejador digita *"quatro dias por pavimento"* em vez de
    desenhar vinte barras.

    **A precedência é `SS` com atraso, e não `FS`.** É a diferença entre uma LOB
    e uma fila: `FS` faria o pavimento seguinte começar depois de o anterior
    terminar, e o ritmo passaria a ser a duração — impossível representar a
    equipe que sobe a cada dois dias um serviço que leva quatro. Com `SS` e
    atraso igual ao ritmo, a inclinação da reta é **exatamente** o que se pediu,
    e o caso `ritmo < duração` (duas equipes se sobrepondo) fica dizível.

    **Simula por padrão de quem chama.** A mesma régua do gerador de locais da
    PDCA.0: o número tem de ser conhecido antes de o cliente descobrir que gerou
    200 atividades.
    """
    tid = tenant_id if tenant_id is not None else cronograma.tenant_id
    if not cronograma.editavel:
        raise ValidationError(
            "Só um cronograma em rascunho recebe traço novo. Para mudar o plano "
            "vigente, replaneje — a linha de balanço desenha o plano, e o plano "
            "vigente é a régua contra a qual o atraso já está sendo medido."
        )
    if not locais:
        raise ValidationError("Escolha ao menos um local para o serviço percorrer.")
    if duracao_por_local < 1:
        raise ValidationError(
            "A duração em cada local tem de ser de pelo menos um dia. Serviço de "
            "duração zero é marco, e marco não tem ritmo."
        )
    validar_teto_de_locais_do_ritmo(len(locais))

    passo = duracao_por_local if ritmo_dias is None else ritmo_dias
    if passo < 1:
        raise ValidationError(
            "O ritmo tem de ser de pelo menos um dia por local. Ritmo zero faria "
            "todos os locais começarem no mesmo dia — isso não é ritmo, é a obra "
            "inteira de uma vez."
        )

    #: Os locais têm de ser **desta obra**, e vêm na ordem em que foram pedidos —
    #: é o planejador quem decide se a equipe sobe ou desce, e reordenar por
    #: conta própria apagaria a decisão dele.
    achados = {
        l.local_id: l for l in LocalObra.objects.filter(
            tenant_id=tid, obra_id=cronograma.obra_id, local_id__in=locais,
        )
    }
    faltando = [i for i in locais if i not in achados]
    if faltando:
        raise ValidationError(
            f"{len(faltando)} local(is) não são desta obra ou não existem: "
            f"{faltando[:5]}."
        )

    pai = None
    if pai_id:
        pai = Atividade.objects.filter(
            tenant_id=tid, cronograma=cronograma, atividade_id=pai_id,
        ).first()
        if pai is None:
            raise ValidationError("O serviço escolhido não é deste cronograma.")
    elif not (nome or "").strip():
        raise ValidationError(
            "Diga qual é o serviço — ou escolha um que já existe no plano."
        )

    nome_do_servico = (pai.nome if pai else nome).strip()
    raiz = codigo.strip() or (pai.codigo if pai else "")
    if not raiz:
        raise ValidationError("Informe o código da EAP do serviço.")

    #: Continua a numeração do serviço em vez de reiniciar — desenhar a segunda
    #: torre não pode renumerar a primeira por cima.
    ja_existem = Atividade.objects.filter(
        tenant_id=tid, cronograma=cronograma, pai=pai,
    ).count() if pai else 0

    previa = [
        {
            "codigo": f"{raiz}.{ja_existem + i + 1}",
            "nome": f"{nome_do_servico} — {achados[local_id].nome}",
            "local": local_id,
            "local_rotulo": f"{achados[local_id].codigo} · {achados[local_id].nome}",
            "ordem": ja_existem + i + 1,
        }
        for i, local_id in enumerate(locais)
    ]
    resumo = {
        "servico": nome_do_servico,
        "criar": len(previa),
        "duracao_por_local": duracao_por_local,
        "ritmo_dias": passo,
        #: O prazo total do traço, dito antes de gravar: o último local começa
        #: `passo × (n-1)` dias depois do primeiro e leva a duração dele.
        "dias_uteis_total": passo * (len(locais) - 1) + duracao_por_local,
        "previa": previa,
    }
    if simular:
        return {**resumo, "simulado": True, "pai": pai.pk if pai else None}

    validar_teto_de_atividades(cronograma, acrescentando=len(locais) + (0 if pai else 1))

    if pai is None:
        pai = Atividade.objects.create(
            tenant_id=tid, cronograma=cronograma, codigo=raiz,
            nome=nome_do_servico, profundidade=1,
            ordem=Atividade.objects.filter(
                tenant_id=tid, cronograma=cronograma, pai__isnull=True,
            ).count() + 1,
        )

    criadas: list[Atividade] = []
    for linha, local_id in zip(previa, locais):
        criadas.append(Atividade.objects.create(
            tenant_id=tid, cronograma=cronograma, pai=pai,
            codigo=linha["codigo"], nome=linha["nome"],
            ordem=linha["ordem"], profundidade=pai.profundidade + 1,
            duracao_dias=duracao_por_local, local_id=local_id,
        ))

    Precedencia.objects.bulk_create([
        Precedencia(
            tenant_id=tid, origem=criadas[i], destino=criadas[i + 1],
            tipo=Precedencia.Tipo.SS, atraso_dias=passo,
        )
        for i in range(len(criadas) - 1)
    ])

    #: A primeira do traço fica ancorada na data pedida. As seguintes vêm da
    #: rede — é o CPM que as posiciona, e não uma data gravada por este serviço:
    #: duas fontes para a mesma data é como se descobre, tarde, que arrastar a
    #: barra no Gantt não moveu a reta na LOB.
    if criadas:
        criadas[0].nao_comecar_antes_de = inicio
        criadas[0].save(update_fields=["nao_comecar_antes_de"])

    cpm = calcular_cpm(cronograma)
    return {
        **resumo, "simulado": False, "pai": pai.pk,
        "atividades": [a.pk for a in criadas], "cpm": cpm,
    }


def str_decimais(dados):
    """`Decimal` vira string no JSON, recursivamente.

    O `float` do JSON tem 53 bits de mantissa e **não representa centavo
    exatamente** — é a razão de o DRF serializar `DecimalField` como string por
    padrão. Os endpoints que devolvem dicionários montados à mão, fora de um
    serializer, precisam desta passada; sem ela R$ 1.234,57 viraria
    1234.5699999999999 na tela do gestor.

    **Mora aqui, e não no `views`, desde 15/09/2026.** A PDCA.5 devolve o PPC por
    dois caminhos — a ação `encerrar/` (view) e o `ppc` do documento (campo de
    serializer) — e o serializer não pode importar do `views`, que importa dele.
    Com uma cópia em cada lado, um dos caminhos ficaria para trás; foi o que
    aconteceu, e o `pdca5_programacao_test.py` pegou: o índice atravessava como
    número enquanto o `types.ts` do frontend o declarava `string`.
    """
    if isinstance(dados, Decimal):
        return str(dados)
    if isinstance(dados, dict):
        return {chave: str_decimais(valor) for chave, valor in dados.items()}
    if isinstance(dados, (list, tuple)):
        return [str_decimais(valor) for valor in dados]
    return dados


# ---------------------------------------------------------------------------
# 14. A máquina de verificação (PDCA.7) — FVS, NC, 5W2H e eficácia
# ---------------------------------------------------------------------------
# As quatro seções abaixo estão na ordem em que a qualidade acontece: monta-se a
# ficha (14.1), aplica-se no canteiro (14.2), registra-se o que reprovou (14.3) e
# fecha-se o laço verificando se o conserto pegou (14.4).
#
# **Nada aqui é gravado como resultado.** Conformidade, contagem por gravidade e
# ranking de item que mais reprova são derivados no ponto de leitura — §4.9 da
# planta, a mesma régua do PPC e da curva S. Gravar a conformidade obrigaria a
# reescrevê-la a cada item respondido, e a primeira gravação fora desse caminho
# faria o número mentir.

# --- 14.1 A biblioteca de modelos --------------------------------------------
#
# **Não existe modelo de fábrica, e a ausência é a decisão.** O catálogo de
# causas da PDCA.5 nasce semeado porque rótulo de falha é vocabulário comum a
# todo canteiro, e um catálogo vazio faria a primeira reunião inventar texto
# livre. FVS não é isso: ela é o método da empresa escrito — o que ela aprendeu a
# conferir, com o critério numérico que ela adota, e é contra ela que o organismo
# certificador audita. Uma ficha de fábrica seria aplicada sem ser lida, e a
# empresa se certificaria contra o nosso chute. O que a fatia oferece no lugar é
# o `duplicar`, que é o gesto real: quem tem 40 FVS tem 40 variações de 3 linhas.


def validar_teto_de_modelos(tenant_id, *, acrescentando: int = 1) -> None:
    """A biblioteca só serve enquanto for escolhível — §5.5l do `planos.py`."""
    atual = ModeloVerificacao.objects.filter(tenant_id=tenant_id).count()
    if atual + acrescentando > PDCA_TETO_MODELOS_POR_TENANT:
        raise ValidationError(
            f"A biblioteca de modelos do seu plano vai até "
            f"{_milhar(PDCA_TETO_MODELOS_POR_TENANT)} fichas, e você já tem "
            f"{_milhar(atual)}. Desative as que não se aplicam mais — elas "
            f"continuam legíveis em tudo que já foi verificado — em vez de "
            f"acrescentar novas: com mil modelos cadastrados cada engenheiro "
            f"escolhe o seu, e a conformidade de duas obras deixa de ser "
            f"comparável."
        )


def validar_teto_de_itens_do_modelo(modelo: "ModeloVerificacao", *,
                                    acrescentando: int = 1) -> None:
    """A ficha tem de terminar numa visita — §5.5l do `planos.py`."""
    atual = modelo.itens.count()
    if atual + acrescentando > PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO:
        raise ValidationError(
            f"Esta ficha já tem {_milhar(atual)} perguntas, e o teto do seu "
            f"plano é {_milhar(PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO)}. Quem "
            f"responde está de pé no canteiro: ficha que não termina numa "
            f"visita volta pela metade, e ficha pela metade não se distingue de "
            f"serviço reprovado. Quebre-a em duas."
        )


@transaction.atomic
def duplicar_modelo(*, modelo: "ModeloVerificacao", codigo: str, nome: str,
                    por: str = "") -> "ModeloVerificacao":
    """Copia a ficha inteira com os itens — **o gesto real da biblioteca**.

    Quem tem FVS de alvenaria de bloco cerâmico tem a de bloco de concreto, e as
    duas diferem em três linhas. Sem este verbo, a segunda é digitada de novo
    inteira — e é aí que o critério de uma diverge do da outra por descuido, que
    é exatamente o que a biblioteca existe para impedir.
    """
    validar_teto_de_modelos(modelo.tenant_id)
    if not (codigo or "").strip():
        raise ValidationError("A cópia precisa de um código próprio.")

    copia = ModeloVerificacao.objects.create(
        tenant_id=modelo.tenant_id,
        codigo=codigo.strip(),
        nome=(nome or f"{modelo.nome} (cópia)").strip(),
        dominio=modelo.dominio,
        descricao=modelo.descricao,
        criado_por=por or "",
    )
    ItemModeloVerificacao.objects.bulk_create([
        ItemModeloVerificacao(
            tenant_id=modelo.tenant_id, modelo=copia, ordem=item.ordem,
            texto=item.texto, criterio=item.criterio,
            obrigatorio=item.obrigatorio, exige_foto=item.exige_foto,
        )
        for item in modelo.itens.all()
    ])
    return copia


# --- 14.2 A ficha aplicada ---------------------------------------------------


@transaction.atomic
def aplicar_verificacao(*, modelo: "ModeloVerificacao", obra, data: date,
                        local_id=None, atividade_id=None, inspetor: str = "",
                        por: str = "", tenant_id=None) -> "Verificacao":
    """Abre a ficha **copiando as perguntas para dentro dela**.

    **Não se chama `aplicar_modelo`, e o nome custou uma volta.** Este módulo já
    tem um `aplicar_modelo` desde a PDCA.1b — o que aplica um *plano modelo* a
    uma obra nova. Escrever o segundo com o mesmo nome não deu erro de import
    nenhum: o de baixo simplesmente passou a valer para os dois, e quem quebrou
    foi o **cronograma**, numa chamada que nada tinha a ver com qualidade. Duas
    bibliotecas de padrões no mesmo módulo é um fato do domínio (a do plano e a
    da ficha), então o desempate fica no nome do que se aplica, não no verbo.

    A cópia é a razão de este serviço existir em vez de um `POST` cru: sem ela a
    ficha leria o texto pelo FK e toda inspeção passada mudaria de sentido no dia
    em que a empresa apertasse um critério. Ver a docstring do `ItemVerificacao`.

    **Modelo inativo não se aplica.** `ativo=False` quer dizer "pare de oferecer
    esta ficha", e aplicá-la assim mesmo produziria inspeção contra um método que
    a empresa já abandonou — com a assinatura de alguém embaixo.

    **Modelo sem item também não.** Uma ficha de zero perguntas conclui com 100%
    de conformidade sem ninguém ter olhado nada, que é o pior número que este
    módulo poderia produzir.
    """
    if not modelo.ativo:
        raise ValidationError(
            f"O modelo '{modelo.codigo}' está inativo — ele saiu da lista de "
            f"escolha porque a empresa deixou de usá-lo. Reative-o se ele "
            f"voltou a valer, ou escolha o que o substituiu: inspecionar contra "
            f"um método abandonado registra uma conformidade que não significa "
            f"nada."
        )
    itens_modelo = list(modelo.itens.all().order_by("ordem", "item_modelo_id"))
    if not itens_modelo:
        raise ValidationError(
            f"O modelo '{modelo.codigo}' não tem nenhuma pergunta. Uma ficha "
            f"vazia conclui com 100% de conformidade sem ninguém ter olhado "
            f"nada — monte os itens antes de aplicá-la."
        )

    tenant_id = tenant_id if tenant_id is not None else modelo.tenant_id
    verificacao = Verificacao.objects.create(
        tenant_id=tenant_id, modelo=modelo, obra=obra, local_id=local_id,
        atividade_id=atividade_id, inspetor=inspetor or "", data=data,
        criada_por=por or "",
    )
    ItemVerificacao.objects.bulk_create([
        ItemVerificacao(
            tenant_id=tenant_id, verificacao=verificacao, item_modelo=item,
            ordem=item.ordem or (i + 1),
            # O congelamento. Ver a docstring do `ItemVerificacao`.
            texto=item.texto, criterio=item.criterio,
            obrigatorio=item.obrigatorio, exige_foto=item.exige_foto,
        )
        for i, item in enumerate(itens_modelo)
    ])
    return verificacao


def _exige_observacao(resultado: str) -> bool:
    return resultado in (
        ResultadoItem.NAO_CONFORME, ResultadoItem.NAO_APLICAVEL,
    )


@transaction.atomic
def responder_itens(*, verificacao: "Verificacao", respostas: list[dict],
                    por: str = "") -> dict:
    """Grava as respostas do campo — **numa transação, o lote inteiro**.

    O instrumento do campo responde uma pergunta por vez (planta §5.2), mas a
    **gravação** é em lote pela mesma razão do julgamento da PDCA.5: item a item
    seriam N requisições, e a que falhasse no meio deixaria a ficha meio
    respondida sem ninguém saber onde parou. A tela acumula e grava.

    **Desvio exige observação**, e a recusa nomeia o item — "o item 7 reprovou
    sem dizer o quê" é acionável; "erro de validação" não é.
    """
    if not verificacao.esta_aberta:
        raise ValidationError(
            "Esta ficha já foi concluída: ela virou prova e não recebe mais "
            "resposta. Corrigir uma inspeção concluída é reinspecionar — "
            "aplique o modelo de novo, que é o que o canteiro também exige."
        )

    por_id = {
        item.pk: item
        for item in verificacao.itens.select_related(None).all()
    }
    agora = timezone.now()
    tocados = []
    for linha in respostas:
        item = por_id.get(linha.get("item_verificacao"))
        if item is None:
            raise ValidationError(
                f"O item {linha.get('item_verificacao')} não é desta ficha."
            )
        resultado = linha.get("resultado") or ResultadoItem.PENDENTE
        observacao = (linha.get("observacao") or "").strip()
        gravidade = linha.get("gravidade") or None
        if _exige_observacao(resultado) and not observacao:
            rotulo = dict(ResultadoItem.choices)[resultado].lower()
            raise ValidationError(
                f"O item {item.ordem} ficou como '{rotulo}' sem explicação. "
                f"Diga o quê: não conforme sem o defeito descrito não vira ação "
                f"nenhuma, e não aplicável sem o motivo é a porta pela qual uma "
                f"ficha inteira passa sem ninguém verificar coisa alguma."
            )
        #: **A gravidade é perguntada aqui, no item**, e não uma vez na
        #: conclusão da ficha (decisão do dono, 16/09/2026 — ver a docstring do
        #: campo). Quem acabou de olhar o defeito sabe se ele se corrige na hora
        #: ou se para o serviço; quem lê a lista depois, não.
        if resultado == ResultadoItem.NAO_CONFORME and not gravidade:
            raise ValidationError(
                f"O item {item.ordem} reprovou sem dizer **quanto** pesa. Um "
                f"desalinhamento que se corrige na frente e a falta de uma peça "
                f"que impede aceitar o serviço são dois defeitos diferentes, e "
                f"contá-los com o mesmo rótulo faz o painel de gravidade deixar "
                f"de servir para escolher o que tratar primeiro."
            )
        item.resultado = resultado
        item.observacao = observacao
        #: Só o reprovado guarda gravidade — o `None` aqui é o que limpa a
        #: escolha de quem marcou "não conforme", pesou, e depois corrigiu para
        #: "conforme". Sem esta linha a gravidade órfã ficaria contada no painel.
        item.gravidade = (
            gravidade if resultado == ResultadoItem.NAO_CONFORME else None
        )
        if "nota" in linha and linha["nota"] is not None:
            item.observacao = (linha["nota"] or "").strip() or item.observacao
        item.respondido_em = agora if resultado != ResultadoItem.PENDENTE else None
        item.respondido_por = por or "" if resultado != ResultadoItem.PENDENTE else ""
        tocados.append(item)

    if tocados:
        ItemVerificacao.objects.bulk_update(
            tocados,
            ["resultado", "observacao", "gravidade", "respondido_em",
             "respondido_por"],
        )
    return {
        "respondidos": len(tocados),
        "resultado": resultado_da_verificacao(verificacao),
    }


def resultado_da_verificacao(verificacao: "Verificacao") -> dict:
    """As contagens e a conformidade — **derivadas, nunca gravadas** (§4.9).

    **`nao_aplicavel` fica fora do denominador**, e essa é a única escolha
    honesta: um item que não se aplica àquela frente não é um acerto nem um erro,
    e contá-lo como conforme inflaria a conformidade de toda ficha longa aplicada
    a um serviço pequeno.

    **`conformidade` é `None` enquanto nada foi respondido**, na mesma régua do
    PPC da semana aberta e do avanço sem apontamento: a tela mostra "sem
    apuração", nunca 0% — fabricar uma reprovação que ainda não aconteceu é o
    pecado que este módulo persegue desde a PDCA.2.
    """
    contagem = {
        chave: 0 for chave, _rotulo in ResultadoItem.choices
    }
    for linha in (
        verificacao.itens.values("resultado").annotate(n=Count("item_verificacao_id"))
    ):
        contagem[linha["resultado"]] = linha["n"]

    conformes = contagem[ResultadoItem.CONFORME]
    nao_conformes = contagem[ResultadoItem.NAO_CONFORME]
    julgados = conformes + nao_conformes
    conformidade = (
        (Decimal(conformes) * 100 / Decimal(julgados)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        if julgados
        else None
    )
    return {
        "verificacao": verificacao.pk,
        "status": verificacao.status,
        "total": sum(contagem.values()),
        "conformes": conformes,
        "nao_conformes": nao_conformes,
        "nao_aplicaveis": contagem[ResultadoItem.NAO_APLICAVEL],
        "pendentes": contagem[ResultadoItem.PENDENTE],
        "conformidade": conformidade,
        "apurada": verificacao.status == Verificacao.Status.CONCLUIDA,
    }


def resultados_das_verificacoes(verificacoes: list, *, tenant_id) -> dict:
    """O mesmo de cima, para **uma página inteira, em uma consulta**.

    A leitura por ficha (`resultado_da_verificacao`) faz uma agregação cada;
    uma lista de 50 fichas faria 50. É o D136 exatamente — a listagem de
    medições que trazia ~200 consultas para desenhar uma tabela —, e a correção
    é a mesma: agrupar por documento de uma vez e distribuir em memória.
    """
    ids = [v.pk for v in verificacoes]
    if not ids:
        return {}

    contagens: dict[int, dict[str, int]] = {
        vid: {chave: 0 for chave, _r in ResultadoItem.choices} for vid in ids
    }
    for linha in (
        ItemVerificacao.objects.filter(
            tenant_id=tenant_id, verificacao_id__in=ids,
        )
        .values("verificacao_id", "resultado")
        .annotate(n=Count("item_verificacao_id"))
    ):
        contagens[linha["verificacao_id"]][linha["resultado"]] = linha["n"]

    saida = {}
    for verificacao in verificacoes:
        contagem = contagens[verificacao.pk]
        conformes = contagem[ResultadoItem.CONFORME]
        nao_conformes = contagem[ResultadoItem.NAO_CONFORME]
        julgados = conformes + nao_conformes
        saida[verificacao.pk] = {
            "verificacao": verificacao.pk,
            "status": verificacao.status,
            "total": sum(contagem.values()),
            "conformes": conformes,
            "nao_conformes": nao_conformes,
            "nao_aplicaveis": contagem[ResultadoItem.NAO_APLICAVEL],
            "pendentes": contagem[ResultadoItem.PENDENTE],
            "conformidade": (
                (Decimal(conformes) * 100 / Decimal(julgados)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                if julgados
                else None
            ),
            "apurada": verificacao.status == Verificacao.Status.CONCLUIDA,
        }
    return saida


@transaction.atomic
def concluir_verificacao(*, verificacao: "Verificacao", por: str = "") -> dict:
    """Fecha a ficha — **e recusa deixar pergunta obrigatória sem resposta**.

    `obrigatorio` é do item, e é o que permite a ficha longa ser concluída sem a
    pergunta acessória sobre a qual ninguém tem o que dizer. O que ela não
    permite é concluir com o essencial em branco: a ficha assinada com 6 dos 18
    itens respondidos é pior que nenhuma, porque parece completa.

    **Devolve os reprovados que ainda não viraram NC.** O ato de abrir a NC
    continua explícito (tem permissão própria), mas a tela precisa saber o que
    oferecer — sem isso, o item que reprovou fica no papel e o laço não começa.
    """
    if not verificacao.esta_aberta:
        raise ValidationError("Esta ficha já está concluída.")

    pendentes = list(
        verificacao.itens.filter(
            obrigatorio=True, resultado=ResultadoItem.PENDENTE,
        ).values_list("ordem", flat=True)
    )
    if pendentes:
        quais = ", ".join(str(o) for o in pendentes[:10])
        resto = f" (e mais {len(pendentes) - 10})" if len(pendentes) > 10 else ""
        raise ValidationError(
            f"Faltam responder os itens obrigatórios {quais}{resto}. Uma ficha "
            f"assinada com o essencial em branco é pior do que nenhuma: ela "
            f"parece completa. Responda, ou marque como não aplicável dizendo o "
            f"porquê."
        )

    verificacao.status = Verificacao.Status.CONCLUIDA
    verificacao.concluida_em = timezone.now()
    verificacao.concluida_por = por or ""
    verificacao.save(update_fields=["status", "concluida_em", "concluida_por"])

    #: A gravidade vem junto: a tela de conclusão **mostra** o que vai abrir e
    #: com que peso, em vez de perguntar um peso só para todos. Cada item já foi
    #: pesado por quem o reprovou (§11.15).
    reprovados = list(
        verificacao.itens.filter(resultado=ResultadoItem.NAO_CONFORME)
        .exclude(nao_conformidades__isnull=False)
        .values("item_verificacao_id", "ordem", "texto", "observacao",
                "gravidade")
    )
    rotulos = dict(GravidadeNC.choices)
    for linha in reprovados:
        linha["gravidade_rotulo"] = rotulos.get(linha["gravidade"], "")
    return {
        "resultado": resultado_da_verificacao(verificacao),
        "reprovados_sem_nc": reprovados,
    }


# --- 14.3 A não-conformidade e o tratamento ----------------------------------


def validar_teto_de_ncs(obra_id, *, tenant_id, acrescentando: int = 1) -> None:
    """A NC existe para ser encerrada — §5.5l do `planos.py`."""
    atual = NaoConformidade.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
        status__in=[
            NaoConformidade.Status.ABERTA,
            NaoConformidade.Status.EM_TRATAMENTO,
        ],
    ).count()
    if atual + acrescentando > PDCA_TETO_NCS_ABERTAS_POR_OBRA:
        raise ValidationError(
            f"Esta obra já tem {_milhar(atual)} não-conformidades em aberto, e "
            f"o teto do seu plano é "
            f"{_milhar(PDCA_TETO_NCS_ABERTAS_POR_OBRA)}. Um log com milhares de "
            f"linhas abertas não é controle de qualidade: é um aterro onde a NC "
            f"que vai virar retrabalho caro fica invisível. Trate ou cancele o "
            f"que já não vale antes de abrir mais."
        )


def validar_teto_de_acoes(nc: "NaoConformidade", *,
                          acrescentando: int = 1) -> None:
    """§5.5l — NC que pede vinte ações não é uma NC."""
    atual = nc.acoes.count()
    if atual + acrescentando > PDCA_TETO_ACOES_POR_NC:
        raise ValidationError(
            f"Esta não-conformidade já tem {_milhar(atual)} planos de ação, e o "
            f"teto do seu plano é {_milhar(PDCA_TETO_ACOES_POR_NC)}. Uma NC que "
            f"pede tantas ações não é uma NC: é um problema que precisa ser "
            f"quebrado em vários — e quebrado, cada um encerra o seu."
        )


def ncs_abertas_por_atividade(atividade_ids: list[int],
                              *, tenant_id) -> dict[int, int]:
    """`{atividade_id: quantas NCs abertas}` — **em uma consulta**.

    Irmão do `restricoes_abertas_por_atividade`, e existe pelo mesmo motivo: é o
    quadro inteiro que pergunta de uma vez. É o que põe a qualidade na tela do
    Last Planner — o cartão da semana diz que aquele serviço tem defeito aberto,
    em vez de a equipe descobrir isso ao chegar na frente.
    """
    if not atividade_ids:
        return {}
    linhas = (
        NaoConformidade.objects.filter(
            tenant_id=tenant_id,
            atividade_id__in=atividade_ids,
            status__in=[
                NaoConformidade.Status.ABERTA,
                NaoConformidade.Status.EM_TRATAMENTO,
            ],
        )
        .values("atividade_id")
        .annotate(n=Count("nc_id"))
    )
    return {linha["atividade_id"]: linha["n"] for linha in linhas}


@transaction.atomic
def abrir_ncs_dos_reprovados(*, verificacao: "Verificacao",
                             por: str = "") -> dict:
    """Abre uma NC por item reprovado que ainda não tem uma — **idempotente**.

    É o gesto que sai da conclusão da ficha: o técnico acabou de percorrer 18
    perguntas e 2 reprovaram, e obrigá-lo a redigitar endereço, obra e descrição
    duas vezes é o que faz a NC não ser aberta. A descrição nasce da **pergunta
    congelada mais a observação dele**, que juntas já dizem o que está errado.

    **Cada NC nasce com a gravidade do SEU item**, e este serviço não recebe
    gravidade nenhuma por parâmetro. A primeira escrita desta fatia recebia uma
    e a carimbava em todas — *(decisão do dono, 16/09/2026: "aí fica parecendo
    que um desalinhamento na porta é grave igual a falta de uma maçaneta")*. A
    gravidade é propriedade do defeito e foi respondida no item, por quem estava
    olhando para ele.

    Chamar de novo não duplica: o item que já gerou NC fica de fora.
    """
    reprovados = list(
        verificacao.itens.filter(resultado=ResultadoItem.NAO_CONFORME)
        .exclude(nao_conformidades__isnull=False)
        .order_by("ordem")
    )
    if not reprovados:
        return {"abertas": 0, "ncs": []}

    validar_teto_de_ncs(
        verificacao.obra_id, tenant_id=verificacao.tenant_id,
        acrescentando=len(reprovados),
    )

    criadas = []
    for item in reprovados:
        nc = NaoConformidade.objects.create(
            tenant_id=verificacao.tenant_id,
            obra_id=verificacao.obra_id,
            local_id=verificacao.local_id,
            atividade_id=verificacao.atividade_id,
            item_verificacao=item,
            #: A do item. O `or MENOR` é rede, não regra: a `CheckConstraint`
            #: garante que todo reprovado tem uma, e o fallback só alcança linha
            #: anterior à trava.
            gravidade=item.gravidade or GravidadeNC.MENOR,
            descricao=(
                f"{item.texto.strip()}"
                + (f" — {item.observacao.strip()}" if item.observacao else "")
            ),
            # A foto da evidência viaja junto: ela é a prova do defeito, e
            # obrigar a fotografar de novo a mesma parede é o que faz a NC
            # chegar ao projetista sem imagem.
            foto=item.foto or None,
            aberta_por=por or "",
        )
        criadas.append(nc)
    return {"abertas": len(criadas), "ncs": [nc.pk for nc in criadas]}


@transaction.atomic
def gerar_restricao_da_nc(*, nc: "NaoConformidade", prazo: date | None = None,
                          responsavel: str = "", por: str = "") -> int:
    """NC → **`Restricao` no Last Planner**. O seam vivo com a PDCA.5.

    **É o que dá dente à gravidade.** Sem este elo, "crítica — para o serviço"
    seria adjetivo: o sistema diria que o serviço está parado e a equipe se
    comprometeria com ele na segunda-feira seguinte, porque o quadro da PDCA.5 só
    olha `Restricao`. Com ele, a atividade deixa de poder entrar na programação
    até que alguém declare a trava removida — que é exatamente o que "parar o
    serviço" significa no vocabulário que o módulo já tem.

    **Exige a atividade.** A restrição pende de uma atividade por decisão da
    PDCA.5 (restrição sem alvo não bloqueia nada), e a NC do canteiro nem sempre
    tem uma — a trinca vista a caminho do almoxarifado não sabe de que serviço
    veio. A recusa diz isso em vez de criar uma trava que não trava.

    **Uma NC gera uma restrição.** Chamar de novo devolve a que já existe, na
    régua do `gerar_demanda_scm`: o botão fica na tela e alguém clica duas vezes.
    """
    if nc.restricao_id:
        return nc.restricao_id
    if not nc.atividade_id:
        raise ValidationError(
            "Esta não-conformidade não aponta para uma atividade, e restrição "
            "sem alvo não trava nada. Vincule a NC ao "
            "serviço em que o defeito está antes de parar a frente."
        )
    if not nc.esta_aberta:
        raise ValidationError(
            "Só não-conformidade aberta trava serviço — a que já foi encerrada "
            "não impede mais ninguém de trabalhar."
        )

    validar_teto_de_restricoes(
        nc.obra_id, tenant_id=nc.tenant_id,
    )
    restricao = Restricao.objects.create(
        tenant_id=nc.tenant_id,
        atividade_id=nc.atividade_id,
        local_id=nc.local_id,
        # **`AREA`, e não um tipo novo.** A oitava família da PDCA.5 é "a frente
        # anterior não liberou o local", e é literalmente o que uma NC aberta
        # faz: o serviço está lá, executado errado, e a frente seguinte não
        # entra. Criar um nono tipo `qualidade` partiria o ranking de restrição
        # em dois vocabulários para o mesmo impedimento físico.
        tipo=TipoRestricao.AREA,
        descricao=(
            f"NC #{nc.nc_id} ({nc.get_gravidade_display()}) — "
            f"{nc.descricao.strip()[:400]}"
        ),
        responsavel=responsavel or "",
        prazo=prazo,
        criada_por=por or "",
    )
    nc.restricao = restricao
    nc.save(update_fields=["restricao"])
    return restricao.pk


@transaction.atomic
def concluir_acao(*, plano: "PlanoAcao", por: str = "") -> "PlanoAcao":
    """Marca o 5W2H como executado — **e isso não encerra a NC**.

    A distinção é a razão de a PDCA.7 existir como laço e não como lista: "ação
    concluída" é quem consertou dizendo que consertou. O que fecha a NC é alguém
    **voltar à frente e olhar** (§4.5), e é por isso que o encerramento pede
    `VerificacaoEficacia` e não este carimbo.
    """
    if plano.status == PlanoAcao.Status.CONCLUIDA:
        return plano
    if plano.status == PlanoAcao.Status.CANCELADA:
        raise ValidationError(
            "Este plano de ação foi cancelado — um plano cancelado não se "
            "conclui. Abra outro se a ação voltou a valer."
        )
    plano.status = PlanoAcao.Status.CONCLUIDA
    plano.concluida_em = timezone.now()
    plano.concluida_por = por or ""
    plano.save(update_fields=["status", "concluida_em", "concluida_por"])
    return plano


# --- 14.4 O laço: eficácia e encerramento ------------------------------------


def eficacia_vigente(nc: "NaoConformidade") -> "VerificacaoEficacia | None":
    """A **última** verificação de eficácia — a que vale.

    A sequência inteira fica registrada (o modelo é append-only na prática), mas
    quem decide se a NC pode encerrar é sempre a mais recente: uma NC verificada
    como eficaz em março e reaberta em maio por ter voltado a falhar não pode
    encerrar pela leitura de março.
    """
    return nc.eficacias.order_by("-data", "-eficacia_id").first()


@transaction.atomic
def registrar_eficacia(*, nc: "NaoConformidade", data: date, eficaz: bool,
                       evidencia: str, por: str = "") -> dict:
    """Registra se o conserto pegou — **e o "não" é o resultado mais útil**.

    Eficaz devolve a NC pronta para encerrar; não eficaz a **devolve para
    tratamento**, porque o plano anterior comprovadamente não resolveu e o que
    vem a seguir é um plano novo. Nenhum dos dois apaga a verificação anterior: a
    sequência delas é a história honesta de quantas tentativas o conserto levou.

    A `evidencia` é obrigatória pela mesma razão que a `nota_remocao` da
    restrição é: um `True` sem história não é verificação de eficácia, é um
    carimbo — e é contra isso que a auditoria do PBQP-H olha.
    """
    if nc.status == NaoConformidade.Status.CANCELADA:
        raise ValidationError(
            "Esta NC foi cancelada — não há o que verificar. Cancelada quer "
            "dizer que ela não era uma não-conformidade; se era, reabra-a em "
            "vez de verificar a eficácia de um tratamento que não houve."
        )
    if not (evidencia or "").strip():
        raise ValidationError(
            "Diga o que você olhou para concluir isso. Verificação de eficácia "
            "sem evidência é um carimbo — e é exatamente o que a auditoria "
            "procura quando quer saber se o sistema de qualidade funciona."
        )

    registro = VerificacaoEficacia.objects.create(
        tenant_id=nc.tenant_id, nao_conformidade=nc, data=data,
        eficaz=eficaz, evidencia=evidencia.strip(), verificada_por=por or "",
    )
    if not eficaz and nc.status != NaoConformidade.Status.EM_TRATAMENTO:
        nc.status = NaoConformidade.Status.EM_TRATAMENTO
        nc.save(update_fields=["status"])
    return {
        "eficacia": registro.pk,
        "eficaz": eficaz,
        "nc_status": nc.status,
        "pode_encerrar": bool(eficaz),
    }


@transaction.atomic
def encerrar_nc(*, nc: "NaoConformidade", por: str = "",
                nota: str = "") -> "NaoConformidade":
    """Fecha a NC — **e recusa fechar sem eficácia verificada** (§4.5).

    É a trava que separa tratar de arquivar, e é o padrão do SAP QM. Sem ela,
    "plano de ação concluído" viraria o carimbo que fecha a NC e ninguém
    voltaria à frente para ver se o conserto pegou — que é como a maior parte
    dos sistemas de qualidade perde o valor inteiro do ciclo.

    A regra mora aqui, e não numa `CheckConstraint`, por uma razão física: ela
    olha **outra tabela** (`VerificacaoEficacia`), e check de banco não atravessa
    tabela. O que o banco protege é o que cabe numa linha.
    """
    if nc.status == NaoConformidade.Status.ENCERRADA:
        return nc
    if nc.status == NaoConformidade.Status.CANCELADA:
        raise ValidationError(
            "Esta NC está cancelada. Cancelar e encerrar são coisas "
            "diferentes de propósito: encerrada é defeito tratado, cancelada é "
            "registro que não era defeito — contar as duas juntas inflaria a "
            "leitura de quanto esta obra conserta de fato."
        )

    vigente = eficacia_vigente(nc)
    if vigente is None:
        raise ValidationError(
            "Esta não-conformidade ainda não teve a eficácia verificada. O que "
            "fecha uma NC não é o plano de ação estar concluído — é alguém "
            "voltar à frente e registrar que o conserto pegou. Sem isso, o "
            "sistema arquiva em vez de tratar."
        )
    if not vigente.eficaz:
        raise ValidationError(
            f"A última verificação de eficácia, de {vigente.data:%d/%m/%Y}, "
            f"disse que o tratamento **não** funcionou. Monte um plano de ação "
            f"novo e verifique de novo — encerrar agora registraria como "
            f"resolvido um defeito que a própria empresa constatou que continua "
            f"lá."
        )

    # D191 — a mesma trava de `encerrar_ocorrencia`: encerrar por cima de uma
    # restrição aberta deixaria a frente fora do quadro da semana sem nada
    # explicando por quê. Remover a trava é ato de quem responde pela obra
    # (`pdca.restricao.remover`), e não efeito colateral de um encerramento.
    restricao = nc.restricao
    if restricao is not None and restricao.status == Restricao.Status.ABERTA:
        raise ValidationError(
            f"A frente continua interditada pela restrição #{restricao.pk}, "
            f"aberta por esta não-conformidade. Encerrar aqui deixaria o "
            f"serviço travado sem nada explicando por quê. Declare que o "
            f"risco cessou removendo a restrição — é ato de quem responde "
            f"pela obra."
        )

    nc.status = NaoConformidade.Status.ENCERRADA
    nc.encerrada_em = timezone.now()
    nc.encerrada_por = por or ""
    nc.nota_encerramento = (nota or "").strip()
    nc.save(update_fields=[
        "status", "encerrada_em", "encerrada_por", "nota_encerramento",
    ])
    return nc


def estado_da_nc(nc: "NaoConformidade") -> dict:
    """O que falta nesta NC — **derivado**, para a fila de decisão e o cartão.

    Existe para a tela não precisar reimplementar a regra do encerramento em
    JavaScript. Foi o que o D138 ensinou do outro lado: a mesma conta feita nos
    dois lugares vira dois números para a mesma pergunta.
    """
    acoes = list(nc.acoes.all())
    vigente = eficacia_vigente(nc)
    hoje = timezone.localdate()
    vencidas = [
        a for a in acoes
        if a.quando and a.quando < hoje
        and a.status in (PlanoAcao.Status.PLANEJADA, PlanoAcao.Status.EM_EXECUCAO)
    ]
    return {
        "acoes": len(acoes),
        "acoes_concluidas": sum(
            1 for a in acoes if a.status == PlanoAcao.Status.CONCLUIDA
        ),
        "acoes_vencidas": len(vencidas),
        "tem_preventiva": any(a.tipo == PlanoAcao.Tipo.PREVENTIVA for a in acoes),
        "eficacia_verificada": vigente is not None,
        "eficaz": None if vigente is None else vigente.eficaz,
        "pode_encerrar": bool(vigente and vigente.eficaz),
        # O que a tela escreve no cartão, numa frase. É a mesma ideia do
        # "prometeu 20 pts · campo apontou 12 pts" da PDCA.5: a fila de decisão
        # só serve se disser o que fazer a seguir.
        "falta": _o_que_falta(nc, acoes, vigente),
    }


def _o_que_falta(nc, acoes, vigente) -> str:
    if nc.status == NaoConformidade.Status.ENCERRADA:
        return ""
    if nc.status == NaoConformidade.Status.CANCELADA:
        return ""
    if not acoes:
        return "montar o plano de ação"
    if any(
        a.status in (PlanoAcao.Status.PLANEJADA, PlanoAcao.Status.EM_EXECUCAO)
        for a in acoes
    ):
        return "executar o plano de ação"
    if vigente is None:
        return "verificar a eficácia"
    if not vigente.eficaz:
        return "o tratamento não funcionou — montar plano novo"
    return "encerrar"


def fila_da_qualidade(*, obra_id, tenant_id) -> dict:
    """**A fila de decisão do cockpit** — o que espera alguém, agora.

    Quatro filas, e a ordem é a do laço: NC sem plano (ninguém pegou), plano
    vencido (alguém pegou e não fez), NC esperando eficácia (foi feito e ninguém
    conferiu) e ficha parada em andamento (a inspeção que começou e não terminou).

    É a régua de módulo do projeto — cockpit com fila de decisão real, não um
    hub que soma o que não se soma.
    """
    hoje = timezone.localdate()
    abertas = list(
        NaoConformidade.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id,
            status__in=[
                NaoConformidade.Status.ABERTA,
                NaoConformidade.Status.EM_TRATAMENTO,
            ],
        )
        .select_related("local", "atividade")
        .prefetch_related("acoes", "eficacias")
    )

    sem_plano, esperando_eficacia = [], []
    for nc in abertas:
        estado = estado_da_nc(nc)
        linha = {
            "nc": nc.pk,
            "gravidade": nc.gravidade,
            "gravidade_rotulo": nc.get_gravidade_display(),
            "descricao": nc.descricao[:160],
            "local_rotulo": nc.local.nome if nc.local_id else None,
            "atividade_nome": nc.atividade.nome if nc.atividade_id else None,
            "falta": estado["falta"],
            #: **Há quanto tempo isto espera.** Faltava, e a ausência só
            #: apareceu quando a fila do dia passou a pôr as onze faixas lado a
            #: lado: uma linha de NC sem data fica em branco na única coluna
            #: que ordena a fila inteira, e um defeito de ontem se lê igual a
            #: um de março.
            "aberta_em": nc.aberta_em,
        }
        if estado["acoes"] == 0:
            sem_plano.append(linha)
        elif estado["acoes_concluidas"] == estado["acoes"] and not estado["eficacia_verificada"]:
            esperando_eficacia.append(linha)

    vencidos = [
        {
            "plano": a.pk,
            "nc": a.nao_conformidade_id,
            "o_que": a.o_que[:160],
            "quem": a.quem,
            "quando": a.quando,
            "dias_vencido": (hoje - a.quando).days,
        }
        for a in PlanoAcao.objects.filter(
            tenant_id=tenant_id,
            nao_conformidade__obra_id=obra_id,
            quando__lt=hoje,
            status__in=[PlanoAcao.Status.PLANEJADA, PlanoAcao.Status.EM_EXECUCAO],
        ).order_by("quando")[:PDCA_TETO_NCS_ABERTAS_POR_OBRA]
    ]

    paradas = [
        {
            "verificacao": v.pk,
            "modelo_nome": v.modelo.nome,
            "data": v.data,
            "inspetor": v.inspetor,
            "dias_parada": (hoje - v.data).days,
        }
        for v in Verificacao.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id,
            status=Verificacao.Status.EM_ANDAMENTO,
        ).select_related("modelo").order_by("data")
    ]

    return {
        "obra": obra_id,
        "ncs_sem_plano": sem_plano,
        "acoes_vencidas": vencidos,
        "ncs_esperando_eficacia": esperando_eficacia,
        "fichas_em_andamento": paradas,
        "total": (
            len(sem_plano) + len(vencidos) + len(esperando_eficacia) + len(paradas)
        ),
    }


def painel_de_conformidade(*, obra_id, tenant_id, desde: date | None = None,
                           ate: date | None = None) -> dict:
    """**O "Act" da qualidade** — conformidade por domínio e o que mais reprova.

    Irmão declarado do `ranking_de_causas` da PDCA.5, e existe pela mesma razão:
    o índice diz *quanto* falhou, e só o ranking diz *o quê* mudar. A leitura que
    decide alguma coisa aqui é a terceira — **qual pergunta reprova mais** —,
    porque é ela que aponta o processo a corrigir em vez do serviço a refazer.

    O agrupamento do ranking é pelo **item do modelo**, e não pelo texto
    congelado da ficha: o texto é cópia por item respondido (é o que torna a
    ficha uma prova), e agrupar por ele contaria a mesma pergunta N vezes. A
    resposta órfã — item de modelo apagado, ou item acrescentado em campo — fica
    de fora e é **declarada**, em vez de sumir na conta.
    """
    fichas = Verificacao.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
        status=Verificacao.Status.CONCLUIDA,
    )
    if desde:
        fichas = fichas.filter(data__gte=desde)
    if ate:
        fichas = fichas.filter(data__lte=ate)

    itens = ItemVerificacao.objects.filter(
        tenant_id=tenant_id, verificacao__in=fichas,
    )

    por_dominio = []
    for dominio, rotulo in DominioVerificacao.choices:
        recorte = itens.filter(verificacao__modelo__dominio=dominio)
        conformes = recorte.filter(resultado=ResultadoItem.CONFORME).count()
        nao_conformes = recorte.filter(
            resultado=ResultadoItem.NAO_CONFORME,
        ).count()
        julgados = conformes + nao_conformes
        if not julgados:
            continue
        por_dominio.append({
            "dominio": dominio,
            "rotulo": rotulo,
            "conformes": conformes,
            "nao_conformes": nao_conformes,
            "conformidade": (
                Decimal(conformes) * 100 / Decimal(julgados)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        })

    #: **O ranking conta história, e por isso precisa dizer a situação de hoje.**
    #:
    #: *(Achado do dono, 16/09/2026, olhando o painel: "aqui fica parecendo que
    #: ainda tá em não conformidade, ao invés de dizer a real situação".)*
    #:
    #: A leitura é **cumulativa** de propósito — o que aponta o processo a
    #: corrigir é quantas vezes aquela pergunta reprovou ao longo das fichas,
    #: inclusive nas vezes em que o defeito já foi consertado. Um ranking que
    #: descartasse o que foi tratado zeraria sozinho toda vez que a obra
    #: funcionasse, e deixaria de apontar exatamente o processo que mais dá
    #: trabalho.
    #:
    #: O que faltava era a outra metade: **daquelas reprovas, quantas ainda
    #: estão abertas.** Sem isso a linha "Prumo da parede — 1" se lê como um
    #: problema de agora, mesmo quando ele foi tratado e encerrado na semana
    #: passada.
    #:
    #: Vem numa consulta: o `values` desce até o status da NC (LEFT JOIN, então
    #: a reprova que nunca virou NC aparece com status nulo) e a dobra acontece
    #: em memória. Contar por item com uma consulta cada repetiria o D136.
    bruto = (
        itens.filter(
            resultado=ResultadoItem.NAO_CONFORME, item_modelo__isnull=False,
        )
        .values("item_modelo_id", "item_modelo__texto",
                "verificacao__modelo__codigo", "nao_conformidades__status")
        .annotate(n=Count("item_verificacao_id", distinct=True))
    )
    ABERTAS = (
        NaoConformidade.Status.ABERTA, NaoConformidade.Status.EM_TRATAMENTO,
    )
    por_item: dict = {}
    for linha in bruto:
        chave = linha["item_modelo_id"]
        alvo = por_item.setdefault(chave, {
            "item_modelo": chave,
            "texto": linha["item_modelo__texto"],
            "modelo_codigo": linha["verificacao__modelo__codigo"],
            "reprovas": 0,
            "em_aberto": 0,
            "encerradas": 0,
            #: A reprova que **nunca virou NC**. Não é detalhe: é um defeito que
            #: ninguém está tratando, e some das duas outras contagens.
            "sem_nc": 0,
        })
        quantas = linha["n"]
        status = linha["nao_conformidades__status"]
        alvo["reprovas"] += quantas
        if status in ABERTAS:
            alvo["em_aberto"] += quantas
        elif status == NaoConformidade.Status.ENCERRADA:
            alvo["encerradas"] += quantas
        else:
            # Sem NC, ou com uma cancelada — em nenhum dos dois casos alguém
            # está tratando o defeito, e a tela precisa dizer isso.
            alvo["sem_nc"] += quantas

    total_reprovas = itens.filter(resultado=ResultadoItem.NAO_CONFORME).count()
    orfas = itens.filter(
        resultado=ResultadoItem.NAO_CONFORME, item_modelo__isnull=True,
    ).count()

    ranking = sorted(
        por_item.values(), key=lambda l: l["reprovas"], reverse=True,
    )[:20] if total_reprovas else []
    for linha in ranking:
        linha["percentual"] = (
            Decimal(linha["reprovas"]) * 100 / Decimal(total_reprovas)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    ncs = NaoConformidade.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
    por_gravidade = [
        {
            "gravidade": gravidade,
            "rotulo": rotulo,
            "abertas": ncs.filter(
                gravidade=gravidade,
                status__in=[
                    NaoConformidade.Status.ABERTA,
                    NaoConformidade.Status.EM_TRATAMENTO,
                ],
            ).count(),
            "encerradas": ncs.filter(
                gravidade=gravidade, status=NaoConformidade.Status.ENCERRADA,
            ).count(),
        }
        for gravidade, rotulo in GravidadeNC.choices
    ]

    return {
        "obra": obra_id,
        "fichas_concluidas": fichas.count(),
        "por_dominio": por_dominio,
        "itens_que_mais_reprovam": ranking,
        "reprovas_sem_modelo": orfas,
        "ncs_por_gravidade": por_gravidade,
        # A leitura do laço fechado: de tudo que já foi aberto nesta obra,
        # quanto chegou até a verificação de eficácia. É o número que diz se o
        # sistema de qualidade está funcionando ou só registrando.
        "ncs_encerradas": ncs.filter(
            status=NaoConformidade.Status.ENCERRADA,
        ).count(),
        "ncs_abertas": ncs.filter(
            status__in=[
                NaoConformidade.Status.ABERTA,
                NaoConformidade.Status.EM_TRATAMENTO,
            ],
        ).count(),
    }


# ===========================================================================
# PDCA.8 — SSMA: o diálogo de segurança e a ocorrência
# ===========================================================================


# --- Tetos -----------------------------------------------------------------

def validar_teto_de_participantes(dds: "DialogoSeguranca", *,
                                  acrescentando: int = 1) -> None:
    """A roda tem tamanho físico (§5.5m do `planos.py`)."""
    atual = dds.participantes.count()
    if atual + acrescentando > PDCA_TETO_PARTICIPANTES_POR_DDS:
        raise ValidationError(
            f"Um diálogo de segurança comporta até "
            f"{PDCA_TETO_PARTICIPANTES_POR_DDS} participantes, e este já tem "
            f"{atual}. Acima disso a roda deixa de ser uma roda: ninguém ouve, "
            f"ninguém pergunta, e a lista vira assinatura colhida por fora do "
            f"diálogo. Registre uma roda por frente."
        )


def validar_teto_de_anexos(ocorrencia: "Ocorrencia", *,
                           acrescentando: int = 1) -> None:
    """Quantos arquivos pendem de uma ocorrência (§5.5m do `planos.py`)."""
    atual = ocorrencia.anexos.count()
    if atual + acrescentando > PDCA_TETO_ANEXOS_POR_OCORRENCIA:
        raise ValidationError(
            f"Uma ocorrência comporta até {PDCA_TETO_ANEXOS_POR_OCORRENCIA} "
            f"anexos, e esta já tem {atual}. Ocorrência com dezenas de arquivos "
            f"não é ocorrência documentada: é o acervo da obra despejado no "
            f"registro que a perícia precisa conseguir ler."
        )


# --- O diálogo de segurança ------------------------------------------------

@transaction.atomic
def abrir_dds(*, obra, data: date, tema: str, tenant_id,
              local=None, atividade=None, assunto: str = "",
              duracao_min: int | None = None, responsavel=None,
              responsavel_nome: str = "", por: str = "") -> "DialogoSeguranca":
    """Abre a roda. Nasce em rascunho — a lista de presença se colhe depois."""
    if not (tema or "").strip():
        raise ValidationError(
            "O diálogo precisa de um tema. 'DDS realizado' não é tema: o que "
            "faz o registro servir de prova é dizer sobre o que se falou."
        )
    return DialogoSeguranca.objects.create(
        tenant_id=tenant_id, obra=obra, local=local, atividade=atividade,
        data=data, tema=tema.strip(), assunto=assunto or "",
        duracao_min=duracao_min, responsavel=responsavel,
        responsavel_nome=responsavel_nome or "", registrado_por=por or "",
    )


@transaction.atomic
def registrar_presenca(*, dds: "DialogoSeguranca",
                       participantes: list[dict]) -> dict:
    """Grava a lista de presença — **em lote, e só enquanto a roda está aberta**.

    O lote é pela mesma razão do `responder_itens`: a tela acumula os nomes e
    grava de uma vez, e a que falhasse no meio deixaria metade da lista sem
    ninguém saber onde parou.

    **Encerrado não recebe nome novo**, e é a trava que faz a lista ser prova.
    Sem ela, alguém acrescentaria um participante três dias depois do acidente.
    """
    if not dds.esta_aberto:
        raise ValidationError(
            "Este diálogo já foi encerrado, e a lista de presença fechou com "
            "ele. Acrescentar um nome depois do encerramento é exatamente o que "
            "faz a lista deixar de provar quem estava lá."
        )

    novos = []
    for linha in participantes:
        funcionario_id = linha.get("funcionario") or None
        nome = (linha.get("nome") or "").strip()
        if not funcionario_id and not nome:
            raise ValidationError(
                "Participante sem funcionário e sem nome é linha em branco na "
                "lista de presença — e lista com linha em branco não prova nada."
            )
        novos.append(ParticipanteDDS(
            tenant_id=dds.tenant_id, dds=dds,
            funcionario_id=funcionario_id, nome=nome,
            presente=bool(linha.get("presente", True)),
            assinou=bool(linha.get("assinou", False)),
        ))

    validar_teto_de_participantes(dds, acrescentando=len(novos))
    ParticipanteDDS.objects.bulk_create(novos)
    return {"registrados": len(novos), "total": dds.participantes.count()}


@transaction.atomic
def encerrar_dds(*, dds: "DialogoSeguranca", por: str = "",
                 publicar_no_diario: bool = True) -> dict:
    """Fecha a roda — **e recusa fechar sem ninguém dentro**.

    Um DDS sem participante é um campo de texto afirmando que houve diálogo. O
    que a fiscalização olha é a lista, e é ela que a trava protege.

    **E é aqui que o PDCA escreve no Diário pela primeira vez** (planta §7 — "não
    substitui o Diário: escreve e lê nele"). O diálogo faz parte do que aconteceu
    na obra naquele dia, e o diário é o registro contratual do dia. A escrita é
    **no encerramento** e não na abertura: rascunho no diário seria registro
    contratual de algo que ainda pode mudar.

    O import é tardio pela razão de sempre nesta casa — o PDCA tem de carregar
    numa instalação que não tenha o diário migrado.
    """
    if not dds.esta_aberto:
        raise ValidationError("Este diálogo já está encerrado.")

    presentes = dds.participantes.filter(presente=True).count()
    if not presentes:
        raise ValidationError(
            "Não dá para encerrar um diálogo sem nenhum presente. A lista de "
            "presença é a única parte do DDS que prova alguma coisa — sem ela o "
            "registro afirma que houve conversa e não mostra com quem."
        )

    dds.status = DialogoSeguranca.Status.ENCERRADO
    dds.encerrado_em = timezone.now()
    dds.encerrado_por = por or ""
    campos = ["status", "encerrado_em", "encerrado_por"]

    if publicar_no_diario:
        diario = _publicar_dds_no_diario(dds, presentes=presentes, por=por)
        if diario is not None:
            dds.diario = diario
            campos.append("diario")

    dds.save(update_fields=campos)
    return {
        "dds": dds.pk,
        "presentes": presentes,
        "diario": dds.diario_id,
        # Honestidade: a tela precisa saber se a escrita no diário aconteceu ou
        # se o módulo não estava lá. Nunca `True` otimista.
        "publicado_no_diario": dds.diario_id is not None,
    }


def _publicar_dds_no_diario(dds: "DialogoSeguranca", *, presentes: int,
                            por: str = ""):
    """Escreve o diálogo no diário do dia. Devolve o `DiarioObra` ou `None`."""
    try:
        from modulodiario.services import registrar_contribuicao
    except ImportError:
        return None

    linhas = [f"DDS — {dds.tema}"]
    if dds.assunto:
        linhas.append(dds.assunto)
    responsavel = dds.responsavel_nome or (
        getattr(dds.responsavel, "nome_completo", "") if dds.responsavel_id else ""
    )
    if responsavel:
        linhas.append(f"Conduzido por: {responsavel}")
    linhas.append(f"Participantes presentes: {presentes}")

    # **`origem` fica no default `web`**, e é limite declarado, não descuido:
    # `modulodiario.ORIGEM_CHOICES` só conhece `web` e `whatsapp`, e acrescentar
    # `pdca` ali é migration no modelo de outro módulo — mexer nele de dentro
    # desta fatia seria atravessar a fronteira da §7 pelo lado errado. A entrada
    # se identifica pelo texto ("DDS — ...") e pelo `DialogoSeguranca.diario`,
    # que aponta de volta.
    #
    # `criado_por` também não vai: no diário ele é FK para `Usuario`, e o `por`
    # desta casa é o nome de quem agiu, em texto. Passar a string levantaria
    # `ValueError` — quem assina o diálogo é o `funcionario`, que vai.
    return registrar_contribuicao(
        obra=dds.obra, funcionario=dds.responsavel, texto="\n".join(linhas),
        data=dds.data, tenant_id=dds.tenant_id,
    )


# --- A ocorrência ----------------------------------------------------------

@transaction.atomic
def registrar_ocorrencia(*, obra, ocorrido_em, tipo: str, descricao: str,
                         tenant_id, local=None, atividade=None,
                         por: str = "", **extra) -> "Ocorrencia":
    """Registra o fato — **e é de propósito a função mais permissiva do módulo**.

    Não há teto de ocorrências abertas por obra, não há campo obrigatório além
    do tipo, da hora e do que aconteceu, e a classificação nasce pendente. Cada
    uma dessas ausências é uma decisão, e todas apontam para o mesmo lugar: o
    quase-acidente é o registro mais valioso da segurança e o mais fácil de não
    fazer, porque ninguém se machucou e o turno continua. Todo atrito que se
    põe aqui é subnotificação depois.

    **Data no futuro é recusada**, e essa é a única trava. Acidente que ainda
    não aconteceu não é registro, é erro de digitação — e ele contaminaria a
    série do indicador sem ninguém perceber.
    """
    if not (descricao or "").strip():
        raise ValidationError(
            "Diga o que aconteceu. Uma ocorrência sem descrição não vira "
            "investigação nenhuma, e é ela que a perícia lê primeiro."
        )
    if ocorrido_em and ocorrido_em > timezone.now():
        raise ValidationError(
            "A data da ocorrência está no futuro. Confira o dia e a hora: o "
            "registro adiantado entra na série do indicador e ninguém o vê lá."
        )

    campos = {
        k: v for k, v in extra.items()
        if k in {
            "agente_causador", "situacao_geradora", "houve_registro_policial",
            "horas_trabalhadas_antes", "ultimo_dia_trabalhado", "acidentado",
            "acidentado_nome", "parte_do_corpo", "lateralidade",
            "natureza_lesao", "cid10", "houve_internacao", "atestado_dias",
        }
    }
    return Ocorrencia.objects.create(
        tenant_id=tenant_id, obra=obra, local=local, atividade=atividade,
        ocorrido_em=ocorrido_em, tipo=tipo, descricao=descricao.strip(),
        registrada_por=por or "", **campos,
    )


@transaction.atomic
def classificar_ocorrencia(*, ocorrencia: "Ocorrencia", classificacao: str,
                           dias_perdidos: int | None = None,
                           dias_debitados: int | None = None,
                           por: str = "") -> "Ocorrencia":
    """O verbo separado — **quem é medido não classifica a própria medida**.

    Esta é a segregação da fatia, e ela é nova nesta casa. As anteriores
    separavam quem faz de quem aprova (`apurar` × `atestar`, `tratar` ×
    `verificar_eficacia`); esta separa quem é **medido** de quem classifica. O
    tipo, o afastamento e os dias são os três campos de que a taxa de frequência
    e a de gravidade nascem, e a frente onde o acidente aconteceu é cobrada por
    elas.
    """
    if not ocorrencia.esta_aberta:
        raise ValidationError(
            "Esta ocorrência está encerrada. Reclassificar um fato encerrado "
            "muda o indicador de um período que já foi lido e discutido — "
            "reabra-a, se for o caso, para a mudança ficar visível."
        )
    if ocorrencia.tipo in (
        TipoOcorrencia.QUASE_ACIDENTE, TipoOcorrencia.INCIDENTE,
    ) and classificacao in (
        ClassificacaoOcorrencia.COM_AFASTAMENTO, ClassificacaoOcorrencia.OBITO,
    ):
        raise ValidationError(
            "Quase-acidente e incidente não têm vítima, e por isso não têm "
            "afastamento nem óbito. Se houve alguém ferido, o tipo é que está "
            "errado — corrija-o antes, porque é dele que a CAT depende."
        )
    if classificacao == ClassificacaoOcorrencia.COM_AFASTAMENTO and not dias_perdidos:
        raise ValidationError(
            "Afastamento sem dias perdidos é classificação pela metade: é "
            "exatamente desse número que a taxa de gravidade nasce."
        )
    if classificacao == ClassificacaoOcorrencia.OBITO and not dias_debitados:
        raise ValidationError(
            "O óbito entra na taxa de gravidade por dias **debitados**, não por "
            "dias perdidos — a NBR 14280 fixa 6.000. Informe o débito."
        )

    ocorrencia.classificacao = classificacao
    ocorrencia.dias_perdidos = dias_perdidos
    ocorrencia.dias_debitados = dias_debitados
    ocorrencia.classificada_em = timezone.now()
    ocorrencia.classificada_por = por or ""
    ocorrencia.save(update_fields=[
        "classificacao", "dias_perdidos", "dias_debitados",
        "classificada_em", "classificada_por",
    ])
    return ocorrencia


def prazo_da_cat(ocorrencia: "Ocorrencia") -> dict:
    """Quando a CAT vence — **e a resposta diz o que ela não sabe**.

    Lei 8.213/91 art. 22: até o **1º dia útil seguinte** ao acidente; em caso de
    morte, **de imediato**. O dia útil sai do mesmo `AjusteDeVencimento` que o
    carnê usa desde 16/09/2026, e ele herda a ressalva do **D179**: a tabela de
    feriados é global e nasce vazia. Sem ela o cálculo desvia de sábado e
    domingo e **não** de feriado — e a resposta declara isso em
    `feriados_carregados`, em vez de afirmar um prazo que pode estar um dia à
    frente do real.

    Feriado **nacional** apenas, de propósito: a CAT se comunica ao INSS, que é
    federal. O feriado municipal da praça do imóvel é do carnê, não daqui.
    """
    if not ocorrencia.exige_cat:
        return {
            "exige": False,
            "motivo": (
                "Quase-acidente e incidente não têm vítima e não geram CAT."
            ),
        }

    from modulocalendar.dias_uteis import AjusteDeVencimento, base_sincronizada

    dia_do_fato = timezone.localtime(ocorrencia.ocorrido_em).date()
    imediata = ocorrencia.classificacao == ClassificacaoOcorrencia.OBITO
    ajuste = AjusteDeVencimento()
    vence_em = dia_do_fato if imediata else ajuste(dia_do_fato + timedelta(days=1))

    hoje = timezone.localdate()
    return {
        "exige": True,
        "imediata": imediata,
        "vence_em": vence_em,
        "emitida": ocorrencia.cat_emitida_em is not None,
        "vencido": (
            ocorrencia.cat_emitida_em is None and hoje > vence_em
        ),
        "feriados_carregados": base_sincronizada(),
        "base_legal": "Lei 8.213/91, art. 22",
    }


@transaction.atomic
def registrar_cat(*, ocorrencia: "Ocorrencia", tipo: str, emitida_em: date,
                  protocolo: str = "", por: str = "") -> dict:
    """Guarda que a CAT foi comunicada — **o registro do ato, não o ato**.

    O sistema **não transmite** o evento eSocial S-2210: isso é obrigação da
    folha, e uma segunda porta para um ato com prazo legal e multa criaria duas
    verdades sobre se a CAT foi comunicada. O que mora aqui é o protocolo, que é
    o que prova a comunicação, e o aviso do prazo.
    """
    if not ocorrencia.exige_cat:
        raise ValidationError(
            "Este tipo de ocorrência não gera CAT — quase-acidente e incidente "
            "não têm vítima. Se houve alguém ferido, corrija o tipo primeiro."
        )
    if emitida_em and emitida_em > timezone.localdate():
        raise ValidationError("A data de emissão da CAT está no futuro.")

    ocorrencia.cat_tipo = tipo
    ocorrencia.cat_emitida_em = emitida_em
    ocorrencia.cat_protocolo = (protocolo or "").strip()
    ocorrencia.cat_registrada_por = por or ""
    ocorrencia.save(update_fields=[
        "cat_tipo", "cat_emitida_em", "cat_protocolo", "cat_registrada_por",
    ])
    prazo = prazo_da_cat(ocorrencia)
    return {
        "ocorrencia": ocorrencia.pk,
        "cat": {
            "tipo": ocorrencia.cat_tipo,
            "emitida_em": ocorrencia.cat_emitida_em,
            "protocolo": ocorrencia.cat_protocolo,
        },
        # **No prazo ou fora dele, e a resposta diz.** O sistema não recusa a
        # CAT atrasada — recusá-la apagaria o registro de que ela foi feita, que
        # é pior que registrá-la tarde. Ele conta a verdade.
        "dentro_do_prazo": bool(
            emitida_em and prazo.get("vence_em") and emitida_em <= prazo["vence_em"]
        ),
        "prazo": prazo,
    }


@transaction.atomic
def gerar_restricao_da_ocorrencia(*, ocorrencia: "Ocorrencia",
                                  prazo: date | None = None,
                                  por: str = "") -> "Restricao":
    """Interdita a frente — **o dente da fatia**, na corrente que a NC já usa.

    Idempotente, exige atividade (restrição sem alvo não trava nada) e abre uma
    `Restricao` de tipo `AREA`: a atividade deixa de poder entrar no quadro da
    semana da PDCA.5. **Não há tipo `SEGURANCA` novo** — interditar frente por
    risco *é* "a área não está liberada", e um nono tipo partiria o ranking de
    restrição em dois vocabulários para o mesmo fato. É o argumento que a PDCA.7
    já escreveu ao recusar um tipo próprio para a qualidade.
    """
    if ocorrencia.restricao_id:
        return ocorrencia.restricao
    if not ocorrencia.atividade_id:
        raise ValidationError(
            "Esta ocorrência não aponta para nenhuma atividade, e restrição sem "
            "alvo não trava nada. Diga qual serviço fica interditado."
        )
    if not ocorrencia.esta_aberta:
        raise ValidationError(
            "Ocorrência encerrada não interdita frente: se o risco voltou, o "
            "registro é de um fato novo."
        )

    validar_teto_de_restricoes(ocorrencia.obra_id, tenant_id=ocorrencia.tenant_id)
    restricao = Restricao.objects.create(
        tenant_id=ocorrencia.tenant_id,
        atividade_id=ocorrencia.atividade_id,
        local_id=ocorrencia.local_id,
        tipo=TipoRestricao.AREA,
        descricao=(
            f"Ocorrência #{ocorrencia.pk} ({ocorrencia.get_tipo_display()}) — "
            f"{ocorrencia.descricao.strip()[:400]}"
        ),
        prazo=prazo,
        criada_por=por or "",
    )
    ocorrencia.restricao = restricao
    ocorrencia.save(update_fields=["restricao"])
    return restricao


@transaction.atomic
def abrir_nc_da_ocorrencia(*, ocorrencia: "Ocorrencia",
                           por: str = "") -> "NaoConformidade":
    """Põe a ocorrência na máquina de tratamento — **o laço, sem duplicá-la**.

    Investigar acidente com causa e 5W2H é exatamente o que `NaoConformidade` +
    `PlanoAcao` + `VerificacaoEficacia` já fazem desde a PDCA.7. Refazer a
    máquina aqui produziria uma segunda que divergiria da primeira na primeira
    mudança de requisito. A ocorrência é o **fato**; a NC é o **tratamento**.

    Idempotente, e a gravidade não é perguntada: ela sai do tipo. Acidente é
    `CRITICA` por definição — quem se machucou já disse o quanto pesa.
    """
    if ocorrencia.nao_conformidade_id:
        return ocorrencia.nao_conformidade

    validar_teto_de_ncs(ocorrencia.obra_id, tenant_id=ocorrencia.tenant_id)
    grave = ocorrencia.tipo in (
        TipoOcorrencia.ACIDENTE_TIPICO, TipoOcorrencia.ACIDENTE_TRAJETO,
        TipoOcorrencia.DOENCA_OCUPACIONAL,
    )
    nc = NaoConformidade.objects.create(
        tenant_id=ocorrencia.tenant_id, obra=ocorrencia.obra,
        local=ocorrencia.local, atividade=ocorrencia.atividade,
        gravidade=GravidadeNC.CRITICA if grave else GravidadeNC.MAIOR,
        descricao=(
            f"Ocorrência #{ocorrencia.pk} ({ocorrencia.get_tipo_display()}) — "
            f"{ocorrencia.descricao}"
        ),
        aberta_por=por or "",
    )
    ocorrencia.nao_conformidade = nc
    ocorrencia.status = Ocorrencia.Status.EM_INVESTIGACAO
    ocorrencia.save(update_fields=["nao_conformidade", "status"])
    return nc


@transaction.atomic
def encerrar_ocorrencia(*, ocorrencia: "Ocorrencia", por: str = "",
                        nota: str = "") -> "Ocorrencia":
    """Fecha o fato — **e recusa fechar por cima de uma frente interditada**.

    Esta trava existe por um defeito medido no irmão: `encerrar_nc` **não**
    remove a `Restricao` que a NC abriu, e ninguém o faz em cascata. Copiar esse
    comportamento aqui produziria restrição de segurança fantasma — a frente
    seguiria travada depois de a ocorrência ter sido dada por resolvida, e o
    teto de restrições abertas passaria a estourar por entulho.

    A saída **não** é remover a restrição automaticamente: declarar que o risco
    cessou libera o serviço, e esse é ato de quem responde pela obra
    (`pdca.restricao.remover`), não efeito colateral de um encerramento. Então o
    encerramento recusa e diz o que falta.

    A classificação pendente também barra: ocorrência encerrada sem classificar
    sai da fila de decisão e **não entra em indicador nenhum** — some das duas
    leituras ao mesmo tempo, que é a pior forma de um registro desaparecer.
    """
    if not ocorrencia.esta_aberta:
        raise ValidationError("Esta ocorrência já está encerrada.")

    if ocorrencia.classificacao == ClassificacaoOcorrencia.PENDENTE:
        raise ValidationError(
            "Classifique a ocorrência antes de encerrá-la. Sem classificação "
            "ela sai da fila de decisão e não entra em indicador nenhum — some "
            "das duas leituras de uma vez."
        )

    restricao = ocorrencia.restricao
    if restricao is not None and restricao.status == Restricao.Status.ABERTA:
        raise ValidationError(
            f"A frente continua interditada pela restrição #{restricao.pk}, "
            f"aberta por esta ocorrência. Encerrar aqui deixaria o serviço "
            f"travado sem nada explicando por quê. Declare que o risco cessou "
            f"removendo a restrição — é ato de quem responde pela obra."
        )

    ocorrencia.status = Ocorrencia.Status.ENCERRADA
    ocorrencia.encerrada_em = timezone.now()
    ocorrencia.encerrada_por = por or ""
    ocorrencia.nota_encerramento = nota or ""
    ocorrencia.save(update_fields=[
        "status", "encerrada_em", "encerrada_por", "nota_encerramento",
    ])
    return ocorrencia


def ocorrencias_abertas_por_atividade(atividade_ids: list[int], *,
                                      tenant_id) -> dict[int, int]:
    """Quantas ocorrências abertas cada atividade tem — **numa consulta só**.

    Irmã do `ncs_abertas_por_atividade`, e existe pelo mesmo motivo escrito lá:
    o quadro da semana pergunta isso de 300 cartões de uma vez, e uma property
    no modelo faria 300 consultas.
    """
    if not atividade_ids:
        return {}
    linhas = (
        Ocorrencia.objects.filter(
            tenant_id=tenant_id, atividade_id__in=atividade_ids,
            status__in=[
                Ocorrencia.Status.ABERTA, Ocorrencia.Status.EM_INVESTIGACAO,
            ],
        )
        .values("atividade_id")
        .annotate(n=Count("ocorrencia_id"))
    )
    return {linha["atividade_id"]: linha["n"] for linha in linhas}


# --- As duas leituras ------------------------------------------------------

#: **A frase da ausência, uma vez só.** O painel da SSMA e o pulso da obra
#: respondem a mesma pergunta — *por que a taxa está vazia?* — e dois textos
#: para ela viram duas explicações que um dia divergem: a pessoa passa a achar
#: que a taxa nula do cockpit é coisa diferente da taxa nula do painel.
#:
#: Ela perdeu o "é a PDCA.9" que tinha. Número de fatia é vocabulário de quem
#: escreveu o sistema, não de quem opera (convenções §9); a NBR fica, porque
#: essa o técnico de segurança conhece e usa.
TAXAS_DE_SSMA_INDISPONIVEIS_PORQUE = (
    "A taxa de frequência e a de gravidade dividem por homem-hora de exposição "
    "ao risco (NBR 14280), e o sistema ainda não apropria homem-hora. Mostrar "
    "zero no lugar diria que a obra é segura quando o que houve foi ninguém "
    "medir."
)


def fila_da_ssma(*, obra_id, tenant_id) -> dict:
    """A fila de decisão da segurança — **quatro paradas, e nenhuma é estatística**.

    No molde da `fila_da_qualidade`: o que o cockpit mostra é o que pede ação
    hoje, não o que resume o mês.
    """
    abertas = Ocorrencia.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
        status__in=[Ocorrencia.Status.ABERTA, Ocorrencia.Status.EM_INVESTIGACAO],
    ).select_related("local", "atividade")[:PDCA_TETO_OCORRENCIAS_NA_FILA]

    cat_vencendo, sem_classificacao, sem_tratamento, interditadas = [], [], [], []
    for ocorrencia in abertas:
        linha = {
            "ocorrencia": ocorrencia.pk,
            "tipo": ocorrencia.tipo,
            "ocorrido_em": ocorrencia.ocorrido_em,
            "descricao": ocorrencia.descricao[:160],
            "local": ocorrencia.local_id,
            "atividade": ocorrencia.atividade_id,
        }
        prazo = prazo_da_cat(ocorrencia)
        if prazo["exige"] and not prazo["emitida"]:
            cat_vencendo.append({**linha, "prazo": prazo})
        if ocorrencia.classificacao == ClassificacaoOcorrencia.PENDENTE:
            sem_classificacao.append(linha)
        if not ocorrencia.nao_conformidade_id:
            sem_tratamento.append(linha)
        if ocorrencia.restricao_id:
            interditadas.append(linha)

    return {
        # A CAT primeiro porque é a única com prazo em lei e multa.
        "cat_por_comunicar": cat_vencendo,
        "sem_classificacao": sem_classificacao,
        "sem_tratamento": sem_tratamento,
        "frentes_interditadas": interditadas,
        "truncada": len(abertas) >= PDCA_TETO_OCORRENCIAS_NA_FILA,
    }


def indicadores_de_ssma(*, obra_id, tenant_id, desde: date | None = None,
                        ate: date | None = None) -> dict:
    """Os números da segurança — **e os dois que o sistema ainda não sabe**.

    **Taxa de frequência e taxa de gravidade voltam `None`, com motivo.** As
    duas dividem por homem-hora de exposição ao risco (HHT), e HHT não existe no
    sistema: `Efetivo` e `ApropriacaoHH` são da PDCA.9, e `Obra.equipe` é um M2M
    sem datas — a foto do efetivo de hoje, com o qual reconstruir o efetivo de
    julho seria fabricar.

    É a régua que o módulo já aplica duas vezes (`conformidade = None` enquanto
    nada foi respondido, `ppc = None` para semana aberta), e aqui ela é mais
    dura: numa tela de segurança, **"taxa de frequência 0,00" é a mentira mais
    cara que o sistema pode contar** — ela diz que a obra é segura quando o que
    houve foi ninguém medir. Quando a PDCA.9 entrar, as duas acendem sem
    migration, lendo `Efetivo × CalendarioTrabalho.horas_por_dia`.

    O que a fatia entrega inteiro é o **numerador** e a **pirâmide**, que é o
    que aponta ação: a razão entre quase-acidente e acidente diz se a obra está
    registrando o que avisa antes ou só o que sangra.
    """
    ocorrencias = Ocorrencia.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
    dds = DialogoSeguranca.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
    if desde:
        ocorrencias = ocorrencias.filter(ocorrido_em__date__gte=desde)
        dds = dds.filter(data__gte=desde)
    if ate:
        ocorrencias = ocorrencias.filter(ocorrido_em__date__lte=ate)
        dds = dds.filter(data__lte=ate)

    ocorrencias = ocorrencias.exclude(status=Ocorrencia.Status.CANCELADA)
    por_tipo = {
        linha["tipo"]: linha["n"]
        for linha in ocorrencias.values("tipo").annotate(n=Count("ocorrencia_id"))
    }
    com_afastamento = ocorrencias.filter(
        classificacao=ClassificacaoOcorrencia.COM_AFASTAMENTO,
    ).count()
    obitos = ocorrencias.filter(
        classificacao=ClassificacaoOcorrencia.OBITO,
    ).count()
    agregado = ocorrencias.aggregate(
        perdidos=Sum("dias_perdidos"), debitados=Sum("dias_debitados"),
    )

    acidentes = sum(
        por_tipo.get(t, 0) for t in (
            TipoOcorrencia.ACIDENTE_TIPICO, TipoOcorrencia.ACIDENTE_TRAJETO,
            TipoOcorrencia.DOENCA_OCUPACIONAL,
        )
    )
    quase = por_tipo.get(TipoOcorrencia.QUASE_ACIDENTE, 0)

    dds_encerrados = dds.filter(
        status=DialogoSeguranca.Status.ENCERRADO,
    ).count()

    return {
        "por_tipo": por_tipo,
        "acidentes": acidentes,
        "quase_acidentes": quase,
        "com_afastamento": com_afastamento,
        "sem_afastamento": ocorrencias.filter(
            classificacao=ClassificacaoOcorrencia.SEM_AFASTAMENTO,
        ).count(),
        "obitos": obitos,
        "nao_classificadas": ocorrencias.filter(
            classificacao=ClassificacaoOcorrencia.PENDENTE,
        ).count(),
        "dias_perdidos": agregado["perdidos"] or 0,
        "dias_debitados": agregado["debitados"] or 0,
        # **O indicador proativo**, e é o único que a fatia entrega fechado:
        # mede o que a obra faz antes, não o que ela contabiliza depois.
        "dds_encerrados": dds_encerrados,
        # A razão da pirâmide (Bird): quantos avisos para cada acidente. `None`
        # quando não houve acidente — dividir por zero aqui daria "infinitamente
        # seguro", que é o oposto do que um denominador zero significa.
        "avisos_por_acidente": (
            round(quase / acidentes, 2) if acidentes else None
        ),
        "taxa_frequencia": None,
        "taxa_gravidade": None,
        #: **Uma frase só, e por isso ela é constante.** O pulso da obra
        #: responde a mesma ausência, e dois textos para ela viram duas
        #: explicações que um dia divergem — a pessoa passa a achar que a
        #: taxa nula do cockpit é coisa diferente da taxa nula do painel.
        "taxas_indisponiveis_porque": TAXAS_DE_SSMA_INDISPONIVEIS_PORQUE,
    }


def epi_vencido_da_obra(*, obra_id, tenant_id) -> dict:
    """Quem está com EPI vencido nesta obra — **lendo o SIL, que é o dono**.

    A PDCA.8 não tem tabela de EPI *(decisão do dono, 20/09/2026)*: a entrega
    vive em `modulosil.EntregaEPI` desde 25/07/2026, completa, e duplicá-la
    criaria duas verdades sobre o mesmo capacete. O que a SSMA faz é ler.

    **Import tardio**, pela razão escrita no `gerar_demanda_scm`: uma importação
    no topo faria o PDCA deixar de carregar numa instalação que não contrate o
    SIL. E a degradação é **declarada** — `disponivel: False` com motivo, nunca
    uma lista vazia que se lê como "está tudo em dia".

    **O grão é a obra, e não a frente**, e isso também é declarado. Travar a
    entrada de alguém numa frente exigiria saber quem está em qual frente hoje,
    e `Efetivo` é da PDCA.9. Prometer o bloqueio agora seria prometer o que não
    há como apurar.
    """
    try:
        from modulosil.models import EntregaEPI
    except ImportError:
        return {
            "disponivel": False,
            "motivo": "O módulo de estoque (SIL) não está instalado.",
            "vencidos": [],
        }

    hoje = timezone.localdate()
    entregas = (
        EntregaEPI.objects.filter(tenant_id=tenant_id, obra_id=obra_id,
                                  status=EntregaEPI.Status.ENTREGUE)
        .filter(
            Q(ca_validade__lt=hoje) | Q(data_prevista_troca__lt=hoje),
        )
        .select_related("item", "colaborador")
    )
    vencidos = [
        {
            "entrega": e.pk,
            "colaborador": (
                e.colaborador.nome_completo if e.colaborador_id
                else e.colaborador_nome
            ),
            "item": getattr(e.item, "descricao", "") or str(e.item_id),
            "ca_numero": e.ca_numero,
            "ca_validade": e.ca_validade,
            "troca_prevista": e.data_prevista_troca,
        }
        for e in entregas[:PDCA_TETO_OCORRENCIAS_NA_FILA]
    ]
    return {
        "disponivel": True,
        "vencidos": vencidos,
        "total": len(vencidos),
        "grao": "obra",
        "observacao": (
            "A leitura é por obra. Dizer quem está com EPI vencido numa frente "
            "exige saber quem trabalha em cada frente, e isso o sistema ainda "
            "não registra."
        ),
    }


# ===========================================================================
# As leituras que ATRAVESSAM — carteira, fila do dia, pulso e busca única
# ===========================================================================
#
# Tudo o que veio antes responde sobre **um** agregado: um cronograma, um
# contrato, uma ficha, uma obra. Estas quatro respondem sobre o que a pessoa
# tem pela frente quando abre o sistema de manhã, e por isso cruzam
# exatamente o que as outras separam — onze faixas numa fila só, sete tabelas
# numa busca só, N obras numa carteira só.
#
# **Nenhuma delas calcula nada de novo, e isso é o ponto.** Cada número que
# sai daqui vem da função que já o produzia (`avanco_do_cronograma`,
# `serie_ppc`, `fila_da_qualidade`, `fila_da_ssma`). Uma segunda implementação
# da mesma média ponderada é o D138 se repetindo em escala de carteira: o
# cockpit diria 62%, o posto diria 64%, e ninguém saberia qual acreditar.
#
# **A permissão é por BLOCO, e a leitura NUNCA devolve 403 inteira.** Quem tem
# `pdca.nc.view` e não tem `pdca.ocorrencia.view` recebe a fila da qualidade e,
# no lugar da SSMA, uma entrada em `sem_permissao` dizendo qual permissão falta
# e a quem pedir. É a régua omitir × trancar aplicada a um agregado: recusar a
# página inteira esconderia o trabalho que a pessoa pode fazer, e omitir em
# silêncio faria a fila parecer vazia — que é a pior das três saídas, porque
# não parece falha.
#
# Quem decide se pode é o chamador, por uma função `pode(codigo) -> bool`. O
# serviço não conhece `request`, e é o que permite exercer estas leituras do
# comando de bancada e do teste sem forjar um token.


def _pode_tudo(_permissao: str) -> bool:
    """A leitura sem recorte — bancada, seed e teste que não simula a IAM."""
    return True


def _sem_permissao(bloco: str, oque: str, permissao: str) -> dict:
    return {
        "bloco": bloco,
        "o_que": oque,
        "permissao": permissao,
        "motivo": (
            f"Você não tem permissão para ver {oque}. "
            f"Quem libera é o administrador, pela permissão '{permissao}'."
        ),
    }


def _dia_de(quando) -> date | None:
    """A data de um `date` ou de um `datetime` com fuso, sem repetir o `if`."""
    if quando is None:
        return None
    if isinstance(quando, datetime):
        return timezone.localtime(quando).date()
    return quando


def _dias_desde(quando) -> int | None:
    dia = _dia_de(quando)
    return None if dia is None else (timezone.localdate() - dia).days


def _faixa(codigo: str, rotulo: str, consequencia: str, o_que_decidir: str,
           origem: str, linhas: list[dict], total: int | None = None) -> dict:
    """Uma faixa da fila do dia, já cortada pelo teto de leitura.

    O corte é **por faixa** e não do total (§5.5n do `planos.py`): um canteiro
    com 300 restrições vencidas não pode empurrar a CAT para fora da resposta.
    """
    cortadas = linhas[:PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA]
    quantas = len(linhas) if total is None else total
    return {
        "codigo": codigo,
        "rotulo": rotulo,
        #: `prazo_legal` · `seguranca` · `dinheiro` · `compromisso` ·
        #: `retrabalho`, nesta ordem. É o que impede o hub que soma o que não se
        #: soma: a tela agrupa por degrau em vez de exibir "12 pendências".
        "consequencia": consequencia,
        #: A frase que vira o botão. Fila que diz o que espera e não diz o que
        #: decidir é contagem com outro nome.
        "o_que_decidir": o_que_decidir,
        #: O assunto de origem — a tela escolhe por ele para que posto navegar.
        #: O mapa posto←origem é navegação, e navegação é da tela.
        "origem": origem,
        "linhas": cortadas,
        "total": quantas,
        "truncada": quantas > len(cortadas),
    }


def _linha(*, tipo: str, id_, titulo: str, detalhe: str = "", onde: str = "",
           desde=None, prazo: dict | None = None,
           extra: dict | None = None) -> dict:
    """A linha única da fila — **a mesma forma para os onze assuntos**.

    É o que faz onze filas virarem uma: o que é, há quanto tempo espera, e
    (quando existe) o prazo correndo contra ela.
    """
    return {
        "chave": f"{tipo}:{id_}",
        "tipo": tipo,
        "id": id_,
        "titulo": titulo,
        "detalhe": detalhe,
        "onde": onde,
        "desde": _dia_de(desde),
        "dias": _dias_desde(desde),
        "prazo": prazo,
        **(extra or {}),
    }


def _prazo(vence_em: date | None, *, imediata: bool = False,
           base_legal: str = "") -> dict | None:
    if vence_em is None:
        return None
    hoje = timezone.localdate()
    return {
        "vence_em": vence_em,
        "vencido": vence_em < hoje,
        "imediata": imediata,
        "dias_restantes": (vence_em - hoje).days,
        "base_legal": base_legal,
    }


def _escadas_de(modelo, objetos, *, tenant_id) -> dict:
    """Em que degrau cada documento parou, e **desde quando** — numa consulta.

    Quando um documento começou a esperar não é quando ele foi montado: é
    quando alguém o submeteu, e quem guarda isso é a escada do `nucleo`. Uma
    consulta por documento repetiria o N+1 que o resto desta seção existe para
    não ter — numa fila de 40 medições seriam 40 idas ao banco para escrever 40
    nomes de degrau.

    Serve as três espécies que sobem escada neste módulo (medição, liberação de
    retenção e aditivo) porque a pergunta é a mesma para as três. Escrevê-la de
    novo em cada fila seria a segunda implementação que a §10.1 do desenho
    proíbe — e a que divergiria no dia em que o motor mudasse de campo.
    """
    if not objetos:
        return {}

    from django.contrib.contenttypes.models import ContentType

    from nucleo.models import PedidoAprovacao

    ct = ContentType.objects.get_for_model(modelo)
    por_alvo: dict[int, dict] = {}
    for pedido in (
        PedidoAprovacao.objects.filter(
            tenant_id=tenant_id, alvo_tipo=ct,
            alvo_id__in=[o.pk for o in objetos],
            estado=PedidoAprovacao.Estado.EM_APROVACAO,
        ).select_related("nivel_atual")
    ):
        por_alvo[pedido.alvo_id] = {
            "desde": pedido.solicitado_em,
            "degrau": getattr(pedido.nivel_atual, "nome", ""),
            # **A permissão do degrau, e não a do portão.** É o que permite à
            # tela dizer de quem se espera a assinatura, em vez de oferecer um
            # botão de atestar a quem o motor vai recusar.
            "permissao_do_degrau": getattr(
                pedido.nivel_atual, "permissao_exigida", "",
            ),
        }
    return por_alvo


# --- B3: o posto da medição — a carteira de contratos e a fila do dinheiro ---

def _pedido_do_contrato(contrato) -> dict | None:
    """O pedido de serviço do Suprimentos ligado ao contrato, com o valor pedido."""
    pedido = contrato.pedido_scm
    if pedido is None:
        return None
    valor = pedido.valor_total
    if valor is None:
        valor = sum(((i.quantidade or Decimal("0")) * (i.preco_unitario or Decimal("0"))
                     for i in pedido.itens.all()), Decimal("0"))
    return {"pedido": pedido.pk, "status": pedido.status, "status_rotulo": pedido.get_status_display(),
            "valor_pedido": str(Decimal(valor).quantize(Decimal("0.01")))}


def carteira_de_contratos(*, obra_id, tenant_id, pode=_pode_tudo) -> dict:
    """**Os contratos da obra com o saldo resolvido** — a leitura de cima do
    posto da medição.

    Uma linha por contrato, com contratado, medido nas três faixas, saldo,
    retenção e o período que a próxima medição cobriria. Existe como leitura
    única porque a alternativa é a tela pedir `contratos/` e depois `saldo/`
    **uma vez por contrato**: numa obra com doze empreiteiros são treze idas ao
    servidor para desenhar doze linhas, e as doze respostas chegam em momentos
    diferentes — o total da tela nunca é o total de um instante.

    **Não soma nada de novo.** Cada linha é `saldo_do_contrato`, que já é a
    resposta de `GET contratos/{id}/saldo/`; esta função só a repete pelos
    contratos da obra e corta no teto. Uma segunda implementação do saldo seria
    o D138 em escala de carteira — a tela do contrato diria um número e a do
    posto diria outro.

    **Os encerrados e cancelados ficam de fora por padrão.** Eles não esperam
    decisão nenhuma e ocupariam as linhas de quem espera; `incluir_fechados`
    existe para a vista de histórico, que é outra pergunta.
    """
    if not pode("pdca.contrato.view"):
        return {
            "linhas": [],
            "total": 0,
            "truncada": False,
            "teto": PDCA_TETO_CONTRATOS_NO_POSTO,
            "sem_permissao": [_sem_permissao(
                "contrato", "os contratos desta obra", "pdca.contrato.view",
            )],
        }

    vivos = ContratoObra.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id,
    ).exclude(status__in=(
        ContratoObra.Status.ENCERRADO, ContratoObra.Status.CANCELADO,
    ))
    total = vivos.count()
    contratos = list(
        vivos.select_related("fornecedor", "cliente", "pedido_scm")
        .prefetch_related("itens", "medicoes", "medicoes__itens", "aditivos", "pedido_scm__itens")
        .order_by("numero")[:PDCA_TETO_CONTRATOS_NO_POSTO]
    )

    linhas = []
    for contrato in contratos:
        saldo = saldo_do_contrato(contrato)
        aberta, motivo = planilha_editavel(contrato)
        linhas.append({
            "contrato": contrato.pk,
            "numero": contrato.numero,
            "objeto": contrato.objeto[:200],
            "fornecedor": contrato.fornecedor_id,
            "fornecedor_nome": contrato.parte_nome,
            "lado": contrato.lado,
            "regime": contrato.regime,
            "regime_rotulo": contrato.get_regime_display(),
            "status": contrato.status,
            "status_rotulo": contrato.get_status_display(),
            "data_inicio": contrato.data_inicio,
            "data_fim": contrato.data_fim,
            "regime_publico": contrato.regime_publico,
            # A trava da planilha viaja aqui pelo mesmo motivo que viaja no
            # serializer do contrato (convenções §11): a tela lê a resposta em
            # vez de reimplementar a condição, e a frase que ela mostra é a
            # mesma que a API devolveria ao recusar.
            "planilha_editavel": aberta,
            "planilha_fechada_porque": motivo,
            "saldo": saldo,
            # Medição × compra de serviço: o pedido do Suprimentos que este
            # contrato mede (o medido já está no saldo, ao lado).
            "pedido_scm": _pedido_do_contrato(contrato),
        })

    return {
        "linhas": linhas,
        "total": total,
        "truncada": total > len(linhas),
        "teto": PDCA_TETO_CONTRATOS_NO_POSTO,
        "sem_permissao": [],
    }


def fila_da_medicao(*, obra_id, tenant_id, pode=_pode_tudo) -> dict:
    """**O que espera alguém no caminho do dinheiro desta obra** (B3).

    Quatro filas, e a ordem é a do caminho que o dinheiro percorre: o boletim
    que alguém apurou e não mandou, o que subiu a escada e espera assinatura, a
    caução pedida de volta e o aditivo que ainda não foi decidido. **Todas as
    quatro são documentos que existem e estão parados** — nenhuma é contagem, e
    nenhuma inventa uma cobrança.

    **Por que o contrato "sem medir no mês" não é uma delas.** Seria a fila
    óbvia, e seria ruído: o sistema não conhece a periodicidade combinada com
    cada empreiteiro — não existe esse campo no contrato, e ela é cláusula
    comercial, não decisão de engenharia. Sem ela, qualquer corte ("30 dias sem
    medir") seria um número inventado aqui, e a faixa apareceria todo dia para
    todo contrato vigente — que é a definição de aviso que ensina a ignorar a
    faixa. O período em aberto de cada contrato **já viaja** no
    `periodo_sugerido` do `saldo_do_contrato`, que é a leitura que abre a
    carteira do posto: lá ele é informação ao lado do contrato, e não alarme.

    **Nada aqui é calculado de novo** (§10.1 do desenho): o líquido sai de
    `totais_da_medicao`, o degrau de `_escadas_de`, o valor do aditivo do
    próprio documento.

    **A permissão é por bloco, e a leitura nunca recusa a página inteira.** O
    posto junta dois assuntos com permissões diferentes — a medição e o
    contrato —, e exigir as duas fecharia a porta para quem só ateste. O bloco
    que a pessoa não pode ver vem vazio, e a permissão que falta vem nomeada em
    `sem_permissao`.
    """
    negados: list[dict] = []
    teto = PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA

    rascunhos: list[dict] = []
    a_atestar: list[dict] = []
    total_rascunhos = total_a_atestar = 0

    if pode("pdca.medicao.view"):
        paradas = Medicao.objects.filter(
            tenant_id=tenant_id, contrato__obra_id=obra_id,
            status=Medicao.Status.RASCUNHO,
        )
        total_rascunhos = paradas.count()
        for m in (
            paradas.select_related("contrato", "contrato__fornecedor", "contrato__cliente")
            .order_by("periodo_fim", "numero")[:teto]
        ):
            totais = totais_da_medicao(m)
            rascunhos.append(_linha(
                tipo="medicao", id_=m.pk,
                titulo=f"Medição {m.numero} · contrato {m.contrato.numero}",
                detalhe=(
                    f"Período de {m.periodo_inicio:%d/%m/%Y} a "
                    f"{m.periodo_fim:%d/%m/%Y}"
                ),
                onde=m.contrato.parte_nome,
                desde=m.apurada_em,
                extra={
                    "contrato": m.contrato_id,
                    "numero": m.numero,
                    "liquido": totais["liquido"],
                    "bruto": totais["bruto"],
                    "apurada_por": m.apurada_por,
                    # O boletim aberto e **sem nenhuma linha** não é o mesmo
                    # problema de um pronto que ninguém submeteu: um pede para
                    # ser preenchido, o outro para ser conferido. A tela
                    # precisa distinguir para escolher o verbo que oferece.
                    "linhas": m.itens.count(),
                },
            ))

        em_atesto = Medicao.objects.filter(
            tenant_id=tenant_id, contrato__obra_id=obra_id,
            status=Medicao.Status.EM_APROVACAO,
        )
        total_a_atestar = em_atesto.count()
        esperando = list(
            em_atesto.select_related("contrato", "contrato__fornecedor", "contrato__cliente")
            .order_by("periodo_fim", "numero")[:teto]
        )
        escadas = _escadas_de(Medicao, esperando, tenant_id=tenant_id)
        for m in esperando:
            escada = escadas.get(m.pk, {})
            totais = totais_da_medicao(m)
            a_atestar.append(_linha(
                tipo="medicao", id_=m.pk,
                titulo=f"Medição {m.numero} · contrato {m.contrato.numero}",
                detalhe=(
                    f"Período de {m.periodo_inicio:%d/%m/%Y} a "
                    f"{m.periodo_fim:%d/%m/%Y}"
                ),
                onde=m.contrato.parte_nome,
                desde=escada.get("desde") or m.apurada_em,
                extra={
                    "contrato": m.contrato_id,
                    "numero": m.numero,
                    "liquido": totais["liquido"],
                    "bruto": totais["bruto"],
                    "degrau": escada.get("degrau", ""),
                    "permissao_do_degrau": escada.get("permissao_do_degrau", ""),
                },
            ))
    else:
        negados.append(_sem_permissao(
            "medicao", "as medições desta obra", "pdca.medicao.view",
        ))

    retencoes: list[dict] = []
    aditivos: list[dict] = []
    total_retencoes = total_aditivos = 0

    # Aditivo e liberação de retenção são documentos do **contrato** — quem os
    # lê é quem lê o contrato, e é por isso que os dois blocos estão atrás da
    # mesma permissão, e não da de medição.
    if pode("pdca.contrato.view"):
        pedidas = LiberacaoRetencao.objects.filter(
            tenant_id=tenant_id, contrato__obra_id=obra_id,
            status=LiberacaoRetencao.Status.EM_APROVACAO,
        )
        total_retencoes = pedidas.count()
        lista_retencoes = list(
            pedidas.select_related("contrato", "contrato__fornecedor", "contrato__cliente")
            .order_by("data")[:teto]
        )
        escadas = _escadas_de(
            LiberacaoRetencao, lista_retencoes, tenant_id=tenant_id,
        )
        for lib in lista_retencoes:
            escada = escadas.get(lib.pk, {})
            retencoes.append(_linha(
                tipo="liberacao", id_=lib.pk,
                titulo=f"Retenção do contrato {lib.contrato.numero}",
                detalhe=lib.condicao_atendida[:160],
                onde=lib.contrato.parte_nome,
                desde=escada.get("desde") or lib.criado_em,
                extra={
                    "contrato": lib.contrato_id,
                    "liquido": lib.valor,
                    "degrau": escada.get("degrau", ""),
                    "permissao_do_degrau": escada.get("permissao_do_degrau", ""),
                },
            ))

        abertos = AditivoContrato.objects.filter(
            tenant_id=tenant_id, contrato__obra_id=obra_id,
            status__in=(
                AditivoContrato.Status.RASCUNHO,
                AditivoContrato.Status.EM_APROVACAO,
            ),
        )
        total_aditivos = abertos.count()
        lista_aditivos = list(
            abertos.select_related("contrato", "contrato__fornecedor", "contrato__cliente")
            .order_by("criado_em")[:teto]
        )
        escadas = _escadas_de(
            AditivoContrato, lista_aditivos, tenant_id=tenant_id,
        )
        for ad in lista_aditivos:
            escada = escadas.get(ad.pk, {})
            aditivos.append(_linha(
                tipo="aditivo", id_=ad.pk,
                titulo=f"Aditivo {ad.numero} · contrato {ad.contrato.numero}",
                detalhe=ad.justificativa[:160],
                onde=ad.contrato.parte_nome,
                desde=escada.get("desde") or ad.criado_em,
                extra={
                    "contrato": ad.contrato_id,
                    "numero": ad.numero,
                    "status": ad.status,
                    "degrau": escada.get("degrau", ""),
                    "permissao_do_degrau": escada.get("permissao_do_degrau", ""),
                },
            ))
    else:
        negados.append(_sem_permissao(
            "contrato", "os contratos desta obra", "pdca.contrato.view",
        ))

    return {
        "obra": obra_id,
        "medicoes_em_rascunho": rascunhos,
        "medicoes_a_atestar": a_atestar,
        "retencoes_a_liberar": retencoes,
        "aditivos_a_decidir": aditivos,
        # Os totais vêm ao lado das listas porque **elas são cortadas pelo
        # teto**: uma tela que contasse `linhas.length` diria "40" numa obra
        # com 300 medições paradas, e número errado numa fila de dinheiro é
        # pior do que número nenhum.
        "totais": {
            "medicoes_em_rascunho": total_rascunhos,
            "medicoes_a_atestar": total_a_atestar,
            "retencoes_a_liberar": total_retencoes,
            "aditivos_a_decidir": total_aditivos,
        },
        "total": (
            total_rascunhos + total_a_atestar + total_retencoes + total_aditivos
        ),
        "sem_permissao": negados,
    }


# --- B2: a fila única da obra ----------------------------------------------

def fila_do_dia(*, obra_id, tenant_id, pode=_pode_tudo) -> dict:
    """**Tudo o que espera alguém nesta obra, numa ordenação só** (B2).

    O backend já tinha o padrão certo em dois lugares — `ncs/fila` e
    `ocorrencias/fila` devolvem *o que espera alguém, agora*, e não uma
    contagem. O que faltava era o que as une: sem isto a tela de abertura faria
    cinco chamadas e ordenaria no navegador, o que dá a ordem errada (o
    navegador não sabe que CAT tem prazo em lei) e dá devagar.

    **A ordem é por consequência, e ela não é negociável:** prazo legal
    primeiro, porque a CAT tem multa e não se recupera depois; segurança em
    seguida, porque a classificação pendente pode estar escondendo uma CAT;
    dinheiro depois; compromisso assumido; e retrabalho por último. Uma NC sem
    plano e uma medição sem atesto **não viram "12 pendências"** — ficam em
    faixas nomeadas, cada uma com o verbo que a fecha.
    """
    hoje = timezone.localdate()
    fim_da_semana = segunda_da_semana(hoje) + timedelta(days=6)
    faixas: list[dict] = []
    negados: list[dict] = []

    # --- prazo legal e segurança --------------------------------------------
    ssma, sem_ssma = faixas_da_seguranca(
        obra_id=obra_id, tenant_id=tenant_id, pode=pode,
    )
    faixas.extend(ssma)
    negados.extend(sem_ssma)

    # --- dinheiro -------------------------------------------------------------
    if pode("pdca.medicao.view"):
        em_atesto = Medicao.objects.filter(
            tenant_id=tenant_id, contrato__obra_id=obra_id,
            status=Medicao.Status.EM_APROVACAO,
        )
        esperando = list(
            em_atesto.select_related("contrato")
            .order_by("periodo_fim")[:PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA]
        )
        #: Quando a medição **começou a esperar** não é quando ela foi apurada:
        #: é quando alguém a submeteu, e quem guarda isso é a escada do
        #: `nucleo`. Vem numa consulta para todas — uma por medição repetiria o
        #: N+1 que o `_apontado_por_codigo` existe para não ter.
        escadas = _escadas_de(Medicao, esperando, tenant_id=tenant_id)
        faixas.append(_faixa(
            "medicoes_a_atestar", "Medição esperando atesto", "dinheiro",
            "Atestar ou devolver a medição — o pagamento sai daqui.", "medicao",
            [
                _linha(
                    tipo="medicao", id_=m.pk,
                    titulo=f"Medição {m.numero} · contrato {m.contrato.numero}",
                    detalhe=(
                        f"Período de {m.periodo_inicio:%d/%m/%Y} a "
                        f"{m.periodo_fim:%d/%m/%Y}"
                    ),
                    desde=escadas.get(m.pk, {}).get("desde") or m.apurada_em,
                    extra={
                        "contrato": m.contrato_id,
                        "degrau": escadas.get(m.pk, {}).get("degrau", ""),
                        "liquido": totais_da_medicao(m)["liquido"],
                    },
                )
                for m in esperando
            ],
            total=em_atesto.count(),
        ))
    else:
        negados.append(_sem_permissao(
            "medicao", "as medições desta obra", "pdca.medicao.view",
        ))

    # --- compromisso assumido -------------------------------------------------
    if pode("pdca.programacao.view"):
        vencidas = ProgramacaoSemanal.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id,
            status=ProgramacaoSemanal.Status.COMPROMETIDA,
            semana_fim__lt=hoje,
        )
        faixas.append(_faixa(
            "semanas_a_encerrar", "Semana por encerrar", "compromisso",
            "Julgar item a item e registrar a causa do que não saiu.",
            "programacao",
            [
                _linha(
                    tipo="programacao", id_=p.pk,
                    titulo=f"Semana de {p.semana_inicio:%d/%m/%Y}",
                    detalhe=(
                        f"Acabou em {p.semana_fim:%d/%m/%Y} e os compromissos "
                        f"ainda não foram julgados"
                    ),
                    desde=p.semana_fim,
                )
                for p in vencidas.order_by(
                    "semana_inicio",
                )[:PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA]
            ],
            total=vencidas.count(),
        ))
    else:
        negados.append(_sem_permissao(
            "programacao", "a programação semanal desta obra",
            "pdca.programacao.view",
        ))

    if pode("pdca.restricao.view"):
        abertas = Restricao.objects.filter(
            tenant_id=tenant_id, atividade__cronograma__obra_id=obra_id,
            status=Restricao.Status.ABERTA, prazo__isnull=False,
        ).select_related("atividade", "local")

        def _linha_da_restricao(r) -> dict:
            return _linha(
                tipo="restricao", id_=r.pk,
                titulo=r.get_tipo_display(),
                detalhe=r.descricao[:160],
                onde=(r.local.nome if r.local_id else ""),
                desde=r.criada_em,
                prazo=_prazo(r.prazo),
                extra={
                    "responsavel": r.responsavel,
                    "atividade": r.atividade_id,
                    "atividade_nome": r.atividade.nome if r.atividade_id else "",
                    "demanda_scm": r.demanda_scm_id,
                },
            )

        ja_venceu = abertas.filter(prazo__lt=hoje)
        faixas.append(_faixa(
            "restricoes_vencidas", "Restrição com prazo vencido", "compromisso",
            "Remover a restrição ou repactuar o prazo com quem a resolve.",
            "restricao",
            [
                _linha_da_restricao(r) for r in
                ja_venceu.order_by("prazo")[:PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA]
            ],
            total=ja_venceu.count(),
        ))

        vencendo = abertas.filter(prazo__gte=hoje, prazo__lte=fim_da_semana)
        faixas.append(_faixa(
            "restricoes_vencendo", "Restrição vencendo nesta semana",
            "compromisso",
            "Resolver antes de virar impedimento do quadro da semana.",
            "restricao",
            [
                _linha_da_restricao(r) for r in
                vencendo.order_by("prazo")[:PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA]
            ],
            total=vencendo.count(),
        ))
    else:
        negados.append(_sem_permissao(
            "restricao", "as restrições desta obra", "pdca.restricao.view",
        ))

    # --- retrabalho -----------------------------------------------------------
    retrabalho, sem_qualidade = faixas_da_qualidade(
        obra_id=obra_id, tenant_id=tenant_id, pode=pode,
    )
    faixas.extend(retrabalho)
    negados.extend(sem_qualidade)

    return _fila_de(faixas, negados, obra_id=obra_id, hoje=hoje)


def _fila_de(faixas: list[dict], negados: list[dict], *, obra_id,
             hoje: date) -> dict:
    """A forma da fila que a tela desenha — a do dia e a de cada posto.

    É uma só para que o componente que a desenha seja um só: a fila do posto é
    a fila do dia recortada por assunto, e duas formas para a mesma linha
    divergiriam na primeira coluna nova.
    """
    com_gente_esperando = [f for f in faixas if f["total"]]
    return {
        "obra": obra_id,
        "hoje": hoje,
        #: **Só as faixas que têm alguém esperando.** Faixa vazia no cockpit é
        #: ruído que ensina a ignorar a tela (convenções §9); a tela mostra o
        #: estado vazio uma vez, no lugar da fila inteira, quando não há nada.
        "faixas": com_gente_esperando,
        #: Quantas a leitura varreu — a tela diz "nenhuma das 11 filas tem
        #: alguém esperando" em vez de abrir uma página em branco.
        "faixas_varridas": len(faixas),
        "total": sum(f["total"] for f in com_gente_esperando),
        "sem_permissao": negados,
    }


def faixas_da_seguranca(*, obra_id, tenant_id,
                        pode=_pode_tudo) -> tuple[list[dict], list[dict]]:
    """As faixas de prazo legal e de segurança — **as da fila do dia**.

    Função própria porque duas leituras as servem: a fila do dia, que as põe
    no topo de tudo, e o posto da segurança, que abre por elas. Montá-las duas
    vezes daria duas frases para a mesma CAT.
    """
    if not pode("pdca.ocorrencia.view"):
        return [], [_sem_permissao(
            "seguranca", "as ocorrências de segurança desta obra",
            "pdca.ocorrencia.view",
        )]

    ssma = fila_da_ssma(obra_id=obra_id, tenant_id=tenant_id)

    def _rotulo_do_tipo(valor: str) -> str:
        try:
            return TipoOcorrencia(valor).label
        except ValueError:
            return valor

    def _linha_da_ocorrencia(bruta: dict, prazo: dict | None = None) -> dict:
        return _linha(
            tipo="ocorrencia", id_=bruta["ocorrencia"],
            titulo=_rotulo_do_tipo(bruta["tipo"]),
            detalhe=bruta["descricao"],
            desde=bruta["ocorrido_em"],
            prazo=prazo,
            extra={"local": bruta["local"], "atividade": bruta["atividade"]},
        )

    return [
        _faixa(
            "cat_por_comunicar", "CAT por comunicar", "prazo_legal",
            "Emitir a CAT e guardar o protocolo.", "seguranca",
            [
                _linha_da_ocorrencia(bruta, _prazo(
                    bruta["prazo"].get("vence_em"),
                    imediata=bruta["prazo"].get("imediata", False),
                    base_legal=bruta["prazo"].get("base_legal", ""),
                ))
                for bruta in ssma["cat_por_comunicar"]
            ],
        ),
        _faixa(
            "ocorrencias_sem_classificacao", "Ocorrência por classificar",
            "seguranca",
            "Classificar a ocorrência — tipo, afastamento e dias perdidos.",
            "seguranca",
            [_linha_da_ocorrencia(b) for b in ssma["sem_classificacao"]],
        ),
        _faixa(
            "ocorrencias_sem_tratamento", "Ocorrência sem tratamento aberto",
            "seguranca",
            "Abrir a não-conformidade que investiga a causa.", "seguranca",
            [_linha_da_ocorrencia(b) for b in ssma["sem_tratamento"]],
        ),
    ], []


def faixas_da_qualidade(*, obra_id, tenant_id,
                        pode=_pode_tudo) -> tuple[list[dict], list[dict]]:
    """As quatro faixas do retrabalho — **as da fila do dia**, e as do posto.

    A mesma razão do `faixas_da_seguranca`: o posto da qualidade abre pela
    fila do laço aberto, e ela é exatamente o degrau de retrabalho da fila do
    dia. Duas montagens seriam dois textos para o mesmo defeito parado.
    """
    faixas: list[dict] = []
    negados: list[dict] = []
    pode_nc = pode("pdca.nc.view")
    pode_ficha = pode("pdca.verificacao.view")
    qualidade = (
        fila_da_qualidade(obra_id=obra_id, tenant_id=tenant_id)
        if (pode_nc or pode_ficha) else None
    )

    if pode_nc:
        def _linha_da_nc(bruta: dict) -> dict:
            return _linha(
                tipo="nc", id_=bruta["nc"],
                titulo=f"{bruta['gravidade_rotulo']} · {bruta['descricao']}",
                detalhe=bruta["falta"],
                onde=(bruta["local_rotulo"] or ""),
                desde=bruta["aberta_em"],
                extra={
                    "gravidade": bruta["gravidade"],
                    "atividade_nome": bruta["atividade_nome"],
                },
            )

        faixas.append(_faixa(
            "ncs_sem_plano", "Defeito sem plano de ação", "retrabalho",
            "Montar o plano de ação — quem faz o quê, até quando.",
            "qualidade",
            [_linha_da_nc(b) for b in qualidade["ncs_sem_plano"]],
        ))
        faixas.append(_faixa(
            "acoes_vencidas", "Ação com prazo vencido", "retrabalho",
            "Executar a ação ou repactuar o prazo por escrito.", "qualidade",
            [
                _linha(
                    tipo="plano_acao", id_=bruta["plano"],
                    titulo=bruta["o_que"],
                    detalhe=f"Responsável: {bruta['quem'] or 'não informado'}",
                    desde=bruta["quando"],
                    prazo=_prazo(bruta["quando"]),
                    extra={"nc": bruta["nc"]},
                )
                for bruta in qualidade["acoes_vencidas"]
            ],
        ))
        faixas.append(_faixa(
            "ncs_esperando_eficacia", "Conserto por conferir", "retrabalho",
            "Verificar em campo se o tratamento funcionou — só a eficácia "
            "encerra o defeito.",
            "qualidade",
            [_linha_da_nc(b) for b in qualidade["ncs_esperando_eficacia"]],
        ))
    else:
        negados.append(_sem_permissao(
            "qualidade", "as não-conformidades desta obra", "pdca.nc.view",
        ))

    if pode_ficha:
        faixas.append(_faixa(
            "fichas_em_andamento", "Ficha parada no meio", "retrabalho",
            "Terminar de responder a ficha e concluí-la.", "qualidade",
            [
                _linha(
                    tipo="verificacao", id_=bruta["verificacao"],
                    titulo=bruta["modelo_nome"],
                    detalhe=f"Aberta por {bruta['inspetor'] or 'não informado'}",
                    desde=bruta["data"],
                )
                for bruta in qualidade["fichas_em_andamento"]
            ],
        ))
    else:
        negados.append(_sem_permissao(
            "verificacao", "as fichas de verificação desta obra",
            "pdca.verificacao.view",
        ))

    return faixas, negados


# --- B8 e B9: os postos da qualidade e da segurança -------------------------

def posto_da_qualidade(*, obra_id, tenant_id, pode=_pode_tudo,
                       desde: date | None = None,
                       ate: date | None = None) -> dict:
    """**O laço aberto e o que mais reprova**, numa leitura (B8).

    A fila é a do degrau de retrabalho da fila do dia, recortada — e por isso
    as duas não podem discordar. O painel é o `painel_de_conformidade`, que já
    existia e continua sendo o único lugar onde a conta é feita; vem nulo, com
    a permissão nomeada, para quem não vê não-conformidade.
    """
    faixas, negados = faixas_da_qualidade(
        obra_id=obra_id, tenant_id=tenant_id, pode=pode,
    )
    painel = None
    if pode("pdca.nc.view"):
        painel = painel_de_conformidade(
            obra_id=obra_id, tenant_id=tenant_id, desde=desde, ate=ate,
        )
    return {
        "fila": _fila_de(
            faixas, negados, obra_id=obra_id, hoje=timezone.localdate(),
        ),
        "painel": painel,
        "sem_permissao": negados,
    }


def posto_da_seguranca(*, obra_id, tenant_id, pode=_pode_tudo,
                       desde: date | None = None,
                       ate: date | None = None) -> dict:
    """**A CAT no topo, e os números que o sistema sabe e os que não** (B9).

    Mesma construção do posto da qualidade: a fila é a da fila do dia, e os
    indicadores são o `indicadores_de_ssma` — com as duas taxas nulas e o
    motivo, que é o que impede a tela de desenhar "0,00" onde ninguém mediu.

    **As frentes interditadas vêm à parte**, e não como faixa: não são uma
    decisão parada nesta tela — liberar a frente é remover a restrição, ato de
    quem responde pela obra, na semana. Aqui elas são o que o técnico precisa
    saber antes de encerrar a ocorrência que as abriu.
    """
    faixas, negados = faixas_da_seguranca(
        obra_id=obra_id, tenant_id=tenant_id, pode=pode,
    )
    indicadores = None
    interditadas: list[dict] = []
    if pode("pdca.ocorrencia.view"):
        indicadores = indicadores_de_ssma(
            obra_id=obra_id, tenant_id=tenant_id, desde=desde, ate=ate,
        )
        interditadas = [
            {
                "ocorrencia": o.pk,
                "restricao": o.restricao_id,
                "tipo_rotulo": o.get_tipo_display(),
                "descricao": o.descricao[:160],
                "atividade_nome": o.atividade.nome if o.atividade_id else "",
                "local_rotulo": o.local.nome if o.local_id else "",
                "desde": _dia_de(o.restricao.criada_em),
            }
            for o in Ocorrencia.objects.filter(
                tenant_id=tenant_id, obra_id=obra_id,
                restricao__status=Restricao.Status.ABERTA,
            ).select_related("restricao", "atividade", "local")
            .order_by("restricao__criada_em")[:PDCA_TETO_OCORRENCIAS_NA_FILA]
        ]
    return {
        "fila": _fila_de(
            faixas, negados, obra_id=obra_id, hoje=timezone.localdate(),
        ),
        "indicadores": indicadores,
        "frentes_interditadas": interditadas,
        "sem_permissao": negados,
    }


# --- B6: o pulso da obra ----------------------------------------------------

def _plano_vigente(obra_id, *, tenant_id):
    return (
        Cronograma.objects
        .filter(tenant_id=tenant_id, obra_id=obra_id,
                status=Cronograma.Status.VIGENTE)
        .first()
    )


def _leitura_de_prazo(plano) -> dict:
    """Término previsto × término da linha de base, no grão da **obra**.

    A comparação atividade a atividade é do posto `PLANO`
    (`comparar_com_base`); o cockpit precisa de um número só, e é o término
    deste cronograma contra o da versão de que ele descende. Sem base — obra
    que nunca publicou duas versões — o desvio é `None`, e `None` aqui é
    resposta: não há atraso contra um combinado que nunca foi combinado.
    """
    if plano is None:
        return {
            "tem_plano": False, "cronograma": None, "versao": None,
            "termino": None, "base_versao": None, "base_termino": None,
            "desvio_dias": None,
            "sem_apuracao_porque": (
                "Esta obra ainda não tem um cronograma publicado."
            ),
        }
    base = linha_de_base(plano)
    desvio = None
    if base is not None and plano.termino_calculado and base.termino_calculado:
        desvio = (plano.termino_calculado - base.termino_calculado).days
    return {
        "tem_plano": True,
        "cronograma": plano.pk,
        "versao": plano.versao,
        "termino": plano.termino_calculado,
        "base_versao": None if base is None else base.versao,
        "base_termino": None if base is None else base.termino_calculado,
        "desvio_dias": desvio,
        "sem_apuracao_porque": (
            "" if base is not None else
            "Este é o primeiro plano publicado — ainda não há versão anterior "
            "com que comparar o prazo."
        ),
    }


def _leitura_de_avanco(plano) -> dict:
    """O avanço físico da obra — **`None` quando ninguém apontou, nunca 0%**.

    Chama o `avanco_do_cronograma`, que é a única implementação da média
    ponderada, e traduz o `folhas_apontadas == 0` na frase que a tela mostra.
    Zero diria que a obra não andou; o que houve foi ninguém apontar.
    """
    if plano is None:
        return {
            "fisico": None, "financeiro": None, "folhas": 0,
            "folhas_apontadas": 0, "folhas_sem_peso": 0,
            "ultimo_apontamento": None,
            "sem_apuracao_porque": (
                "Esta obra ainda não tem um cronograma publicado."
            ),
        }
    bruto = avanco_do_cronograma(plano)
    fisico = bruto["fisico"]
    porque = ""
    if bruto["folhas_apontadas"] == 0:
        #: **O zero vira nulo aqui, e não lá.** O `avanco_do_cronograma`
        #: devolve `0.0` para o plano em que ninguém apontou, e está certo do
        #: ponto de vista dele: a média ponderada de atividades com peso e sem
        #: apontamento é zero mesmo, e é isso que a barra de cada linha do
        #: Gantt precisa desenhar.
        #:
        #: No cockpit a mesma resposta mente. "Avanço 0%" ao lado de "PPC 68%"
        #: se lê como *a obra não andou*, quando o que houve foi ninguém
        #: apontar — e é a régua da §5.1, que exige "sem apuração" e proíbe o
        #: zero justamente neste caso. Converter no consumidor, e não na conta,
        #: é o que evita mexer no número de que o posto `PLANO` depende.
        fisico = None
        porque = (
            "Ninguém apontou avanço neste plano ainda. O primeiro apontamento "
            "acende o número."
        )
    elif fisico is None:
        porque = (
            "As atividades apontadas ainda não têm peso. Vincule ao orçamento "
            "ou informe a duração para o avanço poder ser somado."
        )
    return {
        "fisico": fisico,
        "financeiro": bruto["financeiro"],
        "folhas": bruto["folhas"],
        "folhas_apontadas": bruto["folhas_apontadas"],
        "folhas_sem_peso": bruto["folhas_sem_peso"],
        "ultimo_apontamento": bruto["ultimo_apontamento"],
        "sem_apuracao_porque": porque,
    }


def _ultimo_ppc(obra_id, *, tenant_id) -> dict:
    serie = serie_ppc(obra_id=obra_id, tenant_id=tenant_id, limite=8)
    if not serie:
        return {
            "ppc": None, "semana_inicio": None, "comprometidos": 0,
            "cumpridos": 0, "peso_bases": [], "vezes_reaberta": 0,
            "encerrada_antes_do_fim": False, "serie": [],
            "sem_apuracao_porque": (
                "Nenhuma semana foi encerrada ainda. O índice aparece quando a "
                "primeira reunião de encerramento julgar os compromissos."
            ),
        }
    ultimo = serie[-1]
    return {
        "ppc": ultimo["ppc"],
        "semana_inicio": ultimo["semana_inicio"],
        "comprometidos": ultimo["comprometidos"],
        "cumpridos": ultimo["cumpridos"],
        "peso_bases": ultimo["peso_bases"],
        "vezes_reaberta": ultimo["vezes_reaberta"],
        "encerrada_antes_do_fim": ultimo["encerrada_antes_do_fim"],
        #: A tendência viaja junto porque **um PPC isolado não diz nada**: 68%
        #: subindo de 40% e 68% caindo de 90% são duas obras diferentes.
        "serie": serie,
        "sem_apuracao_porque": "",
    }


def _leitura_de_conformidade(obra_ids, *, tenant_id, desde=None,
                             ate=None) -> dict:
    """Conformidade por obra, **numa consulta para todas**.

    Mesma conta do `painel_de_conformidade` (conformes ÷ julgados, sobre ficha
    concluída), agregada em SQL em vez de por domínio: a carteira precisa de um
    número por obra, e chamar o painel quarenta vezes seria quarenta varreduras
    de item para produzir quarenta divisões.
    """
    itens = ItemVerificacao.objects.filter(
        tenant_id=tenant_id,
        verificacao__obra_id__in=obra_ids,
        verificacao__status=Verificacao.Status.CONCLUIDA,
        resultado__in=[ResultadoItem.CONFORME, ResultadoItem.NAO_CONFORME],
    )
    if desde:
        itens = itens.filter(verificacao__data__gte=desde)
    if ate:
        itens = itens.filter(verificacao__data__lte=ate)

    bruto: dict = {}
    for linha in (
        itens.values("verificacao__obra_id", "resultado")
        .annotate(n=Count("item_verificacao_id"))
    ):
        alvo = bruto.setdefault(linha["verificacao__obra_id"], {
            "conformes": 0, "nao_conformes": 0,
        })
        if linha["resultado"] == ResultadoItem.CONFORME:
            alvo["conformes"] += linha["n"]
        else:
            alvo["nao_conformes"] += linha["n"]

    pronto = {}
    for obra_id in obra_ids:
        contagem = bruto.get(obra_id)
        if not contagem:
            pronto[obra_id] = {
                "conformidade": None, "conformes": 0, "nao_conformes": 0,
                "julgados": 0,
                "sem_apuracao_porque": (
                    "Nenhuma ficha de verificação foi concluída nesta obra "
                    "ainda."
                ),
            }
            continue
        julgados = contagem["conformes"] + contagem["nao_conformes"]
        pronto[obra_id] = {
            "conformidade": (
                Decimal(contagem["conformes"]) * 100 / Decimal(julgados)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "conformes": contagem["conformes"],
            "nao_conformes": contagem["nao_conformes"],
            "julgados": julgados,
            "sem_apuracao_porque": "",
        }
    return pronto


def _leitura_de_seguranca(obra_ids, *, tenant_id) -> dict:
    """Dias sem acidente com afastamento — e o `None` que **não** é zero.

    Obra que nunca registrou um acidente com afastamento não tem "0 dias": ela
    não tem a série. Contar desde o início da obra seria fabricar — e num
    painel de segurança o número fabricado é o mais caro de todos, porque é o
    que faz alguém concluir que a obra é segura.
    """
    hoje = timezone.localdate()
    ultima: dict = {
        linha["obra_id"]: linha["ultima"]
        for linha in Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
            classificacao__in=[
                ClassificacaoOcorrencia.COM_AFASTAMENTO,
                ClassificacaoOcorrencia.OBITO,
            ],
        ).exclude(status=Ocorrencia.Status.CANCELADA)
        .values("obra_id").annotate(ultima=Max("ocorrido_em"))
    }
    abertas: dict = {
        linha["obra_id"]: linha["n"]
        for linha in Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
            status__in=[
                Ocorrencia.Status.ABERTA, Ocorrencia.Status.EM_INVESTIGACAO,
            ],
        ).values("obra_id").annotate(n=Count("ocorrencia_id"))
    }
    registradas: dict = {
        linha["obra_id"]: linha["n"]
        for linha in Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
        ).exclude(status=Ocorrencia.Status.CANCELADA)
        .values("obra_id").annotate(n=Count("ocorrencia_id"))
    }

    pronto = {}
    for obra_id in obra_ids:
        dia = _dia_de(ultima.get(obra_id))
        pronto[obra_id] = {
            "dias_sem_afastamento": None if dia is None else (hoje - dia).days,
            "ultimo_afastamento": dia,
            "ocorrencias_abertas": abertas.get(obra_id, 0),
            "ocorrencias_registradas": registradas.get(obra_id, 0),
            "sem_apuracao_porque": (
                "" if dia is not None else
                "Nenhum acidente com afastamento foi registrado nesta obra."
            ),
            "taxa_frequencia": None,
            "taxa_gravidade": None,
            "taxas_indisponiveis_porque": TAXAS_DE_SSMA_INDISPONIVEIS_PORQUE,
        }
    return pronto


def pulso_da_obra(*, obra_id, tenant_id, pode=_pode_tudo,
                  desde: date | None = None, ate: date | None = None) -> dict:
    """**As quatro leituras honestas da obra, num retorno só** (B6).

    Avanço contra a linha de base, PPC da última semana encerrada,
    conformidade do período e segurança. Quatro chamadas para quatro números
    faziam a tela de abertura esperar quatro vezes e — pior — deixavam cada
    número chegar com um recorte de período diferente do vizinho.

    **Cada bloco traz `sem_apuracao_porque`, e a tela escreve a frase.** Não é
    enfeite: é o que impede o zero. Avanço sem apontamento, PPC sem semana
    encerrada e conformidade sem ficha concluída são todos *ausência de
    medida*, e desenhar 0% em qualquer um deles afirma um fracasso que não
    aconteceu.
    """
    negados: list[dict] = []
    ve_plano = pode("pdca.cronograma.view")
    plano = _plano_vigente(obra_id, tenant_id=tenant_id) if ve_plano else None

    prazo = _leitura_de_prazo(plano) if ve_plano else None
    if not ve_plano:
        negados.append(_sem_permissao(
            "prazo", "o cronograma desta obra", "pdca.cronograma.view",
        ))

    if ve_plano and pode("pdca.avanco.view"):
        avanco = _leitura_de_avanco(plano)
    else:
        avanco = None
        negados.append(_sem_permissao(
            "avanco", "o avanço apontado desta obra", "pdca.avanco.view",
        ))

    if pode("pdca.programacao.view"):
        ppc = _ultimo_ppc(obra_id, tenant_id=tenant_id)
    else:
        ppc = None
        negados.append(_sem_permissao(
            "ppc", "o cumprimento da programação semanal",
            "pdca.programacao.view",
        ))

    if pode("pdca.verificacao.view"):
        conformidade = _leitura_de_conformidade(
            [obra_id], tenant_id=tenant_id, desde=desde, ate=ate,
        )[obra_id]
    else:
        conformidade = None
        negados.append(_sem_permissao(
            "conformidade", "as fichas de verificação desta obra",
            "pdca.verificacao.view",
        ))

    if pode("pdca.ocorrencia.view"):
        seguranca = _leitura_de_seguranca(
            [obra_id], tenant_id=tenant_id,
        )[obra_id]
    else:
        seguranca = None
        negados.append(_sem_permissao(
            "seguranca", "as ocorrências de segurança desta obra",
            "pdca.ocorrencia.view",
        ))

    return {
        "obra": obra_id,
        "prazo": prazo,
        "avanco": avanco,
        "ppc": ppc,
        "conformidade": conformidade,
        "seguranca": seguranca,
        "sem_permissao": negados,
    }


# --- B1: a carteira ---------------------------------------------------------

#: A ordem em que uma pendência dói — prazo legal primeiro, retrabalho por
#: último. A carteira usa para dizer **qual** é a pior de cada obra, em vez de
#: somar coisas que não se somam.
ORDEM_DA_CONSEQUENCIA = (
    "prazo_legal", "seguranca", "dinheiro", "compromisso", "retrabalho",
)

#: `(código, rótulo, consequência)` — a mesma taxonomia da fila do dia, para a
#: carteira e o cockpit não discordarem sobre o que é urgente.
CONTAGENS_DA_CARTEIRA = (
    ("cat_por_comunicar", "CAT por comunicar", "prazo_legal"),
    ("ocorrencias_sem_classificacao", "Ocorrência por classificar",
     "seguranca"),
    ("medicoes_a_atestar", "Medição esperando atesto", "dinheiro"),
    ("semanas_a_encerrar", "Semana por encerrar", "compromisso"),
    ("restricoes_vencidas", "Restrição com prazo vencido", "compromisso"),
    ("acoes_vencidas", "Ação com prazo vencido", "retrabalho"),
    ("ncs_abertas", "Defeito em aberto", "retrabalho"),
)


def _pendencias_da_carteira(obra_ids, *, tenant_id, pode) -> dict:
    """As contagens da carteira — **em sete consultas para todas as obras**.

    A fila do dia (`fila_do_dia`) lista; esta conta. Listar quarenta obras
    custaria quarenta varreduras de NC com prefetch e quarenta cálculos de
    prazo de CAT, e a carteira não mostra linha nenhuma — ela mostra qual obra
    precisa de você. **Os fatos contados são os mesmos**, e é por isso que
    entrar na obra não muda o número.
    """
    hoje = timezone.localdate()
    vazio = {codigo: 0 for codigo, _, _ in CONTAGENS_DA_CARTEIRA}
    saida = {obra_id: dict(vazio) for obra_id in obra_ids}
    negados: list[dict] = []

    def _somar(codigo, linhas, campo="obra_id"):
        for linha in linhas:
            alvo = saida.get(linha[campo])
            if alvo is not None:
                alvo[codigo] = linha["n"]

    if pode("pdca.ocorrencia.view"):
        _somar("cat_por_comunicar", Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
            tipo__in=Ocorrencia.TIPOS_QUE_EXIGEM_CAT,
            cat_emitida_em__isnull=True,
        ).exclude(status=Ocorrencia.Status.CANCELADA)
        .values("obra_id").annotate(n=Count("ocorrencia_id")))
        _somar("ocorrencias_sem_classificacao", Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
            classificacao=ClassificacaoOcorrencia.PENDENTE,
            status__in=[
                Ocorrencia.Status.ABERTA, Ocorrencia.Status.EM_INVESTIGACAO,
            ],
        ).values("obra_id").annotate(n=Count("ocorrencia_id")))
    else:
        negados.append(_sem_permissao(
            "seguranca", "as ocorrências de segurança", "pdca.ocorrencia.view",
        ))

    if pode("pdca.medicao.view"):
        _somar("medicoes_a_atestar", Medicao.objects.filter(
            tenant_id=tenant_id, contrato__obra_id__in=obra_ids,
            status=Medicao.Status.EM_APROVACAO,
        ).values("contrato__obra_id").annotate(n=Count("medicao_id")),
            campo="contrato__obra_id")
    else:
        negados.append(_sem_permissao(
            "medicao", "as medições", "pdca.medicao.view",
        ))

    if pode("pdca.programacao.view"):
        _somar("semanas_a_encerrar", ProgramacaoSemanal.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
            status=ProgramacaoSemanal.Status.COMPROMETIDA,
            semana_fim__lt=hoje,
        ).values("obra_id").annotate(n=Count("programacao_id")))
    else:
        negados.append(_sem_permissao(
            "programacao", "a programação semanal", "pdca.programacao.view",
        ))

    if pode("pdca.restricao.view"):
        _somar("restricoes_vencidas", Restricao.objects.filter(
            tenant_id=tenant_id,
            atividade__cronograma__obra_id__in=obra_ids,
            status=Restricao.Status.ABERTA, prazo__lt=hoje,
        ).values("atividade__cronograma__obra_id")
        .annotate(n=Count("restricao_id")),
            campo="atividade__cronograma__obra_id")
    else:
        negados.append(_sem_permissao(
            "restricao", "as restrições", "pdca.restricao.view",
        ))

    if pode("pdca.nc.view"):
        _somar("ncs_abertas", NaoConformidade.objects.filter(
            tenant_id=tenant_id, obra_id__in=obra_ids,
            status__in=[
                NaoConformidade.Status.ABERTA,
                NaoConformidade.Status.EM_TRATAMENTO,
            ],
        ).values("obra_id").annotate(n=Count("nc_id")))
        _somar("acoes_vencidas", PlanoAcao.objects.filter(
            tenant_id=tenant_id,
            nao_conformidade__obra_id__in=obra_ids,
            quando__lt=hoje,
            status__in=[
                PlanoAcao.Status.PLANEJADA, PlanoAcao.Status.EM_EXECUCAO,
            ],
        ).values("nao_conformidade__obra_id").annotate(n=Count("plano_id")),
            campo="nao_conformidade__obra_id")
    else:
        negados.append(_sem_permissao(
            "qualidade", "as não-conformidades", "pdca.nc.view",
        ))

    return {"por_obra": saida, "sem_permissao": negados}


def carteira(*, tenant_id, pode=_pode_tudo, obras=None) -> dict:
    """**As obras lado a lado** — a porta de fora e a casa da diretoria (B1).

    Até aqui todo agregado do módulo exigia `obra_id`: não havia uma leitura
    sequer que cruzasse obras, e sem ela a pergunta da diretoria — *qual obra
    precisa de mim esta semana?* — só tinha resposta abrindo uma por uma.

    **Não é painel de vaidade, e não soma o que não se soma.** Cada linha traz
    as pendências **discriminadas** e diz qual é a pior pela ordem de
    consequência; não existe um "12 pendências" que misture uma CAT vencendo
    com um defeito de pintura.

    **O teto de 40 obras é de leitura, e o caro é o avanço.** Cada linha custa
    o rollup do cronograma vigente daquela obra — a mesma média ponderada do
    posto, reusada em vez de reescrita. Acima do teto a resposta vem cortada
    dizendo quantas ficaram de fora.
    """
    from obras.models import Obra

    consulta = Obra.objects.filter(tenant_id=tenant_id)
    if obras:
        consulta = consulta.filter(obra_id__in=obras)
    quantas = consulta.count()
    lista = list(consulta.order_by("nome_obra")[:PDCA_TETO_OBRAS_NA_CARTEIRA])
    obra_ids = [o.pk for o in lista]
    if not obra_ids:
        return {
            "obras": [], "total": 0, "truncada": False,
            "teto": PDCA_TETO_OBRAS_NA_CARTEIRA, "sem_permissao": [],
        }

    pendencias = _pendencias_da_carteira(
        obra_ids, tenant_id=tenant_id, pode=pode,
    )
    negados: list[dict] = list(pendencias["sem_permissao"])

    ve_plano = pode("pdca.cronograma.view")
    ve_avanco = ve_plano and pode("pdca.avanco.view")
    ve_ppc = pode("pdca.programacao.view")
    ve_conformidade = pode("pdca.verificacao.view")
    ve_seguranca = pode("pdca.ocorrencia.view")

    if not ve_plano:
        negados.append(_sem_permissao(
            "prazo", "os cronogramas das obras", "pdca.cronograma.view",
        ))
    elif not ve_avanco:
        negados.append(_sem_permissao(
            "avanco", "o avanço apontado das obras", "pdca.avanco.view",
        ))
    if not ve_ppc:
        negados.append(_sem_permissao(
            "ppc", "o cumprimento da programação semanal",
            "pdca.programacao.view",
        ))
    if not ve_conformidade:
        negados.append(_sem_permissao(
            "conformidade", "as fichas de verificação",
            "pdca.verificacao.view",
        ))

    planos = {}
    if ve_plano:
        planos = {
            plano.obra_id: plano
            for plano in Cronograma.objects.filter(
                tenant_id=tenant_id, obra_id__in=obra_ids,
                status=Cronograma.Status.VIGENTE,
            )
        }

    conformidade = (
        _leitura_de_conformidade(obra_ids, tenant_id=tenant_id)
        if ve_conformidade else {}
    )
    seguranca = (
        _leitura_de_seguranca(obra_ids, tenant_id=tenant_id)
        if ve_seguranca else {}
    )

    linhas = []
    for obra in lista:
        plano = planos.get(obra.pk)
        contagens = pendencias["por_obra"][obra.pk]
        abertas = [
            {
                "codigo": codigo, "rotulo": rotulo,
                "consequencia": consequencia, "quantas": contagens[codigo],
            }
            for codigo, rotulo, consequencia in CONTAGENS_DA_CARTEIRA
            if contagens.get(codigo)
        ]
        pior = min(
            abertas,
            key=lambda p: ORDEM_DA_CONSEQUENCIA.index(p["consequencia"]),
            default=None,
        )
        linhas.append({
            "obra": obra.pk,
            "nome": obra.nome_obra,
            "status_obra": obra.status_obra,
            "status_rotulo": obra.get_status_obra_display(),
            "data_fim_prevista": obra.data_fim_prevista,
            "prazo": _leitura_de_prazo(plano) if ve_plano else None,
            "avanco": _leitura_de_avanco(plano) if ve_avanco else None,
            "ppc": _ultimo_ppc(obra.pk, tenant_id=tenant_id) if ve_ppc else None,
            "conformidade": conformidade.get(obra.pk),
            "seguranca": seguranca.get(obra.pk),
            #: Discriminadas, **nunca somadas**: a linha diz "CAT por comunicar
            #: · 1", e não "8 pendências". Ver a docstring.
            "pendencias": abertas,
            "pior_pendencia": pior,
        })

    return {
        "obras": linhas,
        "total": quantas,
        "truncada": quantas > len(linhas),
        "teto": PDCA_TETO_OBRAS_NA_CARTEIRA,
        "sem_permissao": negados,
    }


# --- B4: a busca única ------------------------------------------------------

#: Abaixo disto o `LIKE '%a%'` casa com quase tudo, e os oito resultados que
#: voltam são as oito primeiras linhas do banco. É parâmetro de **acerto**, e
#: por isso mora aqui e não no `planos.py` — a fronteira está escrita na §5.6
#: de lá. Quem limita o **alcance** é o `PDCA_TETO_RESULTADOS_POR_ESPECIE`.
MINIMO_DE_LETRAS = 2


def busca_unica(*, tenant_id, termo: str, pode=_pode_tudo,
                obra_id=None) -> dict:
    """**Uma busca sobre as sete espécies do módulo** (B4).

    É a válvula que permite manter o menu em seis postos: quem usa o módulo
    todo dia para de navegar por menu na primeira semana e passa a escrever o
    nome do que quer. Sem ela, cada assunto novo do backend pressiona por um
    item de menu — que foi exatamente como o depósito nasceu da primeira vez.

    **Sem acento nas duas pontas**, pela régua de acessibilidade da casa: o
    `__unaccent__icontains` é o mesmo que o `BuscaSemAcento` interpõe nas
    listas. Quem digita `fundacao` acha `Fundação`, no celular e de luva.

    **Cada espécie cobra a permissão dela** e é cortada pelo próprio teto — por
    espécie, e não no total, para quarenta atividades chamadas "alvenaria" não
    esconderem o contrato que também se chama assim.
    """
    termo = (termo or "").strip()
    if len(termo) < MINIMO_DE_LETRAS:
        return {
            "termo": termo,
            "curta": True,
            "minimo_de_letras": MINIMO_DE_LETRAS,
            "teto_por_especie": PDCA_TETO_RESULTADOS_POR_ESPECIE,
            "especies": [],
            "especies_varridas": 0,
            "total": 0,
            "sem_permissao": [],
            "aviso": f"Escreva pelo menos {MINIMO_DE_LETRAS} letras.",
        }

    teto = PDCA_TETO_RESULTADOS_POR_ESPECIE
    especies: list[dict] = []
    negados: list[dict] = []

    def _especie(codigo, rotulo, permissao, consulta, monta):
        if not pode(permissao):
            negados.append(_sem_permissao(codigo, rotulo.lower(), permissao))
            return
        achados = list(consulta[:teto + 1])
        especies.append({
            "codigo": codigo,
            "rotulo": rotulo,
            "resultados": [monta(objeto) for objeto in achados[:teto]],
            "truncada": len(achados) > teto,
        })

    def _da_obra(consulta, campo="obra_id"):
        if obra_id is None:
            return consulta
        return consulta.filter(**{campo: obra_id})

    _especie(
        "atividade", "Atividades", "pdca.cronograma.view",
        _da_obra(
            Atividade.objects.filter(tenant_id=tenant_id).filter(
                Q(codigo__unaccent__icontains=termo)
                | Q(nome__unaccent__icontains=termo),
            ).select_related("cronograma", "cronograma__obra", "local")
            .order_by("cronograma__obra_id", "codigo"),
            campo="cronograma__obra_id",
        ),
        lambda a: {
            "chave": f"atividade:{a.pk}", "id": a.pk,
            "titulo": f"{a.codigo} · {a.nome}",
            "subtitulo": (a.local.nome if a.local_id else ""),
            "obra": a.cronograma.obra_id,
            "obra_nome": (
                a.cronograma.obra.nome_obra if a.cronograma.obra_id else ""
            ),
            "extra": {"cronograma": a.cronograma_id, "critica": a.critica},
        },
    )

    _especie(
        "local", "Locais da obra", "pdca.local.view",
        _da_obra(
            LocalObra.objects.filter(tenant_id=tenant_id, ativo=True).filter(
                Q(codigo__unaccent__icontains=termo)
                | Q(nome__unaccent__icontains=termo),
            ).select_related("obra")
            .order_by("obra_id", "profundidade", "codigo"),
        ),
        lambda lugar: {
            "chave": f"local:{lugar.pk}", "id": lugar.pk,
            "titulo": f"{lugar.codigo} · {lugar.nome}",
            "subtitulo": lugar.get_nivel_display(),
            "obra": lugar.obra_id,
            "obra_nome": lugar.obra.nome_obra if lugar.obra_id else "",
            "extra": {},
        },
    )

    _especie(
        "contrato", "Contratos", "pdca.contrato.view",
        _da_obra(
            ContratoObra.objects.filter(tenant_id=tenant_id).filter(
                Q(numero__unaccent__icontains=termo)
                | Q(objeto__unaccent__icontains=termo)
                | Q(fornecedor__razao_social__unaccent__icontains=termo)
                | Q(cliente__nome_completo__unaccent__icontains=termo),
            ).select_related("obra", "fornecedor", "cliente").order_by("-criado_em"),
        ),
        lambda c: {
            "chave": f"contrato:{c.pk}", "id": c.pk,
            "titulo": f"Contrato {c.numero}",
            "subtitulo": (c.objeto or "")[:120],
            "obra": c.obra_id,
            "obra_nome": c.obra.nome_obra if c.obra_id else "",
            "extra": {"status": c.status},
        },
    )

    _especie(
        "medicao", "Medições", "pdca.medicao.view",
        _da_obra(
            Medicao.objects.filter(tenant_id=tenant_id).filter(
                Q(contrato__numero__unaccent__icontains=termo)
                | Q(observacao__unaccent__icontains=termo),
            ).select_related("contrato", "contrato__obra")
            .order_by("-periodo_fim"),
            campo="contrato__obra_id",
        ),
        lambda m: {
            "chave": f"medicao:{m.pk}", "id": m.pk,
            "titulo": f"Medição {m.numero} · contrato {m.contrato.numero}",
            "subtitulo": (
                f"{m.periodo_inicio:%d/%m/%Y} a {m.periodo_fim:%d/%m/%Y} · "
                f"{m.get_status_display()}"
            ),
            "obra": m.contrato.obra_id,
            "obra_nome": (
                m.contrato.obra.nome_obra if m.contrato.obra_id else ""
            ),
            "extra": {"status": m.status, "contrato": m.contrato_id},
        },
    )

    _especie(
        "verificacao", "Fichas de verificação", "pdca.verificacao.view",
        _da_obra(
            Verificacao.objects.filter(tenant_id=tenant_id).filter(
                Q(modelo__codigo__unaccent__icontains=termo)
                | Q(modelo__nome__unaccent__icontains=termo)
                | Q(inspetor__unaccent__icontains=termo),
            ).select_related("modelo", "obra", "local").order_by("-data"),
        ),
        lambda v: {
            "chave": f"verificacao:{v.pk}", "id": v.pk,
            "titulo": f"{v.modelo.codigo} · {v.modelo.nome}",
            "subtitulo": (
                f"{v.data:%d/%m/%Y} · {v.get_status_display()}"
                + (f" · {v.local.nome}" if v.local_id else "")
            ),
            "obra": v.obra_id,
            "obra_nome": v.obra.nome_obra if v.obra_id else "",
            "extra": {"status": v.status},
        },
    )

    _especie(
        "nc", "Não-conformidades", "pdca.nc.view",
        _da_obra(
            NaoConformidade.objects.filter(tenant_id=tenant_id).filter(
                Q(descricao__unaccent__icontains=termo)
                | Q(aberta_por__unaccent__icontains=termo),
            ).select_related("obra", "local").order_by("-aberta_em"),
        ),
        lambda n: {
            "chave": f"nc:{n.pk}", "id": n.pk,
            "titulo": n.descricao[:120],
            "subtitulo": (
                f"{n.get_gravidade_display()} · {n.get_status_display()}"
                + (f" · {n.local.nome}" if n.local_id else "")
            ),
            "obra": n.obra_id,
            "obra_nome": n.obra.nome_obra if n.obra_id else "",
            "extra": {"status": n.status, "gravidade": n.gravidade},
        },
    )

    _especie(
        "ocorrencia", "Ocorrências de segurança", "pdca.ocorrencia.view",
        _da_obra(
            Ocorrencia.objects.filter(tenant_id=tenant_id).filter(
                Q(descricao__unaccent__icontains=termo)
                | Q(agente_causador__unaccent__icontains=termo),
            ).select_related("obra", "local").order_by("-ocorrido_em"),
        ),
        lambda o: {
            "chave": f"ocorrencia:{o.pk}", "id": o.pk,
            "titulo": o.get_tipo_display(),
            #: **Sem nada do bloco clínico.** Lesão, CID e atestado saem só
            #: pelo `pdca.ocorrencia.dado_medico`, e uma busca que os vazasse
            #: no subtítulo seria a porta lateral que o serializer fecha na
            #: porta da frente.
            "subtitulo": o.descricao[:120],
            "obra": o.obra_id,
            "obra_nome": o.obra.nome_obra if o.obra_id else "",
            "extra": {"status": o.status, "ocorrido_em": o.ocorrido_em},
        },
    )

    return {
        "termo": termo,
        "curta": False,
        "minimo_de_letras": MINIMO_DE_LETRAS,
        "teto_por_especie": teto,
        #: Só as espécies que acharam alguma coisa. Sete cabeçalhos vazios numa
        #: paleta de comando afogam o único resultado que veio.
        "especies": [e for e in especies if e["resultados"]],
        "especies_varridas": len(especies),
        "total": sum(len(e["resultados"]) for e in especies),
        "sem_permissao": negados,
    }


# --- O terceiro bloco do cockpit: o que mudou -------------------------------

#: Quantos dias para trás o cockpit olha por padrão. **Não é teto**: o
#: chamador passa outro, e o que corta a resposta é o teto de linhas da fila
#: (§5.5n). É o tamanho da pergunta *"o que aconteceu desde que eu saí"*, e
#: uma semana é o que cobre quem tirou sexta e volta na segunda.
DIAS_DE_MUDANCAS = 7


def mudancas_recentes(*, obra_id, tenant_id, pode=_pode_tudo,
                      dias: int = DIAS_DE_MUDANCAS) -> dict:
    """**Fatos, não posts** — o que mudou nesta obra nos últimos dias.

    A terceira faixa do cockpit, e a única que olha para trás. A fila diz o
    que espera e o pulso diz como a obra está; esta responde à pergunta de
    quem tirou sexta-feira: *o que aconteceu enquanto eu não estava?*

    **Cada linha é um ato com carimbo de quem o praticou**, tirado do próprio
    campo que o registrou — `congelada_em` da medição, `encerrada_em` da
    semana, `publicado_em` do cronograma. Não existe tabela de evento e não
    deveria existir: um log paralelo divergiria do fato na primeira vez que
    alguém gravasse por outro caminho, e o que a obra quer saber é o que
    aconteceu com os documentos, não o que um registrador achou que aconteceu.
    """
    desde = timezone.now() - timedelta(days=max(1, dias))
    teto = PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA
    fatos: list[dict] = []
    negados: list[dict] = []

    def _fato(quando, *, tipo, id_, verbo, titulo, quem):
        fatos.append({
            "chave": f"{tipo}:{id_}",
            "tipo": tipo,
            "id": id_,
            "verbo": verbo,
            "titulo": titulo,
            "quem": quem or "",
            "quando": quando,
        })

    if pode("pdca.medicao.view"):
        for m in Medicao.objects.filter(
            tenant_id=tenant_id, contrato__obra_id=obra_id,
            congelada_em__gte=desde, status=Medicao.Status.APROVADA,
        ).select_related("contrato").order_by("-congelada_em")[:teto]:
            _fato(
                m.congelada_em, tipo="medicao", id_=m.pk, verbo="atestada",
                titulo=f"Medição {m.numero} · contrato {m.contrato.numero}",
                quem=m.apurada_por,
            )
    else:
        negados.append(_sem_permissao(
            "medicao", "as medições desta obra", "pdca.medicao.view",
        ))

    if pode("pdca.programacao.view"):
        for p in ProgramacaoSemanal.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, encerrada_em__gte=desde,
        ).order_by("-encerrada_em")[:teto]:
            _fato(
                p.encerrada_em, tipo="programacao", id_=p.pk,
                verbo="semana encerrada",
                titulo=f"Semana de {p.semana_inicio:%d/%m/%Y}",
                quem=p.encerrada_por,
            )
    else:
        negados.append(_sem_permissao(
            "programacao", "a programação semanal desta obra",
            "pdca.programacao.view",
        ))

    if pode("pdca.cronograma.view"):
        for c in Cronograma.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, publicado_em__gte=desde,
        ).order_by("-publicado_em")[:teto]:
            _fato(
                c.publicado_em, tipo="cronograma", id_=c.pk,
                verbo="plano publicado",
                titulo=f"Versão {c.versao} · {c.descricao}",
                quem="",
            )
    else:
        negados.append(_sem_permissao(
            "prazo", "o cronograma desta obra", "pdca.cronograma.view",
        ))

    if pode("pdca.restricao.view"):
        for r in Restricao.objects.filter(
            tenant_id=tenant_id, atividade__cronograma__obra_id=obra_id,
            removida_em__gte=desde, status=Restricao.Status.REMOVIDA,
        ).select_related("atividade").order_by("-removida_em")[:teto]:
            _fato(
                r.removida_em, tipo="restricao", id_=r.pk,
                verbo="destravada", titulo=r.descricao[:120],
                quem=r.removida_por,
            )
    else:
        negados.append(_sem_permissao(
            "restricao", "as restrições desta obra", "pdca.restricao.view",
        ))

    if pode("pdca.nc.view"):
        for n in NaoConformidade.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, aberta_em__gte=desde,
        ).order_by("-aberta_em")[:teto]:
            _fato(
                n.aberta_em, tipo="nc", id_=n.pk, verbo="defeito registrado",
                titulo=f"{n.get_gravidade_display()} · {n.descricao[:110]}",
                quem=n.aberta_por,
            )
        for n in NaoConformidade.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, encerrada_em__gte=desde,
        ).order_by("-encerrada_em")[:teto]:
            _fato(
                n.encerrada_em, tipo="nc", id_=n.pk, verbo="defeito encerrado",
                titulo=f"{n.get_gravidade_display()} · {n.descricao[:110]}",
                quem=n.encerrada_por,
            )
    else:
        negados.append(_sem_permissao(
            "qualidade", "as não-conformidades desta obra", "pdca.nc.view",
        ))

    if pode("pdca.verificacao.view"):
        for v in Verificacao.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, concluida_em__gte=desde,
        ).select_related("modelo").order_by("-concluida_em")[:teto]:
            _fato(
                v.concluida_em, tipo="verificacao", id_=v.pk,
                verbo="ficha concluída", titulo=v.modelo.nome,
                quem=v.concluida_por,
            )
    else:
        negados.append(_sem_permissao(
            "verificacao", "as fichas de verificação desta obra",
            "pdca.verificacao.view",
        ))

    if pode("pdca.ocorrencia.view"):
        for o in Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, registrada_em__gte=desde,
        ).order_by("-registrada_em")[:teto]:
            _fato(
                o.registrada_em, tipo="ocorrencia", id_=o.pk,
                verbo="ocorrência registrada", titulo=o.get_tipo_display(),
                quem=o.registrada_por,
            )
        for o in Ocorrencia.objects.filter(
            tenant_id=tenant_id, obra_id=obra_id, classificada_em__gte=desde,
        ).order_by("-classificada_em")[:teto]:
            _fato(
                o.classificada_em, tipo="ocorrencia", id_=o.pk,
                verbo="ocorrência classificada",
                titulo=(
                    f"{o.get_tipo_display()} · {o.get_classificacao_display()}"
                ),
                quem=o.classificada_por,
            )
    else:
        negados.append(_sem_permissao(
            "seguranca", "as ocorrências de segurança desta obra",
            "pdca.ocorrencia.view",
        ))

    fatos.sort(key=lambda f: f["quando"], reverse=True)
    return {
        "obra": obra_id,
        "dias": dias,
        "desde": desde,
        "fatos": fatos[:teto],
        "total": len(fatos),
        "truncada": len(fatos) > teto,
        "sem_permissao": negados,
    }


# --- B5: a frente de quem está no canteiro ---------------------------------
#
# **A leitura da segunda superfície.** As quatro anteriores respondem a quem
# olha a obra de fora — a carteira cruza obras, a fila junta assuntos, o pulso
# resume e a busca acha. Esta responde a quem está **dentro** dela, com a luva
# na mão, e a pergunta é outra: *o que é meu, agora?*
#
# É a leitura que produz o dado de todas as outras. O avanço que o pulso mostra,
# o compromisso que o PPC divide e a ficha de que sai a conformidade nascem
# aqui, no canteiro — e frontend de campo ruim é indicador inventado.


def _bloco_da_frente(codigo: str, rotulo: str, o_que_fazer: str,
                     linhas: list[dict], *, vazio_porque: str = "") -> dict:
    """Um bloco da frente, já cortado pelo teto **do bloco**.

    Por bloco e não no total, pela mesma razão da faixa da fila (§5.5n do
    `planos.py`): cinquenta restrições vencidas não podem esconder a ficha que
    está parada esperando uma resposta.
    """
    cortadas = linhas[:PDCA_TETO_LINHAS_POR_FRENTE]
    return {
        "codigo": codigo,
        "rotulo": rotulo,
        #: O verbo que fecha o bloco. É a mesma régua do `o_que_decidir` da
        #: fila: lista que diz o que existe e não diz o que fazer é inventário.
        "o_que_fazer": o_que_fazer,
        "linhas": cortadas,
        "total": len(linhas),
        "truncada": len(linhas) > len(cortadas),
        #: Bloco vazio **com razão**. No celular, uma lista em branco é
        #: indistinguível de uma lista que não carregou — e a pessoa conclui
        #: que o sistema está fora do ar em vez de que não há nada para ela.
        "vazio_porque": vazio_porque if not cortadas else "",
    }


def minhas_frentes(*, tenant_id, quem: str, pode=_pode_tudo, obra_id=None,
                   hoje: date | None = None) -> dict:
    """**O que está atribuído a quem pede, na semana corrente** (B5).

    Quatro blocos, e os quatro saem de um campo de texto: o compromisso que a
    pessoa assumiu no quadro, a trava que é dela remover, a ação de conserto
    que é dela fazer e a ficha que está esperando ela responder.

    **Por que casa por nome, e não por FK.** `responsavel`, `quem` e `inspetor`
    são **rótulo durável** em todo o módulo, e a decisão é anterior a esta
    leitura: quem assume a frente é com frequência o encarregado da empreiteira,
    quem destrava é o projetista ou o fiscal da prefeitura, e exigir FK de
    usuário obrigaria a cadastrar a prefeitura para poder escrever "aguardando
    alvará". A consequência é que "meu" se resolve comparando **nome sem
    acento**, e a resposta diz contra qual nome casou — quem não se reconhece
    na lista descobre por quê em vez de concluir que o sistema esqueceu dela.

    **E por isso `quem` pode vir de fora.** O escritório digita o rótulo que
    usa ("Mestre Antônio"), que nem sempre é o nome do login. Sem poder
    escolher o nome, a pessoa cujo cadastro diverge veria a frente vazia para
    sempre. Não é vazamento: é a mesma lista que o quadro da semana já mostra
    inteira a quem tem `pdca.programacao.view`.

    **Atravessa obras de propósito** — sem `obra_id` vêm todas as do tenant. O
    encarregado costuma estar numa; o mestre que cobre duas veria metade do
    trabalho dele se a leitura exigisse escolher.

    **A permissão é por bloco, e nunca 403 na página.** Quem vê a programação e
    não vê a qualidade recebe os compromissos e, no lugar das fichas, a frase
    de qual permissão falta. Recusar a página inteira tiraria do encarregado o
    trabalho que ele pode fazer.
    """
    hoje = hoje or timezone.localdate()
    inicio = segunda_da_semana(hoje)
    fim = inicio + timedelta(days=6)
    alvo = (quem or "").strip()

    corpo = {
        "quem": alvo,
        "obra": obra_id,
        "hoje": hoje,
        "semana_inicio": inicio,
        "semana_fim": fim,
        "compromissos": None,
        "restricoes": None,
        "acoes": None,
        "fichas": None,
        "total": 0,
        "blocos_varridos": 4,
        "teto": PDCA_TETO_LINHAS_POR_FRENTE,
        "sem_permissao": [],
        #: Sem nome não há frente, e a frase diz o que fazer a respeito.
        "sem_nome_porque": "" if alvo else (
            "Não sabemos em que nome procurar. O escritório escreve o nome de "
            "quem assume cada frente no quadro da semana — peça para "
            "conferirem como o seu está escrito lá."
        ),
    }
    if not alvo:
        return corpo

    negados: list[dict] = []

    # --- o que eu assumi nesta semana --------------------------------------
    if pode("pdca.programacao.view"):
        semanas = ProgramacaoSemanal.objects.filter(
            tenant_id=tenant_id, semana_inicio=inicio,
        ).select_related("obra")
        if obra_id:
            semanas = semanas.filter(obra_id=obra_id)
        semanas = list(semanas)
        por_semana = {s.pk: s for s in semanas}

        meus = list(
            ItemProgramacao.objects.filter(
                tenant_id=tenant_id,
                programacao_id__in=list(por_semana),
                responsavel__unaccent__iexact=alvo,
            )
            .select_related("atividade", "local")
            .order_by("ordem", "item_programacao_id")
        )
        #: O apontado vem **uma consulta por semana**, e não uma por cartão —
        #: a mesma régua do quadro no escritório.
        com_cartao = {item.programacao_id for item in meus}
        apontado: dict[int, Decimal] = {}
        for semana in semanas:
            if semana.pk in com_cartao:
                apontado.update(avanco_apontado_dos_itens(semana))
        alvos = [item.atividade_id for item in meus]
        travas = restricoes_abertas_por_atividade(alvos, tenant_id=tenant_id)
        defeitos = ncs_abertas_por_atividade(alvos, tenant_id=tenant_id)

        linhas = []
        for item in meus:
            semana = por_semana[item.programacao_id]
            ponto = apontado.get(item.pk)
            linhas.append({
                "item": item.pk,
                "programacao": semana.pk,
                "obra": semana.obra_id,
                "obra_nome": semana.obra.nome_obra,
                "atividade": item.atividade_id,
                "codigo": item.atividade.codigo,
                "nome": item.atividade.nome,
                "local": item.local_id,
                "local_rotulo": item.local.nome if item.local_id else "",
                #: Prometido e feito lado a lado, **nunca somados**: um é o que
                #: a equipe assumiu, o outro é o que o campo apontou.
                "previsto": item.percentual_previsto,
                "apontado": ponto,
                #: Nulo é "ninguém apontou", que é diferente de zero — ver
                #: `avanco_apontado_dos_itens`.
                "apontou": ponto is not None,
                "restricoes_abertas": travas.get(item.atividade_id, 0),
                "ncs_abertas": defeitos.get(item.atividade_id, 0),
                "vezes_arrastado": item.vezes_arrastado or 0,
                "cumprido": item.cumprido,
                "status_da_semana": semana.status,
                "semana_aberta": semana.esta_aberta_para_montagem,
            })
        corpo["compromissos"] = _bloco_da_frente(
            "compromissos", "O que eu assumi nesta semana",
            "Aponte o quanto andou",
            linhas,
            vazio_porque=(
                "Nenhum serviço desta semana está no seu nome. Quem monta o "
                "quadro é a reunião de segunda — se você assumiu uma frente "
                "lá, peça para escreverem o seu nome nela."
            ),
        )
    else:
        negados.append(_sem_permissao(
            "compromissos", "os compromissos da semana",
            "pdca.programacao.view",
        ))

    # --- o que eu tenho de destravar ---------------------------------------
    if pode("pdca.restricao.view"):
        travadas = Restricao.objects.filter(
            tenant_id=tenant_id, status=Restricao.Status.ABERTA,
            responsavel__unaccent__iexact=alvo,
        ).select_related("atividade", "atividade__cronograma", "local")
        if obra_id:
            travadas = travadas.filter(atividade__cronograma__obra_id=obra_id)
        linhas = [
            {
                "restricao": r.pk,
                "obra": r.atividade.cronograma.obra_id,
                "atividade": r.atividade_id,
                "codigo": r.atividade.codigo,
                "nome": r.atividade.nome,
                "local_rotulo": r.local.nome if r.local_id else "",
                "tipo": r.tipo,
                "tipo_rotulo": r.get_tipo_display(),
                "descricao": r.descricao[:200],
                "desde": _dia_de(r.criada_em),
                "dias": _dias_desde(r.criada_em),
                "prazo": _prazo(r.prazo),
                "demanda_scm": r.demanda_scm_id,
            }
            for r in travadas.order_by(
                F("prazo").asc(nulls_last=True), "-restricao_id",
            )
        ]
        corpo["restricoes"] = _bloco_da_frente(
            "restricoes", "O que está no seu nome para destravar",
            "Diga como foi removida",
            linhas,
            vazio_porque="Nenhuma trava da obra está esperando você.",
        )
    else:
        negados.append(_sem_permissao(
            "restricoes", "as restrições da obra", "pdca.restricao.view",
        ))

    # --- o conserto que é meu ----------------------------------------------
    if pode("pdca.nc.view"):
        acoes = PlanoAcao.objects.filter(
            tenant_id=tenant_id,
            quem__unaccent__iexact=alvo,
            status__in=[
                PlanoAcao.Status.PLANEJADA, PlanoAcao.Status.EM_EXECUCAO,
            ],
        ).select_related("nao_conformidade", "nao_conformidade__local")
        if obra_id:
            acoes = acoes.filter(nao_conformidade__obra_id=obra_id)
        linhas = [
            {
                "acao": a.pk,
                "nc": a.nao_conformidade_id,
                "obra": a.nao_conformidade.obra_id,
                "o_que": a.o_que[:200],
                "onde": a.onde or (
                    a.nao_conformidade.local.nome
                    if a.nao_conformidade.local_id else ""
                ),
                "como": a.como[:200],
                "status": a.status,
                "status_rotulo": a.get_status_display(),
                "gravidade": a.nao_conformidade.gravidade,
                "gravidade_rotulo": a.nao_conformidade.get_gravidade_display(),
                "defeito": a.nao_conformidade.descricao[:160],
                "prazo": _prazo(a.quando),
            }
            for a in acoes.order_by(
                F("quando").asc(nulls_last=True), "-plano_id",
            )
        ]
        corpo["acoes"] = _bloco_da_frente(
            "acoes", "O conserto que é seu",
            "Conclua e registre o que foi feito",
            linhas,
            vazio_porque="Nenhum conserto está no seu nome.",
        )
    else:
        negados.append(_sem_permissao(
            "acoes", "os planos de ação dos defeitos", "pdca.nc.view",
        ))

    # --- a ficha que está esperando você -----------------------------------
    if pode("pdca.verificacao.view"):
        fichas = Verificacao.objects.filter(
            tenant_id=tenant_id, status=Verificacao.Status.EM_ANDAMENTO,
            inspetor__unaccent__iexact=alvo,
        ).select_related("modelo", "local", "atividade")
        if obra_id:
            fichas = fichas.filter(obra_id=obra_id)
        fichas = list(fichas.order_by("data", "-verificacao_id"))
        pendentes = {
            linha["verificacao_id"]: linha["n"]
            for linha in ItemVerificacao.objects.filter(
                tenant_id=tenant_id,
                verificacao_id__in=[f.pk for f in fichas],
                resultado=ResultadoItem.PENDENTE,
            ).values("verificacao_id").annotate(n=Count("item_verificacao_id"))
        }
        linhas = [
            {
                "verificacao": f.pk,
                "obra": f.obra_id,
                "modelo_codigo": f.modelo.codigo,
                "modelo_nome": f.modelo.nome,
                "onde": (
                    f.local.nome if f.local_id
                    else (f.atividade.nome if f.atividade_id else "")
                ),
                "desde": f.data,
                "dias": (hoje - f.data).days,
                #: Quantas perguntas ainda estão sem resposta. É o que diz se a
                #: ficha é de cinco minutos ou de uma manhã, e sem isso a
                #: pessoa abre para descobrir.
                "por_responder": pendentes.get(f.pk, 0),
            }
            for f in fichas
        ]
        corpo["fichas"] = _bloco_da_frente(
            "fichas", "A ficha que está esperando você",
            "Responda item a item",
            linhas,
            vazio_porque="Nenhuma ficha está aberta no seu nome.",
        )
    else:
        negados.append(_sem_permissao(
            "fichas", "as fichas de verificação", "pdca.verificacao.view",
        ))

    corpo["sem_permissao"] = negados
    corpo["total"] = sum(
        bloco["total"]
        for bloco in (
            corpo["compromissos"], corpo["restricoes"],
            corpo["acoes"], corpo["fichas"],
        )
        if bloco is not None
    )
    return corpo
