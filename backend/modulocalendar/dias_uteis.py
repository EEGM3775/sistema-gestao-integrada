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

**A base nasce vazia.** Quem a enche é `manage.py sincronizar_feriados`. Sem ela
o cálculo continua certo para fim de semana e simplesmente não conhece feriado —
por isso `base_sincronizada()` existe e as telas que dependem disso a exibem, em
vez de prometer um ajuste que não aconteceu.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q

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


def base_sincronizada() -> bool:
    """A tabela global de feriados foi populada alguma vez?

    Quem responde "não" deve dizê-lo na tela: um vencimento "ajustado" sem base
    de feriados só desviou de sábado e domingo, e parecer mais do que é seria o
    pior dos dois mundos.
    """
    return Feriado.objects.exists()


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

    def __init__(self, *, uf: str = "", ibge: str = "", ativo: bool = True):
        self.uf = (uf or "").upper()[:2]
        self.ibge = ibge or ""
        self.ativo = ativo
        self._feriados: dict[date, str] = {}
        self._anos_carregados: set[int] = set()

    # -- consulta ------------------------------------------------------------
    def _garantir(self, dia: date) -> None:
        # Carrega o ano inteiro de uma vez. O ajuste de 31/12 pode cair em
        # janeiro, então o ano seguinte entra junto — senão o 1º de janeiro
        # passaria despercebido exatamente na virada.
        for ano in (dia.year, dia.year + 1):
            if ano in self._anos_carregados:
                continue
            self._feriados.update(
                feriados_entre(date(ano, 1, 1), date(ano, 12, 31), uf=self.uf, ibge=self.ibge)
            )
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
