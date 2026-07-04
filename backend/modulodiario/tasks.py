# backend/modulodiario/tasks.py
import requests
import os
import logging
from celery import shared_task
from nucleo.tasks import DLQTask

logger = logging.getLogger(__name__)

@shared_task(bind=True, base=DLQTask, max_retries=3)
def disparar_analise_ia(self, documento_id, tipo_analise):
    """
    Tarefa Celery para chamar o microserviço de IA de forma assíncrona.
    Tenta novamente até 3 vezes em caso de falha de comunicação.
    Se falhar permanentemente, a falha é registrada na DLQ (FailedTask).
    """
    ia_service_url = os.getenv('IA_SERVICE_URL', 'http://localhost:3002/api/analise')
    ia_service_secret = os.getenv('IA_SERVICE_SECRET_TOKEN', '')

    headers = {
        'Content-Type': 'application/json',
        'X-Internal-Service-Token': ia_service_secret
    }
    
    payload = {
        'documento_id': documento_id,
        'tipo_analise': tipo_analise
    }

    try:
        response = requests.post(
            ia_service_url,
            json=payload,
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        logger.info(f"Gatilho de análise de IA ({tipo_analise}) disparado com sucesso para o documento ID: {documento_id}")
    except requests.RequestException as e:
        logger.warning(f"Falha ao disparar gatilho de IA para o documento ID {documento_id}. Tentativa {self.request.retries + 1} de {self.max_retries}. Erro: {e}")
        # Ativa a lógica de retentativa do Celery, esperando 60 segundos antes da próxima tentativa.
        raise self.retry(exc=e, countdown=60)
