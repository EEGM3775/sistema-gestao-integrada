# backend/nucleo/tasks.py
import json
import logging

from celery import Task

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
    """

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
