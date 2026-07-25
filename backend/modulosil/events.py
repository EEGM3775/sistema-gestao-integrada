# backend/modulosil/events.py
"""Eventos de domínio do SIL — **seam do backbone de eventos (E3)**.

Hoje: log estruturado (o `request_id`/`tenant_id` já entram pela observabilidade).
Futuro (E3, docs/expansão/02-arquitetura-de-expansao.md): publicação via outbox
(linha na transação → relay Celery) consumida por automação (E6), webhooks e a
esfera de rede. Os chamadores não mudam quando o backbone existir."""
import logging

logger = logging.getLogger("sil.eventos")


def emitir_evento_dominio(nome, tenant_id, payload):
    logger.info(
        "evento_dominio %s",
        nome,
        extra={"evento": nome, "tenant_id": str(tenant_id), "payload": payload},
    )
