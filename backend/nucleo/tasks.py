# backend/nucleo/tasks.py
import json
import logging

from celery import Task, shared_task

logger = logging.getLogger(__name__)


def _json_safe(value):
    """JSONField não aceita objetos arbitrários; degrada para repr() sem perder o registro."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


class DLQTask(Task):
    """
    Base de task Celery com Dead Letter Queue: falha permanente (retries
    esgotados) vira linha em `FailedTask`. Usar com
    `@shared_task(bind=True, base=DLQTask, ...)`; o Celery chama `on_failure`
    tanto no worker quanto em modo eager.

    Também é aqui que o **limite de fornecedor** (camada 2 — ver
    docs/arquitetura/rate-limiting.md) vira reagendamento: tratar isso em cada
    task seria repetitivo e fácil de esquecer numa integração nova.
    """

    # Orçamento de retentativas SÓ para espera por limite de fornecedor. É
    # separado (e maior) que o `max_retries` da task de propósito: esperar a fila
    # do fornecedor andar não é sintoma de defeito, e não pode consumir as
    # tentativas reservadas a falhas de verdade (rede, 5xx). Um lote grande pode
    # legitimamente esperar várias janelas até passar inteiro.
    RATE_LIMIT_MAX_RETRIES = 48

    def __call__(self, *args, **kwargs):
        from .rate_limit import LimiteFornecedorExcedido

        try:
            return super().__call__(*args, **kwargs)
        except LimiteFornecedorExcedido as exc:
            # Reagenda em vez de bloquear: worker parado esperando token deixa de
            # atender TODA a fila, inclusive tarefas de outros tenants.
            logger.info(
                "Task %s adiada %ss: limite de '%s' atingido.",
                self.name, exc.espera_segundos, exc.fornecedor,
            )
            raise self.retry(
                exc=exc,
                countdown=exc.espera_segundos,
                max_retries=self.RATE_LIMIT_MAX_RETRIES,
            )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        from .models import FailedTask

        try:
            FailedTask.objects.get_or_create(
                task_id=task_id,
                defaults={
                    "task_name": self.name,
                    "args": [_json_safe(a) for a in (args or [])],
                    "kwargs": {k: _json_safe(v) for k, v in (kwargs or {}).items()},
                    "exception": str(exc),
                    "traceback": str(einfo),
                },
            )
        except Exception:
            logger.exception("CRÍTICO: falha ao gravar na DLQ (task %s)", task_id)
        super().on_failure(exc, task_id, args, kwargs, einfo)


@shared_task(name="nucleo.liberar_cadeiras_presas")
def liberar_cadeiras_presas():
    """D98 — devolve à fila as cadeiras presas por um worker que morreu sem avisar.

    **É a rede do desenho sem despachante próprio.** Todo job que ocupa cadeira
    termina avisando — o caminho feliz chama `frota.concluir` e o `DLQTask` acima
    garante o aviso até no caminho de falha. O que nenhum aviso cobre é a morte
    violenta: OOM do cgroup, container derrubado, máquina reiniciada. Sem esta
    varredura, cada uma dessas reduziria a frota em uma vaga **para sempre**, e o
    sintoma seria uma fila que anda cada vez mais devagar sem nada nos logs.

    Sem `DLQTask` de propósito: uma varredura que falhou não precisa de entrada na
    DLQ nem de retry: o beat a chama de novo em cinco minutos, e o estado que ela
    lê é o mesmo. Uma DLQ cheia de varreduras esconderia a falha que importa.
    """
    from . import frota

    return frota.liberar_orfas()
