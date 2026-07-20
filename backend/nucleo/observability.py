"""
Observabilidade da plataforma (Fase 10.1) — núcleo compartilhado.

Três eixos, todos emitindo para **stdout**/endpoints (os containers já capturam):

1. **Correlação de requisição** — `request_id` (gerado na borda ou no
   `ObservabilityMiddleware`) e `tenant_id` (armado junto do contexto RLS) vivem
   em `contextvars`, de modo que QUALQUER log emitido durante a requisição os
   carrega, sem precisar passá-los de função em função. O `JsonLogFormatter` os
   injeta em toda linha; o `RequestContextFilter` garante os atributos mesmo em
   logs fora de requisição (Celery, management commands).

2. **Métricas** — contador de requisições por método/rota/status e histograma
   de latência, no formato Prometheus (`/metrics`). O import de `prometheus_client`
   é **tolerante**: se a lib não estiver instalada, tudo vira no-op e o app sobe
   normalmente (útil antes de `pip install`); com a lib, `/metrics` expõe de fato.

3. **Prontidão** — `check_readiness()` sonda banco, cache (Redis) e broker
   (Celery/Redis) para o `/readyz`, separando *liveness* (processo vivo) de
   *readiness* (dependências prontas para receber tráfego).

Espelhado na IAM (`identity/observability.py`) com o mesmo contrato.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

# --- Contexto de requisição (correlação) ------------------------------------

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def new_request_id() -> str:
    """Gera um id de requisição curto e ordenável o suficiente para correlação."""
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> None:
    _request_id.set(value or None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_tenant_id(value) -> None:
    """Registra o tenant da requisição para os logs. Chamado do choke point do
    contexto RLS (`arm_rls_for_*`), de modo que toda linha logada depois carregue
    o tenant sem acoplar o logging à camada de tenancy."""
    _tenant_id.set(str(value) if value else None)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def reset_request_context() -> None:
    """Zera o contexto ao fim da requisição (evita vazar id/tenant para a próxima
    requisição reusando a mesma thread/worker)."""
    _request_id.set(None)
    _tenant_id.set(None)


# --- Logging estruturado (JSON) ---------------------------------------------

# Atributos padrão de um LogRecord — o que sobrar são "extras" do chamador e vai
# para o JSON como campo de topo (ex.: logger.info("...", extra={"status": 500})).
_STD_LOGRECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class RequestContextFilter(logging.Filter):
    """Anexa `request_id`/`tenant_id` do contexto a todo LogRecord — inclusive os
    de libs de terceiros (que não conhecem o nosso contexto)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        if not hasattr(record, "tenant_id"):
            record.tenant_id = get_tenant_id()
        return True


class JsonLogFormatter(logging.Formatter):
    """Formata cada linha como um objeto JSON de uma linha (line-delimited JSON),
    consumível por qualquer coletor (Loki/ELK/CloudWatch) sem parser custom."""

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
        # Extras estruturados do chamador (status, method, path, duration_ms, ...).
        for key, value in record.__dict__.items():
            if key not in _STD_LOGRECORD_ATTRS and key not in payload:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


# --- Métricas (Prometheus, tolerante à ausência da lib) ----------------------

try:  # pragma: no cover - caminho depende do ambiente
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
        multiprocess,
    )

    PROMETHEUS_AVAILABLE = True
except Exception:  # noqa: BLE001 - lib opcional; app deve subir sem ela
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


if PROMETHEUS_AVAILABLE:
    # Buckets em segundos calibrados para uma API web (1 ms a ~10 s).
    _LATENCY_BUCKETS = (
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    )
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
else:  # no-op: mantém a API estável sem a lib instalada
    REQUEST_COUNT = None
    REQUEST_LATENCY = None


def observe_request(service: str, method: str, view: str, status: int, duration_s: float) -> None:
    """Registra uma requisição nas métricas. No-op sem `prometheus_client`."""
    if not PROMETHEUS_AVAILABLE:
        return
    REQUEST_COUNT.labels(service=service, method=method, view=view, status=str(status)).inc()
    REQUEST_LATENCY.labels(service=service, method=method, view=view).observe(duration_s)


def render_latest_metrics() -> tuple[bytes, str]:
    """Serializa as métricas no formato de exposição do Prometheus.

    Suporta gunicorn multi-worker: com `PROMETHEUS_MULTIPROC_DIR` setado, agrega
    os arquivos por processo num `MultiProcessCollector`; sem ele, usa o registry
    global do processo. Devolve `(corpo, content_type)`."""
    if not PROMETHEUS_AVAILABLE:
        body = b"# prometheus_client nao instalado; metricas desativadas\n"
        return body, CONTENT_TYPE_LATEST

    import os

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


# --- Prontidão (readiness) ---------------------------------------------------

def check_readiness() -> tuple[bool, dict]:
    """Sonda as dependências externas para o `/readyz`. Devolve
    `(ok, {dependencia: "ok"|"erro: ..."})`. Cada sonda é isolada: uma falha não
    esconde o estado das outras."""
    checks: dict[str, str] = {}
    ok = True

    # Banco: um SELECT trivial pela conexão default.
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"erro: {exc}"
        ok = False

    # Cache (Redis): round-trip curto.
    try:
        from django.core.cache import cache

        cache.set("_readyz_probe", "1", timeout=5)
        cache.get("_readyz_probe")
        checks["cache"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"erro: {exc}"
        ok = False

    # Broker (Celery/Redis): PING direto na URL do broker (não usa o worker).
    try:
        from django.conf import settings

        broker_url = getattr(settings, "CELERY_BROKER_URL", "")
        if broker_url.startswith("redis"):
            import redis

            client = redis.Redis.from_url(
                broker_url, socket_timeout=0.5, socket_connect_timeout=0.5
            )
            client.ping()
            checks["broker"] = "ok"
        else:
            checks["broker"] = "ignorado"
    except Exception as exc:  # noqa: BLE001
        checks["broker"] = f"erro: {exc}"
        ok = False

    return ok, checks
