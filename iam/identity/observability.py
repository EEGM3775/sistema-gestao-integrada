"""
Observabilidade da IAM (Fase 10.1) — espelho enxuto de `nucleo.observability`.

Mesmo contrato do backend (logs JSON com `request_id`, métricas Prometheus, sondas
de prontidão), sem a parte de `tenant_id` por requisição: a IAM não tem RLS
tenant-scoped, então o correlator principal aqui é o `request_id`. O `tenant_id`
existe na API (getter estável) mas fica em `None` por padrão.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> None:
    _request_id.set(value or None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_tenant_id(value) -> None:
    _tenant_id.set(str(value) if value else None)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def reset_request_context() -> None:
    _request_id.set(None)
    _tenant_id.set(None)


_STD_LOGRECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        if not hasattr(record, "tenant_id"):
            record.tenant_id = get_tenant_id()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "tenant_id": getattr(record, "tenant_id", None),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STD_LOGRECORD_ATTRS and key not in payload:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


try:  # pragma: no cover
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
        multiprocess,
    )

    PROMETHEUS_AVAILABLE = True
except Exception:  # noqa: BLE001
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


if PROMETHEUS_AVAILABLE:
    _LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    REQUEST_COUNT = Counter(
        "sgi_http_requests_total",
        "Total de requisições HTTP por método, rota e status.",
        ["service", "method", "view", "status"],
    )
    REQUEST_LATENCY = Histogram(
        "sgi_http_request_duration_seconds",
        "Latência das requisições HTTP em segundos.",
        ["service", "method", "view"],
        buckets=_LATENCY_BUCKETS,
    )
else:
    REQUEST_COUNT = None
    REQUEST_LATENCY = None


def observe_request(service: str, method: str, view: str, status: int, duration_s: float) -> None:
    if not PROMETHEUS_AVAILABLE:
        return
    REQUEST_COUNT.labels(service=service, method=method, view=view, status=str(status)).inc()
    REQUEST_LATENCY.labels(service=service, method=method, view=view).observe(duration_s)


def render_latest_metrics() -> tuple[bytes, str]:
    if not PROMETHEUS_AVAILABLE:
        return b"# prometheus_client nao instalado; metricas desativadas\n", CONTENT_TYPE_LATEST

    import os

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


def check_readiness() -> tuple[bool, dict]:
    """Sonda banco + Redis de revogação de sessão (a IAM não usa Celery/cache)."""
    checks: dict[str, str] = {}
    ok = True

    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"erro: {exc}"
        ok = False

    try:
        from django.conf import settings

        url = getattr(settings, "SESSION_REVOKE_REDIS_URL", "")
        if url.startswith("redis"):
            import redis

            client = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
            client.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "ignorado"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"erro: {exc}"
        ok = False

    return ok, checks
