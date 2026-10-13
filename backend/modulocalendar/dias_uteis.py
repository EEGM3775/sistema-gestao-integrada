# backend/modulocalendar/dias_uteis.py
"""Dia útil **bancário** — a régua do vencimento que vai ao boleto.

Mora aqui, e não no `modulopdca`, porque as duas perguntas só parecem a mesma.
O PDCA pergunta *"a equipe trabalha neste dia?"*, e a resposta depende do
`CalendarioTrabalho` da obra (mutirão de sábado, recesso, turno de domingo).
O financeiro pergunta *"o banco compensa neste dia?"*, e a resposta não tem
calendário de obra nenhum: é sábado, domingo e feriado — nacional, estadual e
municipal do lugar onde o imóvel está.

Misturar os dois seria dizer que a obra que trabalha aos sábados também recebe
boleto aos sábados. Não recebe: quem define o dia de compensação é a rede
bancária, não o canteiro.

**Localidade.** Nacional sempre; estadual só com a UF; municipal só com o código
IBGE. Afirmar feriado municipal sem saber o município seria inventar dia parado —
a mesma régua de dado honesto de `modulopdca.services.feriados_do_periodo`, de
onde este módulo herda a consulta.

**De 1900 a 2100, com ou sem a tabela** *(decisão do dono, 01/10/2026)*. A tabela
`Feriado` é a fonte (o `sincronizar_feriados` grava a faixa inteira), mas um
ano que falte nela não vira "dia útil por não saber": a lei daquele ano é
calculada na hora, o feriado do município é projetado pela regra dos anos que
o dataset publica, e o Carnaval e o Corpus Christi entram como dias sem
expediente bancário. Ver `modulocalendar.feriados`.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q

from . import feriados as _feriados
from .models import Feriado

#: Guarda-corpo do laço que anda um dia por vez — **não é teto de produto**
#: (§5.6 do `payment/planos.py`), é o mesmo guarda-corpo de
#: `modulopdca.services._MAXIMO_DIAS_CAMINHADOS`. Nenhuma sequência real de
#: sábado + domingo + feriado passa de uma semana; 30 dias é folga absurda e
#: curta o bastante para um erro aparecer como erro.
_MAXIMO_DIAS_CAMINHADOS = 30


def feriados_entre(inicio: date, fim: date, *, uf: str = "", ibge: str = "") -> dict[date, str]:
    """`{data: nome}` no período, na localidade informada.

    Uma consulta cobre o intervalo inteiro: ajustar um carnê de 360 parcelas não
    pode virar 360 idas ao banco.
    """
    escopo = Q(escopo="nacional")
    if uf:
        escopo |= Q(escopo="estadual", uf=uf.upper()[:2])
    if ibge:
        escopo |= Q(escopo="municipal", ibge=ibge)
    return {
        f.data: f.nome
        for f in Feriado.objects.filter(escopo, data__gte=inicio, data__lte=fim)
    }


def feriados_da_localidade(inicio: date, fim: date, *, uf: str = "", ibge: str = "") -> dict[date, str]:
    """Os feriados **de lei e do município** no período — os mesmos que a Agenda
    mostra, com ou sem a tabela sincronizada.

    É a resposta para *"a equipe trabalha neste dia?"*: sem o calendário
    bancário (Carnaval e Corpus Christi só entram se forem lei no lugar). A lei
    vem da tabela ou, faltando o ano, do cálculo; o município vem do dataset ou
    da projeção pela regra dos anos publicados — a mesma régua do vencimento.
    """
    uf = (uf or "").upper()[:2]
    municipais = _feriados.FeriadosMunicipais(ibge)
    saida: dict[date, str] = {}
    for ano in range(inicio.year, fim.year + 1):
        lei = _lei_na_tabela(ano, uf)
        if lei is None:
            lei = _feriados.de_lei(ano, uf)
        do_ano = dict(municipais.do_ano(ano))
        do_ano.update(lei)  # a lei dá o nome quando os dois caem no mesmo dia
        saida.update({dia: nome for dia, nome in do_ano.items() if inicio <= dia <= fim})
    return saida


def base_sincronizada() -> bool:
    """O ajuste conhece os feriados? **Sempre, desde 01/10/2026.**

    Era a pergunta "a tabela tem alguma linha?", e ela respondia sim com a
    tabela cobrindo só 2025–2028 — o boleto de 2030 saiu num feriado sem aviso.
    Hoje um ano ausente da tabela é calculado (lei) ou projetado (município), e
    o que foi projetado o ajuste diz em `municipal_projetado`. A função fica
    porque as telas ainda leem o campo; a ressalva delas deixou de ter caso.
    """
    return True


def _lei_na_tabela(ano: int, uf: str) -> dict[date, str] | None:
    """Nacional + estadual do ano pela tabela, ou `None` se o ano não está nela.

    Ano sem nenhum feriado nacional é ano não sincronizado: não existe
    calendário brasileiro sem 1º de janeiro.
    """
    escopo = Q(escopo="nacional")
    if uf:
        escopo |= Q(escopo="estadual", uf=uf)
    linhas = list(
        Feriado.objects.filter(escopo, data__year=ano).values_list("data", "nome", "escopo")
    )
    if not any(e == "nacional" for _, _, e in linhas):
        return None
    return {dia: nome for dia, nome, _ in linhas}


class AjusteDeVencimento:
    """Empurra o vencimento para o próximo dia útil — com os feriados em memória.

    É objeto, e não função solta, porque o carnê pede o ajuste centenas de vezes
    dentro do mesmo intervalo: carregar os feriados uma vez por ano tocado
    transforma N consultas em uma por ano. É também o que permite injetá-lo em
    `clientes.plano_pagamento.montar()` sem que o motor de cálculo — que é puro —
    passe a conhecer o banco.

    `ativo=False` devolve a data intacta: é o caminho de quem não quer ajuste
    (simulação de contrato antigo, teste do cálculo puro) sem um `if` em cada
    chamador.
    """

    def __init__(self, *, uf: str = "", ibge: str = "", ativo: bool = True, bancario: bool = False):
        self.uf = (uf or "").upper()[:2]
        self.ibge = ibge or ""
        self.ativo = ativo
        # Carnaval e Corpus Christi: sem expediente bancário, mas não feriado de
        # lei. Vencimento de título liga; prazo legal (CAT) não.
        self.bancario = bancario
        self._feriados: dict[date, str] = {}
        self._anos_carregados: set[int] = set()
        self._municipais = _feriados.FeriadosMunicipais(self.ibge)
        self.anos_calculados: set[int] = set()  # a lei veio do cálculo, não da tabela
        self._datas_projetadas: set[date] = set()
        self.municipal_projetado = False  # um feriado municipal deduzido decidiu alguma data

    # -- consulta ------------------------------------------------------------
    def _garantir(self, dia: date) -> None:
        # Carrega o ano inteiro de uma vez. O ajuste de 31/12 pode cair em
        # janeiro, então o ano seguinte entra junto — senão o 1º de janeiro
        # passaria despercebido exatamente na virada.
        for ano in (dia.year, dia.year + 1):
            if ano in self._anos_carregados:
                continue
            lei = _lei_na_tabela(ano, self.uf)
            if lei is None:
                lei = _feriados.de_lei(ano, self.uf)
                self.anos_calculados.add(ano)
            # A ordem decide o nome quando dois caem no mesmo dia: a lei fala
            # primeiro, depois o município, por fim o calendário do banco.
            do_ano = dict(_feriados.sem_expediente_bancario(ano)) if self.bancario else {}
            municipais = self._municipais.do_ano(ano)
            do_ano.update(municipais)
            if ano in self._municipais.projetados:
                self._datas_projetadas.update(d for d in municipais if d not in lei)
            do_ano.update(lei)
            self._feriados.update(do_ano)
            self._anos_carregados.add(ano)

    def motivo(self, dia: date) -> str:
        """Por que este dia não é útil — "sábado", "domingo" ou o nome do feriado.

        String vazia significa dia útil. É o texto que a tela mostra ao lado da
        data ajustada: "23/11 era domingo" explica; "ajustado" não.
        """
        if dia.weekday() == 5:
            return "sábado"
        if dia.weekday() == 6:
            return "domingo"
        self._garantir(dia)
        if dia in self._datas_projetadas:
            self.municipal_projetado = True
        return self._feriados.get(dia, "")

    def eh_dia_util(self, dia: date) -> bool:
        return not self.motivo(dia)

    # -- ajuste --------------------------------------------------------------
    def __call__(self, dia: date | None) -> date | None:
        """O próprio dia, se já for útil; senão o primeiro seguinte que for.

        **Sempre para a frente.** Antecipar o vencimento cobraria o comprador
        antes do combinado; adiar é o que o contrato e a rede bancária fazem.
        """
        if dia is None or not self.ativo:
            return dia
        caminhados = 0
        while not self.eh_dia_util(dia):
            dia += timedelta(days=1)
            caminhados += 1
            if caminhados > _MAXIMO_DIAS_CAMINHADOS:
                # Sequência impossível na vida real: devolve o que tem em vez de
                # girar para sempre. Ver `_MAXIMO_DIAS_CAMINHADOS`.
                return dia
        return dia

    def explicar(self, dia: date | None) -> tuple[date | None, str]:
        """`(data_ajustada, motivo_do_original)` — para a tela dizer o porquê."""
        if dia is None or not self.ativo:
            return dia, ""
        motivo = self.motivo(dia)
        return (self(dia), motivo) if motivo else (dia, "")


#: O ajuste que não ajusta. Poupa o `if ajustar is None` de cada chamador.
SEM_AJUSTE = AjusteDeVencimento(ativo=False)
