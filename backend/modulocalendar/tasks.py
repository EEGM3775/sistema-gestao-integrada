# backend/modulocalendar/tasks.py
"""Tarefas periódicas do calendário.

- `sincronizar_feriados_task` (Fatia F): re-sincroniza o dataset de feriados.
  Semanal no beat e, num banco que nunca sincronizou, também quando o beat sobe
  (`_feriados_no_boot`) — o intervalo de 7 dias só dispara a primeira volta uma
  semana depois, e o servidor novo ficava sem feriado estadual nem municipal.
- `despachar_lembretes` (Fatia C): varre os `EventReminder` vencendo e emite uma
  `Notificacao` in-app (e e-mail, se configurado) por ocorrência, uma única vez —
  ao dono do evento e, desde a Fatia D, a cada convidado que **aceitou**.

Ambas rodam no `beat`/`worker` já no compose (Fase 10.9), agendadas em
`CELERY_BEAT_SCHEDULE`.
"""
import logging
from datetime import timedelta

from celery import shared_task
from celery.signals import beat_init
from django.core.management import call_command
from django.utils import timezone

from funcoesemail import enviar
from nucleo.notificacoes import criar_notificacao
from nucleo.models import Notificacao
from nucleo.tasks import DLQTask
from nucleo.tenancy import rls_bypass

from . import recurrence
from .models import EventAttendee, EventReminder

logger = logging.getLogger(__name__)

# Tolerância p/ avisos atrasados (worker fora do ar): notifica ocorrências cujo
# aviso venceu há até 1h; mais antigas que isso são ignoradas (não spammar).
CATCHUP = timedelta(minutes=60)


@shared_task
def sincronizar_feriados_task():
    try:
        call_command("sincronizar_feriados")
    except Exception:  # não derruba o worker se a rede/dataset falhar
        logger.exception("Falha ao sincronizar feriados")


@beat_init.connect
def _feriados_no_boot(sender=None, **kwargs):
    """Banco sem `FeriadoSync` nunca sincronizou: enfileira a primeira volta já."""
    try:
        from .models import FeriadoSync

        if not FeriadoSync.objects.exists():
            sincronizar_feriados_task.delay()
    except Exception:  # o beat não deixa de subir por causa disto
        logger.exception("Falha ao agendar a primeira sincronização de feriados")


def _ocorrencias_vencendo(reminder, agora):
    """Inícios de ocorrência que este lembrete deve notificar **agora**: o aviso
    (`início − offset`) já venceu, a ocorrência está dentro da janela de catch-up
    e ainda não foi notificada (`last_sent_occurrence`). Normalmente 0 ou 1."""
    event = reminder.event
    offset = timedelta(minutes=reminder.offset_minutes)
    janela_ini = agora - CATCHUP

    if event.is_recurring:
        # Ocorrências cujo aviso já venceu têm início ≤ agora + offset.
        pares = recurrence.expand_occurrences(event, janela_ini, agora + offset)
        candidatas = [inicio for inicio, _fim in pares]
    else:
        candidatas = [event.start_time]

    ultima = reminder.last_sent_occurrence
    vencendo = [
        inicio for inicio in candidatas
        if (inicio - offset) <= agora <= (inicio + CATCHUP)
        and inicio >= janela_ini
        and (ultima is None or inicio > ultima)
    ]
    return sorted(vencendo)


def _texto(event, occ_start, offset_minutes):
    quando = timezone.localtime(occ_start).strftime("%d/%m/%Y %H:%M")
    if offset_minutes == 0:
        antecedencia = "agora"
    elif offset_minutes % 1440 == 0:
        antecedencia = f"em {offset_minutes // 1440} dia(s)"
    elif offset_minutes % 60 == 0:
        antecedencia = f"em {offset_minutes // 60}h"
    else:
        antecedencia = f"em {offset_minutes} min"
    return f'"{event.title}" começa {antecedencia} ({quando}).'


@shared_task(bind=True, base=DLQTask, max_retries=3)
def despachar_lembretes(self):
    """Despacha os lembretes vencendo. Roda **fora de request**, cruzando tenants
    sob `rls_bypass()` (a RLS fail-closed barraria a leitura/gravação sem
    contexto); o `tenant` de cada `Notificacao` é herdado do evento."""
    agora = timezone.now()
    enviados = 0

    with rls_bypass():
        reminders = (
            EventReminder.objects
            .select_related("event", "event__user")
            .prefetch_related("event__overrides", "event__attendees__user")
        )
        for reminder in reminders:
            event = reminder.event
            vencendo = _ocorrencias_vencendo(reminder, agora)
            if not vencendo:
                continue
            # Notifica a ocorrência mais imminente pendente; as demais (se houver)
            # disparam nos próximos ciclos, uma por vez.
            occ_start = vencendo[0]
            mensagem = _texto(event, occ_start, reminder.offset_minutes)

            for pessoa in _quem_lembrar(event):
                criar_notificacao(
                    user=pessoa,
                    tenant_id=event.tenant_id,
                    titulo=f"Lembrete: {event.title}",
                    mensagem=mensagem,
                    tipo=Notificacao.Tipo.LEMBRETE,
                    url="/app/calendario",
                )
                _enviar_email(pessoa, event, mensagem)

            reminder.last_sent_occurrence = occ_start
            reminder.save(update_fields=["last_sent_occurrence"])
            enviados += 1

    return enviados


def _quem_lembrar(event):
    """O dono do evento e os convidados que aceitaram (Fatia D). Pendente e
    recusado não recebem: lembrar de um compromisso não assumido é ruído."""
    pessoas = [event.user]
    pessoas += [
        a.user for a in event.attendees.all()
        if a.status == EventAttendee.Status.ACEITO and a.user_id != event.user_id
    ]
    return pessoas


def _enviar_email(pessoa, event, mensagem):
    """E-mail opcional do lembrete — no-op sem `MAIL_HOST` (paridade com o CRM).

    Texto em funcoesemail/templates/calendario/lembrete_evento.txt. O `enviar`
    já trata destinatário vazio, ausência de SMTP e falha de envio (loga e
    devolve False), então aqui não há mais try/except: o lembrete in-app já foi
    criado antes desta chamada e não pode ser perdido por causa do e-mail.
    """
    email = getattr(pessoa, "email", "") or getattr(pessoa, "email_pessoal", "")
    enviar(
        "calendario.lembrete_evento",
        email,
        {"titulo": event.title, "mensagem": mensagem},
    )
