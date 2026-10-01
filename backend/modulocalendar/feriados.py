# backend/modulocalendar/feriados.py
"""Os feriados de um ano qualquer, de 1900 a 2100 — o que a tabela não guarda.

**O defeito (item 55 do dono, revisão de 01/10/2026).** A tabela `Feriado`
cobria 2025–2028. A 46ª parcela de um contrato vencia em 01/01/2030; o ajuste
perguntou à tabela, a tabela não tinha 2030, e o boleto saiu no dia da
Confraternização Universal — sem aviso nenhum, porque `base_sincronizada()` só
sabia dizer se a tabela tinha *alguma* linha.

**A decisão do dono:** os feriados batem de 1900 a 2100. Três camadas:

1. **Lei (nacional e estadual)** — o `sincronizar_feriados` grava a faixa
   inteira. Se mesmo assim um ano faltar na tabela (base nunca sincronizada,
   restauração parcial), este módulo calcula pelo `python-holidays` na hora, em
   vez de responder "dia útil" por não saber.
2. **Município** — o dataset público só tem alguns anos. Nos outros, o feriado
   é **projetado pela regra** que os anos publicados mostram: data que se
   repete de um ano para o outro é fixa (aniversário da cidade, padroeiro);
   data que anda junto com a Páscoa é móvel (Corpus Christi, Carnaval). O que
   foi projetado vem marcado, e a tela pode dizer isso.
3. **Banco** — o dia útil **bancário** não é o feriado de lei: Carnaval
   (segunda e terça) e Corpus Christi não são feriado nacional, mas não têm
   expediente bancário (calendário ANBIMA). Só o vencimento usa esta camada; o
   PDCA ("a equipe trabalha?") continua só com a lei.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import holidays
from dateutil.easter import easter

#: Calendário ANBIMA: o que a rede bancária fecha além do feriado de lei. Os
#: nomes são os da categoria `optional` do `python-holidays` para o Brasil.
SEM_EXPEDIENTE_BANCARIO = frozenset({"Carnaval", "Corpus Christi"})

#: Nome que denuncia feriado móvel quando o dataset só tem um ano dele — sem
#: dois anos não dá para ver se a data andou com a Páscoa.
_NOMES_PASCOAIS = ("corpus christi", "carnaval", "paixão", "sexta-feira santa", "páscoa", "cinzas")


@dataclass(frozen=True)
class Regra:
    """Como um feriado municipal cai num ano qualquer."""

    nome: str
    mes: int = 0
    dia: int = 0
    desde_pascoa: int | None = None  # dias a partir do domingo de Páscoa

    def no_ano(self, ano: int) -> date | None:
        if self.desde_pascoa is not None:
            return easter(ano) + timedelta(days=self.desde_pascoa)
        try:
            return date(ano, self.mes, self.dia)
        except ValueError:  # 29/02 em ano não bissexto
            return None


def _eh_pascoal(nome: str) -> bool:
    nome = nome.lower()
    return any(p in nome for p in _NOMES_PASCOAIS)


def regras_municipais(ocorrencias: list[tuple[date, str]]) -> set[Regra]:
    """As regras que as datas publicadas de **um** município mostram.

    Decide linha a linha, e não pelo nome: o dataset chama muitos feriados só de
    "Feriado Municipal", e um município pode ter quatro deles. Uma data vira
    regra fixa quando o mesmo dia/mês aparece em dois anos; vira regra móvel
    quando a mesma distância da Páscoa aparece em dois anos. Visto em um ano
    só, decide o nome (Corpus Christi é móvel; o resto, fixo).
    """
    anos_fixo: dict[tuple, set[int]] = defaultdict(set)
    anos_pascoa: dict[tuple, set[int]] = defaultdict(set)
    for dia, nome in ocorrencias:
        anos_fixo[(nome, dia.month, dia.day)].add(dia.year)
        anos_pascoa[(nome, (dia - easter(dia.year)).days)].add(dia.year)

    regras = set()
    for dia, nome in ocorrencias:
        fixo = (nome, dia.month, dia.day)
        movel = (nome, (dia - easter(dia.year)).days)
        if len(anos_fixo[fixo]) >= 2:
            regras.add(Regra(nome, mes=dia.month, dia=dia.day))
        elif len(anos_pascoa[movel]) >= 2 or _eh_pascoal(nome):
            regras.add(Regra(nome, desde_pascoa=movel[1]))
        else:
            regras.add(Regra(nome, mes=dia.month, dia=dia.day))
    return regras


@lru_cache(maxsize=512)
def de_lei(ano: int, uf: str = "") -> dict[date, str]:
    """Nacional + estadual do ano, calculados (sem banco). Puro e memoizado."""
    nacional = dict(holidays.Brazil(years=ano).items())
    if uf and uf in holidays.Brazil.subdivisions:
        for dia, nome in holidays.Brazil(subdiv=uf, years=ano).items():
            nacional.setdefault(dia, nome)
    return nacional


@lru_cache(maxsize=256)
def sem_expediente_bancario(ano: int) -> dict[date, str]:
    """Carnaval (segunda e terça) e Corpus Christi do ano."""
    opcionais = holidays.Brazil(years=ano, categories=("optional",))
    return {dia: nome for dia, nome in opcionais.items() if nome in SEM_EXPEDIENTE_BANCARIO}


class FeriadosMunicipais:
    """Os feriados de um município, publicados ou projetados, ano a ano.

    Uma consulta ao banco por município (a vida do objeto é a de um ajuste —
    um carnê, uma prévia), e a projeção só para os anos que o dataset não tem.
    """

    def __init__(self, ibge: str):
        self.ibge = ibge or ""
        self._publicados: dict[int, dict[date, str]] | None = None
        self._regras: set[Regra] = set()
        self.projetados: set[int] = set()

    def _carregar(self) -> None:
        if self._publicados is not None:
            return
        self._publicados = defaultdict(dict)
        if not self.ibge:
            return
        from .models import Feriado

        ocorrencias = list(
            Feriado.objects.filter(escopo="municipal", ibge=self.ibge).values_list("data", "nome")
        )
        for dia, nome in ocorrencias:
            self._publicados[dia.year][dia] = nome
        self._regras = regras_municipais(ocorrencias)

    def do_ano(self, ano: int) -> dict[date, str]:
        self._carregar()
        if ano in self._publicados:
            return dict(self._publicados[ano])
        if not self._regras:
            return {}
        self.projetados.add(ano)
        saida = {}
        for regra in self._regras:
            dia = regra.no_ano(ano)
            if dia is not None:
                saida.setdefault(dia, regra.nome)
        return saida
