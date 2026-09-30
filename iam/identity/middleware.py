"""
Middleware de observabilidade da IAM (Fase 10.1) — espelho de
`nucleo.middleware.ObservabilityMiddleware`. Ver a documentação de lá.
"""
from __future__ import annotations

import logging
import time

from . import observability as obs

logger = logging.getLogger("sgi.access")

REQUEST_ID_HEADER = "X-Request-ID"
_META_KEY = "HTTP_X_REQUEST_ID"
_QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


class ObservabilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        from django.conf import settings

        self.service = getattr(settings, "OBSERVABILITY_SERVICE_NAME", "iam")

    def __call__(self, request):
        incoming = request.META.get(_META_KEY, "").strip()
        request_id = incoming or obs.new_request_id()
        obs.set_request_id(request_id)
        request.request_id = request_id

        start = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            self._record(request, 500, time.monotonic() - start)
            obs.reset_request_context()
            raise

        duration_s = time.monotonic() - start
        response[REQUEST_ID_HEADER] = request_id
        self._record(request, response.status_code, duration_s)
        obs.reset_request_context()
        return response

    def _view_label(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        if match and match.view_name:
            return match.view_name
        return "unmatched"

    def _record(self, request, status: int, duration_s: float) -> None:
        path = request.path
        view = self._view_label(request)
        obs.observe_request(self.service, request.method, view, status, duration_s)

        # O BFF (fase 5) é consultado pelo gateway a cada chamada à API: a linha
        # do acesso já sai no serviço de destino, e a métrica acima fica.
        if path in _QUIET_PATHS or path.startswith("/auth/interno/bff/"):
            return

        logger.log(
            logging.ERROR if status >= 500 else logging.INFO,
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
                "duration_ms": round(duration_s * 1000, 1),
            },
        )
