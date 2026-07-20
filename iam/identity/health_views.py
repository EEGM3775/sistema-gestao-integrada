"""
Endpoints de saúde e métricas da IAM (Fase 10.1) — espelho de
`nucleo.health_views`. Liveness sem I/O, readiness sonda banco+Redis, `/metrics`
expõe Prometheus. Todos `AllowAny`; não roteados publicamente pelo gateway.
"""
from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import observability as obs


class HealthzView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        return JsonResponse({"status": "ok"})


class ReadyzView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        ok, checks = obs.check_readiness()
        return JsonResponse(
            {"status": "ready" if ok else "degraded", "checks": checks},
            status=200 if ok else 503,
        )


class MetricsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        body, content_type = obs.render_latest_metrics()
        return HttpResponse(body, content_type=content_type)
