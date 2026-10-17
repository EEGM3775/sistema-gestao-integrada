"""Quem vê e quem mexe — as regras de acesso das agendas e eventos (Fatia D).

Um lugar só para as três perguntas, porque o feed, o CRUD, as actions de
recorrência e o despacho de lembretes precisam da mesma resposta:

- **ver uma agenda**: o dono; os membros, se é de equipe; todos, se é da empresa;
- **ver um evento**: o dono dele, quem vê a agenda dele, ou quem foi convidado;
- **editar um evento**: o dono dele ou quem pode lançar na agenda dele. Ver uma
  agenda é poder lançar nela — a de equipe é da equipe. O convidado que não vê a
  agenda só **responde** ao convite.

A RLS já fecha o tenant; aqui é só o recorte dentro da empresa.
"""
from django.db.models import Q

from .models import Calendar, CalendarEvent


def agendas_visiveis(user):
    """As agendas que `user` vê (e em que pode lançar)."""
    return Calendar.objects.filter(
        Q(owner=user)
        | Q(scope=Calendar.Scope.EQUIPE, members__user=user)
        | Q(scope=Calendar.Scope.EMPRESA)
    ).distinct()


def ve_agenda(user, calendar) -> bool:
    if calendar.owner_id == user.pk or calendar.scope == Calendar.Scope.EMPRESA:
        return True
    if calendar.scope == Calendar.Scope.EQUIPE:
        return calendar.members.filter(user=user).exists()
    return False


def eventos_visiveis(user):
    """Os eventos que `user` vê: os dele, os das agendas que vê e os convites."""
    return CalendarEvent.objects.filter(
        Q(user=user)
        | Q(calendar__in=agendas_visiveis(user))
        | Q(attendees__user=user)
    ).distinct()


def pode_editar_evento(user, event) -> bool:
    if event.user_id == user.pk:
        return True
    return event.calendar_id is not None and ve_agenda(user, event.calendar)


def gere_agenda(user, calendar) -> bool:
    """Renomear, recolorir, mudar membros ou apagar: só o dono (ou o admin da
    empresa — quem decide é o `nucleo.autorizacao`, nunca a claim lida aqui)."""
    from nucleo import autorizacao

    return calendar.owner_id == user.pk or autorizacao.administra(user)


def interessados_da_agenda(calendar):
    """Ids de quem enxerga a agenda; `None` quando é da empresa (todos)."""
    if calendar.scope == Calendar.Scope.EMPRESA:
        return None
    ids = {calendar.owner_id}
    if calendar.scope == Calendar.Scope.EQUIPE:
        ids.update(calendar.members.values_list('user_id', flat=True))
    return ids


def interessados(event):
    """Ids de quem enxerga o evento — para limpar o cache do feed de cada um.
    `None` quando a agenda é da empresa (todos enxergam)."""
    ids = {event.user_id}
    ids.update(event.attendees.values_list('user_id', flat=True))
    if event.calendar_id is not None:
        da_agenda = interessados_da_agenda(event.calendar)
        if da_agenda is None:
            return None
        ids |= da_agenda
    return ids
