# backend/funcoesia/llm_client.py
"""
Cliente da LLM de visão (Fase 11.3 — absorção do microsserviço Node `funcoesia`).

O worker Python lê a imagem do documento *in-process* (FileField local) e a
envia para o serviço de LLM de visão local (Python, em desenvolvimento pelo
cliente) por HTTP: entra `imagem` + `tipo_analise`, sai o JSON do contrato de
análise (ver docs/arquitetura/diario-ia-reintegracao.md).

Este módulo é um wrapper fino e testável (mockável): não conhece Celery nem o
ORM. Erros são tipados para o worker decidir entre **retry** (indisponibilidade
transitória) e **erro permanente** (resposta malformada).
"""
import logging

import requests
from django.conf import settings

from nucleo.rate_limit import consumir

logger = logging.getLogger(__name__)


class LLMIndisponivel(Exception):
    """Falha transitória (rede/timeout/5xx/URL ausente) — vale a pena repetir."""


class LLMResultadoInvalido(Exception):
    """A LLM respondeu, mas fora do contrato mínimo — repetir não ajuda."""


def analisar_imagem(image_bytes, mime_type, tipo_analise):
    """Envia a imagem à LLM de visão e devolve o `resultado_analise` (dict).

    Levanta `LLMIndisponivel` (transitório → retry) ou `LLMResultadoInvalido`
    (permanente → marca `erro`).
    """
    url = getattr(settings, 'LLM_VISION_URL', '') or ''
    if not url:
        # Ainda não há serviço de LLM local no ar (cliente em desenvolvimento):
        # trata como indisponibilidade para não perder o documento silenciosamente.
        raise LLMIndisponivel(
            "LLM_VISION_URL não configurada — serviço de visão indisponível."
        )

    # Camada 2: analise de imagem e a chamada mais cara e lenta do sistema.
    consumir("llm_vision")

    try:
        response = requests.post(
            url,
            files={'imagem': ('imagem', image_bytes, mime_type or 'application/octet-stream')},
            data={'tipo_analise': tipo_analise},
            headers={'X-Internal-Service-Token': settings.IA_SERVICE_SECRET_TOKEN},
            timeout=getattr(settings, 'LLM_VISION_TIMEOUT', (5, 60)),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMIndisponivel(str(exc)) from exc

    try:
        resultado = response.json()
    except ValueError as exc:
        raise LLMResultadoInvalido("resposta da LLM não é JSON válido") from exc

    if not isinstance(resultado, dict):
        raise LLMResultadoInvalido(
            f"resposta da LLM não é um objeto JSON (tipo {type(resultado).__name__})"
        )

    # Carimba o tipo pedido se a LLM não o ecoar (o contrato pode evoluir; ver plano).
    resultado.setdefault('tipo_analise', tipo_analise)
    return resultado
