"""iCalendar (`.ics`, RFC 5545) — a agenda que entra e sai do SGI (Fatia E).

Só o pedaço da norma que um calendário de mercado troca de verdade: `VEVENT`
com `UID`, `SUMMARY`, `DESCRIPTION`, `LOCATION`, `DTSTART`/`DTEND` (data, hora
UTC, hora local com `TZID` ou flutuante) e `RRULE`/`EXDATE`. Sem biblioteca nova:
o `dateutil` (já usado na recorrência) resolve fuso e data.

**Escrever** sai sempre em UTC (`...Z`), o que qualquer leitor entende sem
`VTIMEZONE`. **Ler** é tolerante com o que o Google e o Outlook mandam: linhas
dobradas, parâmetros, `\\n` escapado; o que não se entende vira erro **com a
linha do evento**, e quem decide recusar o arquivo inteiro é a view (tudo ou nada).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from dateutil import tz
from django.utils import timezone

PRODID = "-//SGI//Calendario//PT-BR"


# --------------------------------------------------------------------- escrever
def _escapar(texto: str) -> str:
    return (
        (texto or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _dobrar(linha: str) -> list[str]:
    """Dobra a linha em 75 octetos (RFC 5545 §3.1), sem partir caractere UTF-8."""
    partes, atual, tamanho = [], "", 0
    for ch in linha:
        n = len(ch.encode("utf-8"))
        limite = 75 if not partes else 74  # a continuação começa com um espaço
        if tamanho + n > limite:
            partes.append(atual)
            atual, tamanho = "", 0
        atual += ch
        tamanho += n
    partes.append(atual)
    return [partes[0]] + [" " + p for p in partes[1:]]


def _utc(dt: datetime) -> str:
    return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _data_local(dt: datetime) -> date:
    return timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()


def escrever(eventos, dominio: str = "sgi") -> str:
    """Os `CalendarEvent` como um `VCALENDAR`. Overrides de série saem como
    eventos próprios (com o UID do mestre e `RECURRENCE-ID`)."""
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN"]
    agora = _utc(timezone.now())
    for ev in eventos:
        uid = ev.ical_uid or f"sgi-{ev.pk}@{dominio}"
        if ev.recurrence_master_id:
            mestre = ev.recurrence_master
            uid = mestre.ical_uid or f"sgi-{mestre.pk}@{dominio}"
        corpo = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{agora}"]
        if ev.all_day:
            ini = _data_local(ev.start_time)
            fim = _data_local(ev.end_time)
            if fim <= ini:
                fim = ini + timedelta(days=1)
            corpo += [f"DTSTART;VALUE=DATE:{ini:%Y%m%d}", f"DTEND;VALUE=DATE:{fim:%Y%m%d}"]
        else:
            corpo += [f"DTSTART:{_utc(ev.start_time)}", f"DTEND:{_utc(ev.end_time)}"]
        if ev.recurrence_master_id and ev.original_start:
            corpo.append(f"RECURRENCE-ID:{_utc(ev.original_start)}")
        corpo.append(f"SUMMARY:{_escapar(ev.title)}")
        if ev.description:
            corpo.append(f"DESCRIPTION:{_escapar(ev.description)}")
        if ev.location:
            corpo.append(f"LOCATION:{_escapar(ev.location)}")
        if ev.recurrence_rule:
            corpo.append(f"RRULE:{ev.recurrence_rule}")
            for iso in ev.excluded_dates_list():
                try:
                    corpo.append(f"EXDATE:{_utc(datetime.fromisoformat(iso))}")
                except ValueError:
                    continue
        corpo.append("END:VEVENT")
        linhas += corpo
    linhas.append("END:VCALENDAR")
    saida = []
    for linha in linhas:
        saida += _dobrar(linha)
    return "\r\n".join(saida) + "\r\n"


# ------------------------------------------------------------------------- ler
@dataclass
class EventoLido:
    linha: int
    uid: str = ""
    titulo: str = ""
    descricao: str = ""
    local: str = ""
    inicio: datetime | None = None
    fim: datetime | None = None
    dia_inteiro: bool = False
    regra: str = ""
    excluidas: list[datetime] = field(default_factory=list)
    #: `RECURRENCE-ID`: esta é a exceção de uma ocorrência da série de mesmo UID.
    recorrencia_de: datetime | None = None


class IcsInvalido(ValueError):
    """O arquivo não é um iCalendar que se possa ler."""


def _desdobrar(texto: str) -> list[tuple[int, str]]:
    """Junta as linhas dobradas e devolve (nº da linha original, conteúdo)."""
    saida: list[tuple[int, str]] = []
    for n, linha in enumerate(texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        if linha.startswith((" ", "\t")) and saida:
            num, anterior = saida[-1]
            saida[-1] = (num, anterior + linha[1:])
        elif linha:
            saida.append((n, linha))
    return saida


def _desescapar(valor: str) -> str:
    saida, i = [], 0
    while i < len(valor):
        ch = valor[i]
        if ch == "\\" and i + 1 < len(valor):
            prox = valor[i + 1]
            saida.append("\n" if prox in "nN" else prox)
            i += 2
            continue
        saida.append(ch)
        i += 1
    return "".join(saida)


def _partir(linha: str) -> tuple[str, dict[str, str], str]:
    """`NOME;P1=a;P2=b:valor` → (NOME, {P1: a, P2: b}, valor). Respeita aspas."""
    em_aspas, corte = False, -1
    for i, ch in enumerate(linha):
        if ch == '"':
            em_aspas = not em_aspas
        elif ch == ":" and not em_aspas:
            corte = i
            break
    if corte < 0:
        raise ValueError("linha sem ':'")
    cabeca, valor = linha[:corte], linha[corte + 1:]
    pedacos = cabeca.split(";")
    params = {}
    for p in pedacos[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return pedacos[0].upper(), params, valor


def _data_hora(valor: str, params: dict[str, str]) -> tuple[datetime, bool]:
    """Valor de `DTSTART`/`DTEND`/`EXDATE` → (datetime consciente, é só data)."""
    valor = valor.strip()
    if params.get("VALUE", "").upper() == "DATE" or (len(valor) == 8 and valor.isdigit()):
        d = datetime.strptime(valor[:8], "%Y%m%d").date()
        return timezone.make_aware(datetime.combine(d, time.min)), True
    if valor.endswith("Z"):
        return datetime.strptime(valor[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=dt_timezone.utc), False
    ingenuo = datetime.strptime(valor[:15], "%Y%m%dT%H%M%S")
    fuso = tz.gettz(params["TZID"]) if params.get("TZID") else None
    if fuso is not None:
        return ingenuo.replace(tzinfo=fuso), False
    return timezone.make_aware(ingenuo), False  # hora flutuante: a do servidor


def ler(texto: str) -> tuple[list[EventoLido], list[str]]:
    """Os `VEVENT` do arquivo e os erros (um por evento ilegível, com a linha)."""
    linhas = _desdobrar(texto)
    if not linhas or linhas[0][1].strip().upper() != "BEGIN:VCALENDAR":
        raise IcsInvalido("O arquivo não é um calendário .ics (falta BEGIN:VCALENDAR).")

    eventos: list[EventoLido] = []
    erros: list[str] = []
    atual: EventoLido | None = None
    profundidade = 0  # VALARM e afins dentro do VEVENT são ignorados
    falhou = False

    for num, linha in linhas:
        maiuscula = linha.strip().upper()
        if maiuscula == "BEGIN:VEVENT":
            atual, profundidade, falhou = EventoLido(linha=num), 0, False
            continue
        if atual is None:
            continue
        if maiuscula.startswith("BEGIN:"):
            profundidade += 1
            continue
        if maiuscula.startswith("END:") and maiuscula != "END:VEVENT":
            profundidade = max(profundidade - 1, 0)
            continue
        if maiuscula == "END:VEVENT":
            if not falhou:
                problema = _conferir(atual)
                if problema:
                    erros.append(f"Evento da linha {atual.linha}: {problema}")
                else:
                    eventos.append(atual)
            atual = None
            continue
        if profundidade or falhou:
            continue
        try:
            nome, params, valor = _partir(linha)
            if nome == "UID":
                atual.uid = valor.strip()[:255]
            elif nome == "SUMMARY":
                atual.titulo = _desescapar(valor).strip()
            elif nome == "DESCRIPTION":
                atual.descricao = _desescapar(valor)
            elif nome == "LOCATION":
                atual.local = _desescapar(valor).strip()[:255]
            elif nome == "DTSTART":
                atual.inicio, atual.dia_inteiro = _data_hora(valor, params)
            elif nome == "DTEND":
                atual.fim, _ = _data_hora(valor, params)
            elif nome == "DURATION":
                atual.fim = None if atual.inicio is None else atual.inicio + _duracao(valor)
            elif nome == "RRULE":
                atual.regra = valor.strip()[:255]
            elif nome == "EXDATE":
                for parte in valor.split(","):
                    atual.excluidas.append(_data_hora(parte, params)[0])
            elif nome == "RECURRENCE-ID":
                atual.recorrencia_de, _ = _data_hora(valor, params)
        except (ValueError, KeyError) as exc:
            erros.append(f"Evento da linha {atual.linha}: não entendi '{linha[:60]}' ({exc}).")
            falhou = True
    return eventos, erros


def _duracao(valor: str) -> timedelta:
    """`DURATION` simples (P1D, PT1H30M, P1W)."""
    import re

    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", valor.strip())
    if not m:
        raise ValueError("DURATION inválida")
    sinal, w, d, h, mi, s = m.groups()
    delta = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0),
                      minutes=int(mi or 0), seconds=int(s or 0))
    return -delta if sinal == "-" else delta


def _conferir(ev: EventoLido) -> str:
    if ev.inicio is None:
        return "sem data de início (DTSTART)."
    if not ev.titulo:
        ev.titulo = "(sem título)"
    if ev.fim is None:
        ev.fim = ev.inicio + (timedelta(days=1) if ev.dia_inteiro else timedelta(hours=1))
    if ev.fim < ev.inicio:
        return "termina antes de começar."
    if ev.regra:
        if "DTSTART" in ev.regra.upper():
            return "regra de repetição com DTSTART embutido."
        if ev.recorrencia_de is not None:
            return "exceção de série (RECURRENCE-ID) com regra de repetição própria."
        try:
            from .recurrence import _rule_from
            next(iter(_rule_from(ev.regra, ev.inicio)), None)
        except (ValueError, TypeError) as exc:
            return f"regra de repetição que não se lê ({exc})."
    if ev.recorrencia_de is not None and not ev.uid:
        return "exceção de série sem UID — não há como saber de qual série é."
    return ""
