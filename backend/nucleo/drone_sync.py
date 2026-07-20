# backend/nucleo/drone_sync.py
"""Reconciliação serviço→serviço com o drone (funcoesODM) — Fase 10.8.

Fecha a pendência da Fase 3: ao excluir uma **obra** ou **empreendimento** no
ERP, os projetos de drone que apontavam para ela (vínculo cross-DB, sem FK)
ficariam órfãos. Aqui o backend, via `post_delete`, enfileira uma task Celery
que **desvincula (soft)** esses projetos no drone.

O backend não pode forjar um token que o drone aceite (só a IAM detém a chave
privada RS256): pede à IAM um **JWT de serviço** de vida curta
(`/auth/service-token/`, autenticado pelo `SERVICE_TOKEN_SECRET`), escopado ao
tenant e com o módulo `drone`, e chama o endpoint de desvínculo do drone com ele.

Sem `DRONE_SERVICE_URL` configurada (ambiente sem o produto drone) tudo vira
no-op silencioso — nada é enfileirado à toa.
"""
import logging

import requests
from celery import shared_task
from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .tasks import DLQTask

logger = logging.getLogger(__name__)


def obter_token_servico(tenant_id, audience="drone"):
    """Pede à IAM um JWT de serviço para agir como `audience` no `tenant_id`.

    Retorna o access token (str) ou lança em erro de rede/credencial — o caller
    (task Celery) trata o retry/DLQ.
    """
    resp = requests.post(
        f"{settings.IAM_INTERNAL_URL.rstrip('/')}/auth/service-token/",
        json={"tenant_id": str(tenant_id), "audience": audience, "caller": "backend"},
        headers={"X-Service-Secret": settings.SERVICE_TOKEN_SECRET},
        timeout=settings.SERVICE_CALL_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access"]


@shared_task(bind=True, base=DLQTask, max_retries=3, default_retry_delay=30)
def desvincular_projetos_drone(self, tenant_id, tipo, obj_id):
    """Desvincula no drone os projetos ligados à obra/empreendimento excluída.

    `tipo` ∈ {"obra", "empreendimento"}. Idempotente: o drone desvincula 0..N e
    responde 200 mesmo quando não há nada. Erros de rede sobem para o retry do
    Celery (e, esgotado, para a DLQ).
    """
    base = (settings.DRONE_SERVICE_URL or "").rstrip("/")
    if not base:
        logger.debug("DRONE_SERVICE_URL não configurada; desvínculo de %s %s ignorado.", tipo, obj_id)
        return
    if not tenant_id:
        logger.warning("Desvínculo de %s %s sem tenant_id; ignorado.", tipo, obj_id)
        return

    try:
        token = obter_token_servico(tenant_id, audience="drone")
        resp = requests.delete(
            f"{base}/api/v1/projects/links/{tipo}/{obj_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.SERVICE_CALL_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Falha ao desvincular %s %s no drone: %s (retry)", tipo, obj_id, exc)
        raise self.retry(exc=exc)

    afetados = (resp.json() or {}).get("unlinked")
    logger.info("Drone: %s projeto(s) desvinculado(s) da %s %s (tenant %s).",
                afetados, tipo, obj_id, tenant_id)


def _enfileirar_desvinculo(tipo, instance):
    """Enfileira o desvínculo se o drone estiver configurado. `tenant_id` vem da
    própria instância (ainda disponível em `post_delete`)."""
    if not settings.DRONE_SERVICE_URL:
        return
    tenant_id = getattr(instance, "tenant_id", None)
    desvincular_projetos_drone.delay(str(tenant_id) if tenant_id else None, tipo, instance.pk)


def conectar_sinais():
    """Liga os `post_delete` de Obra/Empreendimento. Chamado nos `AppConfig.ready()`
    de `obras` e `empreendimentos` (import tardio dos modelos, apps já carregados)."""
    from obras.models import Obra
    from empreendimentos.models import Empreendimento

    @receiver(post_delete, sender=Obra, dispatch_uid="drone_sync_obra")
    def _obra_excluida(sender, instance, **_kwargs):
        _enfileirar_desvinculo("obra", instance)

    @receiver(post_delete, sender=Empreendimento, dispatch_uid="drone_sync_empreendimento")
    def _empreendimento_excluido(sender, instance, **_kwargs):
        _enfileirar_desvinculo("empreendimento", instance)
