"""
Endpoints de saúde e métricas (Fase 10.1).

Separação clássica *liveness* × *readiness*:
- `GET /healthz`  → **liveness**: o processo está de pé e o loop de request
  responde. NÃO toca dependências (um banco fora NÃO deve derrubar/reiniciar o
  container — só marcá-lo como não-pronto). Barato, para o healthcheck do Docker.
- `GET /readyz`   → **readiness**: sonda banco + cache + broker. `503` se algo
  estiver fora → o orquestrador tira o pod do balanceamento sem matá-lo.
- `GET /metrics`  → exposição Prometheus (contagem + latência por rota/status).

Todos são `AllowAny`: não carregam dado sensível (readiness só diz ok/erro por
dependência) e precisam responder a sondas sem credencial. No gateway eles NÃO
são roteados publicamente (só `/api/`, `/media/` vão ao backend), então ficam
acessíveis apenas dentro da rede do compose — de onde Prometheus e o Docker
healthcheck os consomem.
"""
from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import observability as obs


class HealthzView(APIView):
    """Liveness — sempre 200 se o processo atende. Sem I/O."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        return JsonResponse({"status": "ok"})


class ReadyzView(APIView):
    """Readiness — 200 se todas as dependências respondem; 503 caso contrário."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        ok, checks = obs.check_readiness()
        return JsonResponse(
            {"status": "ready" if ok else "degraded", "checks": checks},
            status=200 if ok else 503,
        )


class MetricsView(APIView):
    """Exposição Prometheus. Texto puro no content-type de exposição."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        body, content_type = obs.render_latest_metrics()
        return HttpResponse(body, content_type=content_type)
