"""
Testes da Dead Letter Queue (achado L2): falha permanente de task Celery
deve virar linha em `FailedTask` — com o task_id UUID (string) do Celery.
"""
from celery import shared_task
from django.test import TestCase

from .models import FailedTask
from .tasks import DLQTask


@shared_task(bind=True, base=DLQTask)
def _task_que_sempre_falha(self, documento_id):
    raise ValueError("falha proposital para o teste da DLQ")


class DLQTests(TestCase):
    def test_falha_permanente_grava_failedtask(self):
        result = _task_que_sempre_falha.apply(args=[123], throw=False)

        self.assertTrue(result.failed())
        registro = FailedTask.objects.get(task_id=result.id)
        self.assertEqual(registro.task_name, _task_que_sempre_falha.name)
        self.assertEqual(registro.args, [123])
        self.assertIn("falha proposital", registro.exception)
