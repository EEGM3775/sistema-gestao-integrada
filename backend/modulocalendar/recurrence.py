# backend/modulocalendar/recurrence.py
"""Expansão de ocorrências recorrentes (Fatia B).

As ocorrências de um evento-mestre são **virtuais**: nunca gravadas, apenas
expandidas no feed do período a partir da `recurrence_rule` (RRULE do RFC 5545),
ancorada em `start_time`. Uma exceção ("editar/excluir só esta") vira ou uma
`EXDATE` em `excluded_dates`, ou um evento de *override* apontando para o mestre.
"""
from datetime import datetime, timezone

from dateutil.rrule import rrulestr
from django.utils.dateparse import parse_datetime


def parse_iso(value):
    """String ISO 8601 → datetime (aware quando há offset). Tolerante a 'Z'."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    parsed = parse_datetime(value)
    if parsed is not None:
        return parsed
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def _rule(master):
    """`rrule` ancorada no `start_time`, aceitando a regra com ou sem prefixo."""
    text = master.recurrence_rule.strip()
    if not text:
        return None
    if not text.upper().startswith('RRULE'):
        text = f'RRULE:{text}'
    return rrulestr(text, dtstart=master.start_time)


def expand_occurrences(master, window_start, window_end):
    """Ocorrências (start, end) do mestre que **intersectam** [window_start,
    window_end], já descontadas as `excluded_dates` e as datas com override.

    O `after` recua pela duração do evento para não perder uma ocorrência que
    começa antes da janela mas termina dentro dela.
    """
    rule = _rule(master)
    if rule is None or window_start is None or window_end is None:
        return []

    duration = master.end_time - master.start_time
    starts = rule.between(window_start - duration, window_end, inc=True)

    skip = {parse_iso(d) for d in master.excluded_dates_list()}
    skip |= {
        ov.original_start
        for ov in master.overrides.all()
        if ov.original_start is not None
    }
    skip.discard(None)

    return [(occ, occ + duration) for occ in starts if occ not in skip]


def rule_parts(rule_str):
    """RRULE (com ou sem prefixo) → dict {CHAVE: valor}, preservando ordem."""
    parts = {}
    text = rule_str.strip()
    if text.upper().startswith('RRULE:'):
        text = text.split(':', 1)[1]
    for token in text.split(';'):
        if '=' in token:
            key, value = token.split('=', 1)
            parts[key.upper()] = value
    return parts


def build_rule(parts):
    return ';'.join(f'{key}={value}' for key, value in parts.items() if value != '')


def truncate_rule_until(rule_str, until_dt):
    """Regra com `UNTIL` = until_dt (em UTC, exigido quando o DTSTART é aware),
    removendo `COUNT` (excludente com UNTIL) — usado ao dividir/truncar a série."""
    parts = rule_parts(rule_str)
    parts.pop('COUNT', None)
    parts['UNTIL'] = until_dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return build_rule(parts)


def split_rule_for_future(rule_str, dtstart, boundary):
    """Regra da série NOVA ao dividir "desta em diante". Se a original tem
    `COUNT`, desconta as ocorrências já consumidas antes de `boundary` (senão o
    novo mestre reiniciaria a contagem); regras por `UNTIL` seguem inalteradas."""
    parts = rule_parts(rule_str)
    if 'COUNT' not in parts:
        return build_rule(parts)
    total = int(parts['COUNT'])
    consumidas = sum(1 for occ in _rule_from(rule_str, dtstart) if occ < boundary)
    parts['COUNT'] = str(max(total - consumidas, 1))
    return build_rule(parts)


def _rule_from(rule_str, dtstart):
    text = rule_str.strip()
    if not text.upper().startswith('RRULE'):
        text = f'RRULE:{text}'
    return rrulestr(text, dtstart=dtstart)
