# backend/moduloorcamento/cronograma.py
"""O cronograma físico-financeiro do orçamento — **por etapa**, e calculado.

*Decisão do dono, 10/10/2026:* o cronograma nasce do orçamento e acompanha as
versões dele; o orçamento entrega **só etapas** — quando cada uma começa,
quando termina, quanto vale e, quando a planilha tem composição aberta, quantas
horas de mão de obra ela orça. O detalhe (serviço, frente, sequência, avanço) é
do PDCA, que gera as atividades daqui e compara o executado com este plano.

Antes o planejador digitava um percentual em cada célula etapa × mês. Ferramenta
de mercado não funciona assim: informa-se o período e a forma da curva, e a
grade sai pronta. Aqui é igual:

    etapa (início, término, curva)  →  peso de cada dia útil  →  % de cada mês

**Dia útil, e não dia corrido.** Julho com 23 dias de trabalho e dezembro com
16 não recebem a mesma fatia de uma etapa que atravessa os dois. O expediente é
o da obra no PDCA (`CalendarioTrabalho`: dias da semana, feriados do lugar,
exceções); sem expediente cadastrado, segunda a sexta com os feriados
nacionais — e a resposta diz qual dos dois valeu (`expediente`).

**As curvas** são pesos sobre a posição `x ∈ (0, 1)` do dia útil no período:

    linear  1              S       6·x·(1−x)   (o sino cuja acumulada é o S)
    início  2·(1−x)        fim     2·x

`MANUAL` não recalcula nada: as células passam a ser a verdade e a edição fina
(`ParcelaEtapaViewSet`) continua valendo. Editar uma célula de etapa com curva
calculada a converte para manual — senão a próxima mudança de data apagaria o
ajuste em silêncio.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import ItemOrcado, ItemOrcadoInsumo, Orcamento, ParcelaEtapa, PlanoEtapa
from .planilha import dinheiro

CEM = Decimal("100")
ZERO = Decimal("0")
QUATRO = Decimal("0.0001")
DEC = DecimalField(max_digits=20, decimal_places=4)

#: Unidades em que o insumo de mão de obra é a **hora** — é delas que sai o
#: homem-hora orçado. Mensalista (`MES`) não vira hora: converter salário mensal
#: em hora pediria uma jornada que o orçamento não declara.
UNIDADES_DE_HORA = ("H", "h", "HR", "hr", "Hr")

#: Guarda-corpo do laço que anda um dia por vez — não é teto de produto (§5.6
#: do `payment/planos.py`), é o mesmo de `modulopdca.services._MAXIMO_DIAS_CAMINHADOS`.
_MAXIMO_DIAS = 365 * 10


class CronogramaInvalido(Exception):
    """Período impossível, etapa de outra obra, curva desconhecida."""


class CronogramaFechado(CronogramaInvalido):
    """O orçamento é história (superado ou cancelado) — a API responde 409."""


def exigir_cronograma_editavel(orcamento: Orcamento) -> None:
    if not orcamento.cronograma_editavel:
        raise CronogramaFechado(
            f"Orçamento v{orcamento.versao} está {orcamento.get_status_display().lower()} — "
            "o cronograma dele é história."
        )


def carimbar(orcamento: Orcamento) -> None:
    """Marca que o cronograma mudou — é o que o PDCA lê para avisar."""
    agora = timezone.now()
    Orcamento.objects.filter(pk=orcamento.pk).update(cronograma_atualizado_em=agora)
    orcamento.cronograma_atualizado_em = agora


# ---------------------------------------------------------------------------
# O expediente — de período para dias úteis
# ---------------------------------------------------------------------------


class Expediente:
    """Responde "trabalha-se neste dia?" e "quantas horas rende o dia?".

    Envolve o `CalendarioTrabalho` da obra (o mesmo do CPM do PDCA) quando
    existe; senão, segunda a sexta com feriados nacionais. A diferença viaja em
    `fonte`, porque é ela que diz se o número de dias é o da obra ou um palpite
    honesto e declarado.
    """

    def __init__(self, orcamento: Orcamento, inicio: date, fim: date):
        self.calendario = None
        self.horas_por_dia: Decimal | None = None
        self.fonte = "segunda_a_sexta"
        try:
            from modulopdca import services as pdca

            self.calendario = pdca.calendario_da_obra(orcamento.obra, tenant_id=orcamento.tenant_id)
        except Exception:  # noqa: BLE001 — sem PDCA o cronograma continua valendo
            pdca = None
        if self.calendario is not None:
            self.fonte = "expediente_da_obra"
            self.horas_por_dia = self.calendario.horas_por_dia
            self._feriados = pdca.feriados_do_periodo(self.calendario, inicio, fim, obra=orcamento.obra)
            self._excecoes = pdca._excecoes(self.calendario, inicio, fim)
            self._pdca = pdca
        else:
            from modulocalendar.dias_uteis import feriados_da_localidade

            self._feriados = feriados_da_localidade(inicio, fim)

    def util(self, dia: date) -> bool:
        if self.calendario is not None:
            return self._pdca.eh_dia_util(
                self.calendario, dia, feriados=self._feriados, excecoes=self._excecoes,
            )
        return dia.weekday() < 5 and dia not in self._feriados

    def dias(self, inicio: date, fim: date) -> list[date]:
        if fim < inicio:
            return []
        if (fim - inicio).days > _MAXIMO_DIAS:
            raise CronogramaInvalido("Período de etapa acima de dez anos — confira as datas.")
        saida, dia = [], inicio
        while dia <= fim:
            if self.util(dia):
                saida.append(dia)
            dia += timedelta(days=1)
        return saida


# ---------------------------------------------------------------------------
# A curva — de dias úteis para percentual por mês
# ---------------------------------------------------------------------------


def _peso(curva: str, x: Decimal) -> Decimal:
    if curva == PlanoEtapa.Curva.S:
        return 6 * x * (1 - x)
    if curva == PlanoEtapa.Curva.INICIO:
        return 2 * (1 - x)
    if curva == PlanoEtapa.Curva.FIM:
        return 2 * x
    return Decimal("1")


def percentuais_por_mes(dias: list[date], curva: str) -> dict[date, Decimal]:
    """`{competência: %}` somando exatamente 100, com o resíduo no último mês.

    Sem dia útil no período (uma etapa de um sábado só, num expediente de
    segunda a sexta) a etapa inteira cai no mês do término — o custo existe e
    precisa estar em algum mês; espalhar por dias que não se trabalha seria
    inventar.
    """
    if not dias:
        return {}
    n = len(dias)
    pesos: dict[date, Decimal] = {}
    total = ZERO
    for i, dia in enumerate(dias):
        x = (Decimal(i) + Decimal("0.5")) / Decimal(n)
        p = _peso(curva, x)
        mes = dia.replace(day=1)
        pesos[mes] = pesos.get(mes, ZERO) + p
        total += p
    meses = sorted(pesos)
    saida: dict[date, Decimal] = {}
    acumulado = ZERO
    for mes in meses[:-1]:
        fatia = (pesos[mes] / total * CEM).quantize(QUATRO, rounding=ROUND_HALF_UP)
        saida[mes] = fatia
        acumulado += fatia
    saida[meses[-1]] = CEM - acumulado
    return saida


# ---------------------------------------------------------------------------
# O que o orçamento sabe de cada etapa
# ---------------------------------------------------------------------------


def _raizes(orcamento: Orcamento) -> tuple[dict[int, int], dict[int, ItemOrcado]]:
    """`({linha: grupo de 1º nível}, {grupo: linha})` da planilha.

    A **etapa do orçamento** é o nó de 1º nível da árvore EAP (`pai` nulo): é o
    que o orçamentista já chama de etapa ("1. Rede de distribuição"), e não
    depende de a obra ter ou não `EtapaObra` cadastrada.
    """
    itens = list(ItemOrcado.objects.filter(orcamento=orcamento).only(
        "item_orcado_id", "pai_id", "ordem", "codigo_eap", "descricao", "etapa_id", "tipo_linha",
    ))
    pais = {i.item_orcado_id: i.pai_id for i in itens}
    raiz_de: dict[int, int] = {}
    for pk in pais:
        atual, visto = pk, set()
        while pais.get(atual) is not None and atual not in visto:
            visto.add(atual)
            atual = pais[atual]
        raiz_de[pk] = atual
    raizes = {i.item_orcado_id: i for i in itens if i.pai_id is None}
    return raiz_de, raizes


def valores_por_etapa(orcamento: Orcamento) -> dict[int, Decimal]:
    """Total com BDI das linhas analíticas, por etapa do orçamento (grupo de 1º nível)."""
    raiz_de, _ = _raizes(orcamento)
    saida: dict[int, Decimal] = {}
    for pk, total in ItemOrcado.objects.filter(
        orcamento=orcamento, tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
    ).values_list("item_orcado_id", "total_com_bdi"):
        grupo = raiz_de.get(pk, pk)
        saida[grupo] = saida.get(grupo, ZERO) + (total or ZERO)
    return saida


def horas_por_etapa(orcamento: Orcamento) -> dict[int, Decimal]:
    """Homem-hora orçado por etapa: `Σ coeficiente × quantidade` dos insumos de
    mão de obra medidos em hora.

    Só existe onde a composição foi aberta (a memória de cálculo do ORC.2). A
    etapa sem composição aberta **não** aparece aqui — e a tela mostra "—", não
    zero: zero diria que a etapa não tem mão de obra.
    """
    raiz_de, _ = _raizes(orcamento)
    linhas = ItemOrcadoInsumo.objects.filter(
        item_orcado__orcamento=orcamento,
        categoria=ItemOrcadoInsumo.Categoria.MAO_DE_OBRA,
        unidade__in=UNIDADES_DE_HORA,
    ).values("item_orcado_id").annotate(
        horas=Coalesce(
            Sum(ExpressionWrapper(
                F("coeficiente") * F("item_orcado__quantidade"),
                output_field=DecimalField(max_digits=24, decimal_places=6),
            )),
            ZERO,
        )
    )
    saida: dict[int, Decimal] = {}
    for linha in linhas:
        grupo = raiz_de.get(linha["item_orcado_id"], linha["item_orcado_id"])
        saida[grupo] = saida.get(grupo, ZERO) + linha["horas"]
    return saida


# ---------------------------------------------------------------------------
# Escrita — planejar, distribuir, copiar
# ---------------------------------------------------------------------------


def _grupo_do_orcamento(orcamento: Orcamento, grupo_id: int) -> ItemOrcado:
    grupo = ItemOrcado.objects.filter(
        pk=grupo_id, orcamento=orcamento, pai__isnull=True,
    ).first()
    if grupo is None:
        raise CronogramaInvalido("Etapa não encontrada neste orçamento.")
    return grupo


def _regerar_parcelas(plano: PlanoEtapa, expediente: Expediente | None = None) -> None:
    if plano.curva == PlanoEtapa.Curva.MANUAL:
        return
    orcamento = plano.orcamento
    expediente = expediente or Expediente(orcamento, plano.inicio, plano.termino)
    dias = expediente.dias(plano.inicio, plano.termino)
    fatias = percentuais_por_mes(dias, plano.curva) or {plano.termino.replace(day=1): CEM}
    ParcelaEtapa.objects.filter(orcamento=orcamento, grupo_id=plano.grupo_id).delete()
    ParcelaEtapa.objects.bulk_create([
        ParcelaEtapa(
            tenant_id=orcamento.tenant_id, orcamento=orcamento, grupo_id=plano.grupo_id,
            competencia=mes, percentual=percentual,
        )
        for mes, percentual in fatias.items()
    ])


@transaction.atomic
def planejar_etapa(orcamento: Orcamento, *, grupo_id: int, inicio: date, termino: date,
                   curva: str = PlanoEtapa.Curva.LINEAR, observacao: str = "") -> PlanoEtapa:
    """Cria ou atualiza a etapa planejada e refaz as células dela."""
    exigir_cronograma_editavel(orcamento)
    if termino < inicio:
        raise CronogramaInvalido("O término é anterior ao início.")
    if curva not in PlanoEtapa.Curva.values:
        raise CronogramaInvalido(f"Curva desconhecida: {curva}.")
    grupo = _grupo_do_orcamento(orcamento, grupo_id)

    plano, _criado = PlanoEtapa.objects.update_or_create(
        orcamento=orcamento, grupo=grupo,
        defaults={
            "tenant_id": orcamento.tenant_id, "inicio": inicio, "termino": termino,
            "curva": curva, "observacao": (observacao or "")[:255],
        },
    )
    _regerar_parcelas(plano)
    recalcular_parcelas(orcamento)
    carimbar(orcamento)
    return plano


@transaction.atomic
def remover_etapa(orcamento: Orcamento, *, grupo_id: int) -> None:
    exigir_cronograma_editavel(orcamento)
    PlanoEtapa.objects.filter(orcamento=orcamento, grupo_id=grupo_id).delete()
    ParcelaEtapa.objects.filter(orcamento=orcamento, grupo_id=grupo_id).delete()
    carimbar(orcamento)


@transaction.atomic
def vincular_etapa_da_obra(orcamento: Orcamento, *, grupo_id: int, etapa_id: int | None) -> None:
    """Liga (ou desliga) a etapa do orçamento a uma `EtapaObra` — **opcional**.

    O cronograma funciona sem isto. O vínculo existe para o orçado casar com o
    aplicado do SIL e com o plano do PDCA, e pode ser feito tanto na planilha
    quanto no cronograma. Vale para o grupo e desce para todas as linhas dele
    (é nelas que o SIL e o financeiro leem a etapa). Não muda custo, então vale
    também com o orçamento aprovado; só orçamento superado ou cancelado é
    história e não aceita.
    """
    from obras.models import EtapaObra

    exigir_cronograma_editavel(orcamento)
    grupo = _grupo_do_orcamento(orcamento, grupo_id)
    if etapa_id is not None:
        if not EtapaObra.objects.filter(
            pk=etapa_id, tenant_id=orcamento.tenant_id, obra_id=orcamento.obra_id,
        ).exists():
            raise CronogramaInvalido("Etapa não encontrada nesta obra.")
    raiz_de, _ = _raizes(orcamento)
    ids = [pk for pk, raiz in raiz_de.items() if raiz == grupo.pk]
    ItemOrcado.objects.filter(pk__in=ids).update(etapa_id=etapa_id)
    carimbar(orcamento)


@transaction.atomic
def planejar_todas(orcamento: Orcamento, *, inicio: date, termino: date,
                   curva: str = PlanoEtapa.Curva.LINEAR, so_sem_plano: bool = False) -> int:
    """O ponto de partida: toda etapa com valor recebe o mesmo período.

    Não inventa sequência — fundação antes de estrutura é decisão de quem
    planeja, e um "sequenciamento automático" aqui seria planejamento que
    ninguém fez. O que ele poupa é a digitação; o ajuste é etapa a etapa.
    """
    exigir_cronograma_editavel(orcamento)
    if termino < inicio:
        raise CronogramaInvalido("O término é anterior ao início.")
    etapas = [g for g, valor in valores_por_etapa(orcamento).items() if valor > 0]
    if so_sem_plano:
        ja = set(PlanoEtapa.objects.filter(orcamento=orcamento).values_list("grupo_id", flat=True))
        etapas = [e for e in etapas if e not in ja]
    expediente = Expediente(orcamento, inicio, termino)
    for grupo_id in etapas:
        plano, _ = PlanoEtapa.objects.update_or_create(
            orcamento=orcamento, grupo_id=grupo_id,
            defaults={"tenant_id": orcamento.tenant_id, "inicio": inicio,
                      "termino": termino, "curva": curva},
        )
        _regerar_parcelas(plano, expediente)
    # A célula "orçamento inteiro" (grupo nulo) é do desenho antigo: o
    # cronograma agora é por etapa, e as duas juntas contariam o valor duas vezes.
    ParcelaEtapa.objects.filter(orcamento=orcamento, grupo__isnull=True).delete()
    recalcular_parcelas(orcamento)
    carimbar(orcamento)
    return len(etapas)


def marcar_manual(orcamento: Orcamento, grupo_id: int | None) -> None:
    """A célula foi editada à mão: a curva daquela etapa deixa de ser recalculada."""
    if grupo_id is None:
        return
    PlanoEtapa.objects.filter(orcamento=orcamento, grupo_id=grupo_id).exclude(
        curva=PlanoEtapa.Curva.MANUAL
    ).update(curva=PlanoEtapa.Curva.MANUAL)
    carimbar(orcamento)


def copiar_cronograma(origem: Orcamento, destino: Orcamento, de_para: dict[int, int]) -> None:
    """A revisão herda o cronograma (decisão do dono: "copia e avisa").

    Copia o plano de cada etapa e as **células** como estavam — inclusive as
    manuais —, e o valor é refeito pelo preço da nova versão. `de_para` é o
    mapa linha-da-origem → linha-do-clone que a cópia da planilha devolve: é
    por ele que o grupo da revisão é o clone do grupo da origem.
    """
    PlanoEtapa.objects.bulk_create([
        PlanoEtapa(
            tenant_id=destino.tenant_id, orcamento=destino, grupo_id=de_para[p.grupo_id],
            inicio=p.inicio, termino=p.termino, curva=p.curva, observacao=p.observacao,
        )
        for p in PlanoEtapa.objects.filter(orcamento=origem) if p.grupo_id in de_para
    ])
    ParcelaEtapa.objects.bulk_create([
        ParcelaEtapa(
            tenant_id=destino.tenant_id, orcamento=destino,
            grupo_id=de_para.get(p.grupo_id) if p.grupo_id else None,
            competencia=p.competencia, percentual=p.percentual, observacao=p.observacao,
        )
        for p in ParcelaEtapa.objects.filter(orcamento=origem)
        if p.grupo_id is None or p.grupo_id in de_para
    ])
    recalcular_parcelas(destino)
    if origem.cronograma_atualizado_em or ParcelaEtapa.objects.filter(orcamento=destino).exists():
        carimbar(destino)


def recalcular_parcelas(orcamento: Orcamento) -> list[ParcelaEtapa]:
    """Converte os percentuais em dinheiro, pelo valor atual de cada etapa.

    Roda também ao fim de `planilha.recalcular_orcamento`: o percentual é o que
    sobrevive a uma mudança de preço, e o valor da célula acompanha o preço.
    """
    por_etapa = valores_por_etapa(orcamento)
    total_geral = orcamento.valor_total
    parcelas = list(ParcelaEtapa.objects.filter(orcamento=orcamento))
    for parcela in parcelas:
        base = total_geral if parcela.grupo_id is None else por_etapa.get(parcela.grupo_id, ZERO)
        parcela.valor_previsto = dinheiro(base * parcela.percentual / CEM)
    if parcelas:
        ParcelaEtapa.objects.bulk_update(parcelas, ["valor_previsto"], batch_size=500)
    return parcelas


# ---------------------------------------------------------------------------
# Leitura — a grade e o quadro das etapas
# ---------------------------------------------------------------------------


def etapas_planejadas(orcamento: Orcamento) -> dict:
    """O quadro que a tela edita e que o PDCA consome: uma linha por etapa.

    Toda etapa com valor no orçamento aparece, planejada ou não — a não
    planejada é exatamente o que falta fazer. Para a planejada: dias úteis do
    período, homem-hora orçado (quando há composição aberta) e a **equipe
    média** que ele implica (`Hh ÷ (dias × horas do dia)`), que só existe com
    expediente da obra — sem jornada declarada, dividir por 8 seria inventar.
    """
    from obras.models import EtapaObra

    valores = valores_por_etapa(orcamento)
    horas = horas_por_etapa(orcamento)
    planos = {p.grupo_id: p for p in PlanoEtapa.objects.filter(orcamento=orcamento)}
    _, raizes = _raizes(orcamento)
    grupos = sorted(
        (raizes[g] for g in set(valores) | set(planos) if g in raizes),
        key=lambda i: (i.ordem, i.codigo_eap, i.item_orcado_id),
    )
    obra_etapas = {
        e.pk: e for e in EtapaObra.objects.filter(
            pk__in={g.etapa_id for g in grupos if g.etapa_id}
        )
    }

    if planos:
        inicio = min(p.inicio for p in planos.values())
        fim = max(p.termino for p in planos.values())
        expediente = Expediente(orcamento, inicio, fim)
    else:
        expediente = None

    linhas = []
    for grupo in grupos:
        plano = planos.get(grupo.pk)
        hh = horas.get(grupo.pk)
        vinculo = obra_etapas.get(grupo.etapa_id) if grupo.etapa_id else None
        dias = len(expediente.dias(plano.inicio, plano.termino)) if plano and expediente else None
        equipe = None
        if hh and dias and expediente and expediente.horas_por_dia:
            equipe = (hh / (Decimal(dias) * expediente.horas_por_dia)).quantize(Decimal("0.1"))
        linhas.append({
            "grupo": grupo.pk,
            "codigo": grupo.codigo_eap,
            # `etapa` é a EtapaObra ligada (opcional): nula = etapa só do orçamento.
            "etapa": vinculo.pk if vinculo else None,
            "etapa_obra_nome": vinculo.nome_etapa if vinculo else None,
            "etapa_nome": grupo.descricao,
            "ordem": grupo.ordem,
            "valor": str(dinheiro(valores.get(grupo.pk, ZERO))),
            "horas_mao_de_obra": str(hh.quantize(Decimal("0.01"))) if hh else None,
            "planejada": plano is not None,
            "inicio": plano.inicio.isoformat() if plano else None,
            "termino": plano.termino.isoformat() if plano else None,
            "curva": plano.curva if plano else None,
            "observacao": plano.observacao if plano else "",
            "dias_uteis": dias,
            "equipe_media": str(equipe) if equipe is not None else None,
        })
    return {
        "etapas": linhas,
        "expediente": expediente.fonte if expediente else None,
        "horas_por_dia": (str(expediente.horas_por_dia)
                          if expediente and expediente.horas_por_dia else None),
        "atualizado_em": orcamento.cronograma_atualizado_em,
        "editavel": orcamento.cronograma_editavel,
    }


def competencias(inicio, fim) -> list:
    """Meses de `inicio` a `fim`, inclusive, sempre no dia 1."""
    if fim < inicio:
        raise CronogramaInvalido("A data final é anterior à inicial.")
    meses, ano, mes = [], inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        meses.append(date(ano, mes, 1))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


def grade(orcamento: Orcamento) -> dict:
    """A grade etapa × mês, pronta para a tela — meses **contínuos**.

    Mês sem desembolso no meio do cronograma aparece como coluna vazia: pular a
    coluna faria agosto encostar em outubro e a curva parecer mais curta.
    """
    parcelas = list(
        ParcelaEtapa.objects.filter(orcamento=orcamento)
        .select_related("grupo")
        .order_by("grupo__ordem", "competencia")
    )
    meses = competencias(min(p.competencia for p in parcelas), max(p.competencia for p in parcelas)) \
        if parcelas else []

    por_etapa: dict = {}
    for parcela in parcelas:
        chave = parcela.grupo_id
        linha = por_etapa.setdefault(chave, {
            "grupo": chave,
            "etapa_nome": parcela.grupo.descricao if parcela.grupo else "— orçamento inteiro —",
            "ordem": parcela.grupo.ordem if parcela.grupo else -1,
            "parcelas": {},
            "total": ZERO,
            "soma_percentual": ZERO,
        })
        linha["parcelas"][parcela.competencia.isoformat()] = {
            "parcela_id": parcela.parcela_id,
            "percentual": str(parcela.percentual),
            "valor_previsto": str(parcela.valor_previsto),
        }
        linha["total"] += parcela.valor_previsto
        linha["soma_percentual"] += parcela.percentual

    total = sum((p.valor_previsto for p in parcelas), ZERO)
    mensal, acumulado = [], ZERO
    for mes in meses:
        valor = sum((p.valor_previsto for p in parcelas if p.competencia == mes), ZERO)
        acumulado += valor
        mensal.append({
            "competencia": mes.isoformat(),
            "valor": str(dinheiro(valor)),
            "acumulado": str(dinheiro(acumulado)),
            "pct_acumulado": (str((acumulado / total * CEM).quantize(Decimal("0.01")))
                              if total > 0 else "0"),
        })

    problemas = [
        {"grupo": l["grupo"], "etapa_nome": l["etapa_nome"],
         "soma_percentual": str(l["soma_percentual"]), "diferenca": str(CEM - l["soma_percentual"])}
        for l in por_etapa.values() if l["soma_percentual"] != CEM
    ]
    return {
        "orcamento": orcamento.pk,
        "competencias": [m.isoformat() for m in meses],
        "linhas": [
            {k: (str(dinheiro(v)) if k == "total" else v) for k, v in linha.items() if k != "soma_percentual"}
            for linha in sorted(por_etapa.values(), key=lambda l: (l["ordem"], l["grupo"] or 0))
        ],
        "mensal": mensal,
        "total": str(dinheiro(total)),
        "validacao": {"consistente": not problemas, "problemas": problemas},
    }


def cronograma(orcamento: Orcamento) -> dict:
    """Tudo o que a página do cronograma lê numa chamada só."""
    return {**grade(orcamento), **etapas_planejadas(orcamento),
            "valor_orcamento": str(orcamento.valor_total)}


# ---------------------------------------------------------------------------
# ORC.7 — desembolso na granularidade do insumo
# ---------------------------------------------------------------------------


def desembolso_por_insumo(orcamento: Orcamento, *, categoria: str | None = None) -> dict:
    """Quanto de **cada insumo** cai em cada mês — o cronograma que o suprimento usa.

    O cronograma por etapa responde ao financeiro ("quanto sai em setembro?") e
    não responde a quem compra ("quantas toneladas de aço preciso ter em obra em
    setembro?"). São perguntas diferentes e a segunda é a que evita tanto a
    parada por falta quanto o pátio cheio de material parado — que é dinheiro
    imobilizado e é o que a curva de desembolso por insumo torna visível.

    **A distribuição é herdada, não inventada.** O insumo cai nas competências da
    **etapa da linha em que ele aparece**, na mesma proporção que o planejador já
    distribuiu em `ParcelaEtapa`. Um insumo que entra em três serviços de duas
    etapas diferentes é rateado por cada uma na proporção do valor que tem lá —
    inventar uma curva própria por insumo seria fabricar planejamento que
    ninguém fez, e o módulo não fabrica dado.

    Linha sem etapa e etapa sem cronograma ficam **fora** da grade e são
    devolvidas em `sem_distribuicao`: somá-las no primeiro mês encheria setembro
    de compra que ninguém planejou para setembro.
    """
    from .models import ItemOrcadoInsumo

    percentuais: dict[int | None, list[tuple]] = {}
    for parcela in ParcelaEtapa.objects.filter(orcamento=orcamento):
        percentuais.setdefault(parcela.grupo_id, []).append(
            (parcela.competencia, parcela.percentual)
        )
    raiz_de, _ = _raizes(orcamento)

    consulta = ItemOrcadoInsumo.objects.filter(item_orcado__orcamento=orcamento)
    if categoria:
        consulta = consulta.filter(categoria=categoria)

    linhas = consulta.values(
        "item_id", "descricao", "unidade", "categoria", "item_orcado_id",
    ).annotate(
        quantidade=Coalesce(
            Sum(ExpressionWrapper(
                F("coeficiente") * F("item_orcado__quantidade"),
                output_field=DecimalField(max_digits=24, decimal_places=6),
            )),
            ZERO,
        ),
        valor=Coalesce(
            Sum(ExpressionWrapper(
                F("custo_no_item") * F("item_orcado__quantidade"),
                output_field=DecimalField(max_digits=24, decimal_places=4),
            )),
            ZERO,
        ),
    )

    grade: dict[tuple, dict] = {}
    sem_distribuicao: dict[tuple, dict] = {}
    competencias: set = set()

    for linha in linhas:
        chave = (linha["item_id"], linha["descricao"], linha["unidade"])
        grupo_id = raiz_de.get(linha["item_orcado_id"])
        fatias = percentuais.get(grupo_id) or percentuais.get(None)

        destino = grade if fatias else sem_distribuicao
        registro = destino.setdefault(chave, {
            "item": linha["item_id"],
            "descricao": linha["descricao"],
            "unidade": linha["unidade"],
            "categoria": linha["categoria"],
            "quantidade_total": ZERO,
            "valor_total": ZERO,
            "meses": {},
        })
        registro["quantidade_total"] += linha["quantidade"]
        registro["valor_total"] += linha["valor"]

        if not fatias:
            continue
        for competencia, percentual in fatias:
            competencias.add(competencia)
            fracao = percentual / CEM
            mes = registro["meses"].setdefault(
                competencia.isoformat(), {"quantidade": ZERO, "valor": ZERO}
            )
            mes["quantidade"] += linha["quantidade"] * fracao
            mes["valor"] += linha["valor"] * fracao

    def formatar(registros: dict) -> list[dict]:
        saida = []
        for registro in sorted(registros.values(), key=lambda r: r["valor_total"], reverse=True):
            saida.append({
                **registro,
                "quantidade_total": str(registro["quantidade_total"].quantize(Decimal("0.0001"))),
                "valor_total": str(dinheiro(registro["valor_total"])),
                "meses": {
                    mes: {
                        "quantidade": str(v["quantidade"].quantize(Decimal("0.0001"))),
                        "valor": str(dinheiro(v["valor"])),
                    }
                    for mes, v in sorted(registro["meses"].items())
                },
            })
        return saida

    return {
        "orcamento": orcamento.pk,
        "filtro_categoria": categoria or "",
        "competencias": sorted(mes.isoformat() for mes in competencias),
        "insumos": formatar(grade),
        "sem_distribuicao": formatar(sem_distribuicao),
        "nota_sem_distribuicao": (
            "Insumos de linhas cuja etapa não tem cronograma distribuído. Ficam fora "
            "da grade de propósito — jogá-los no primeiro mês fabricaria compra que "
            "ninguém planejou."
        ) if sem_distribuicao else "",
    }
