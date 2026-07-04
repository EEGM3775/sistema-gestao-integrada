# backend/funcoescobrancas/tasks.py
"""
Tarefas Celery do `funcoescobrancas` — seguem o AD-8 (nova integração externa
→ Celery task em Python). São wrappers finos sobre `services.py`: a lógica
fica testável sem Celery, e aqui só entra retry/Dead Letter Queue.

Em dev, `CELERY_TASK_ALWAYS_EAGER` roda estas tarefas in-process (sem Redis/
worker) — ver `config.settings`.
"""
import logging

from celery import shared_task

from nucleo.tasks import DLQTask

from . import services
from .client import AsaasAPIError
from .services import CobrancaBloqueada

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def criar_cobranca(self, conta_receber_id):
    """ Garante o customer e cria o `payment`/`Boleto` no Asaas para a ContaReceber. """
    from moduloerp.models import ContaReceber

    try:
        conta = ContaReceber.objects.select_related('cliente').get(pk=conta_receber_id)
        boleto = services.gerar_cobranca_asaas(conta)
        logger.info("Cobrança Asaas garantida para ContaReceber #%s — Boleto #%s (gateway_id=%s)",
                    conta_receber_id, boleto.boleto_id, boleto.gateway_id)
        return boleto.boleto_id
    except CobrancaBloqueada as exc:
        # Trava de identidade (nome/CPF divergente, sem documento): é um
        # problema de DADO, não transitório — retry não resolve. A view já
        # barra isso de forma síncrona; se chegou aqui (ex.: corrida com o
        # gateway), NÃO reemitir e deixar a falha visível na DLQ (FailedTask).
        logger.error("Cobrança Asaas BLOQUEADA para ContaReceber #%s [%s]: %s",
                     conta_receber_id, exc.code, exc.mensagem)
        raise
    except AsaasAPIError as exc:
        logger.warning("Falha ao criar cobrança Asaas para ContaReceber #%s (tentativa %s/%s): %s",
                       conta_receber_id, self.request.retries + 1, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def processar_evento_webhook(self, *, evento_id, tipo, payload):
    """ Processa (idempotente) um evento recebido do webhook do Asaas. """
    evento = services.processar_evento_webhook(evento_id=evento_id, tipo=tipo, payload=payload)
    logger.info("Evento Asaas %s (%s) processado: %s", evento_id, tipo, evento.resultado)
    return evento.pk
