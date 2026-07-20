"""
Middleware de observabilidade (Fase 10.1).

Envolve toda requisição para:
- estabelecer/propagar o `request_id` (aceita o `X-Request-ID` da borda — o
  gateway o gera — ou cria um; devolve-o no header da resposta para o cliente
  correlacionar);
- cronometrar a requisição e emitir uma linha de **log de acesso estruturado**
  (JSON) ao final, com método, rota, status, duração e o contexto de correlação;
- alimentar as **métricas** Prometheus (contagem + latência) por rota/status.

Deve ficar no TOPO de `MIDDLEWARE` para medir o tempo total (inclusive dos
demais middlewares). O `tenant_id` é setado mais tarde, na autenticação do DRF
(`arm_rls_for_request`), e já estará no contexto quando a linha de acesso é
emitida em `process_response`.
"""
from __future__ import annotations

import logging
import time

from . import observability as obs

logger = logging.getLogger("sgi.access")

# Header padrão de correlação (mesmo nome usado pelo gateway).
REQUEST_ID_HEADER = "X-Request-ID"
_META_KEY = "HTTP_X_REQUEST_ID"

# Rotas de infra que não valem uma linha de log por acesso (poluiriam o stream e
# inflariam a cardinalidade das métricas). Health é sondado a cada ~10s.
_QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


class ObservabilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Nome do serviço nas métricas/labels — distingue erp/worker/iam num
        # Prometheus compartilhado.
        from django.conf import settings

        self.service = getattr(settings, "OBSERVABILITY_SERVICE_NAME", "erp")

    def __call__(self, request):
        incoming = request.META.get(_META_KEY, "").strip()
        request_id = incoming or obs.new_request_id()
        obs.set_request_id(request_id)
        request.request_id = request_id

        start = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            # A view estourou: a exceção segue para o handler do Django (500),
            # mas registramos a métrica e a linha de acesso antes de propagar.
            duration_s = time.monotonic() - start
            self._record(request, 500, duration_s)
            obs.reset_request_context()
            raise

        duration_s = time.monotonic() - start
        response[REQUEST_ID_HEADER] = request_id
        self._aplicar_headers_de_teto(request, response)
        self._record(request, response.status_code, duration_s)
        obs.reset_request_context()
        return response

    @staticmethod
    def _aplicar_headers_de_teto(request, response) -> None:
        """D23 — `X-RateLimit-*`, o padrão de fato (GitHub, Stripe, Shopify).

        O DRF só manda `Retry-After`, e só no 429. Sem estes headers o cliente
        não tem como se auto-regular: ele descobre o teto **batendo nele**, que é
        justamente o comportamento que o teto existe para evitar. O throttle
        deixa os números na request; aqui só viram cabeçalho.
        """
        info = getattr(request, "sgi_rate_info", None)
        if not info:
            return
        response["X-RateLimit-Limit"] = str(info["limite"])
        response["X-RateLimit-Remaining"] = str(max(0, info["restante"]))
        response["X-RateLimit-Reset"] = str(info["reset"])

    def _view_label(self, request) -> str:
        """Rótulo de baixa cardinalidade para as métricas: o nome da rota
        resolvida (ex.: `cliente-list`), não o path cru (que traria ids)."""
        match = getattr(request, "resolver_match", None)
        if match and match.view_name:
            return match.view_name
        return "unmatched"

    def _record(self, request, status: int, duration_s: float) -> None:
        path = request.path
        view = self._view_label(request)
        obs.observe_request(self.service, request.method, view, status, duration_s)

        if path in _QUIET_PATHS:
            return

        duration_ms = round(duration_s * 1000, 1)
        level = logging.ERROR if status >= 500 else logging.INFO
        logger.log(
            level,
            "%s %s %s",
            request.method,
            path,
            status,
            extra={
                "event": "http_access",
                "service": self.service,
                "method": request.method,
                "path": path,
                "view": view,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
