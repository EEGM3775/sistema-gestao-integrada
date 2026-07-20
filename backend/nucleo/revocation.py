"""Checagem de revogação imediata de sessão — lado resource server (Fase 10.7).

O access token é *stateless*: validado só por assinatura+`exp`, ele sobrevive à
troca de senha / desativação até expirar (a janela residual que um funcionário
descontente exploraria). Para fechar isso, a IAM grava um carimbo
``revoked_after=<agora>`` no Redis compartilhado (ver ``identity.revocation``);
aqui rejeitamos, **por requisição**, todo access token cujo ``iat`` seja anterior
ao carimbo do usuário.

FAIL-OPEN (``SESSION_REVOCATION_FAIL_OPEN=True``, padrão): se o Redis não
responder, NÃO bloqueia — a pior consequência é voltar à janela de ≤ access TTL
enquanto o Redis estiver fora, em vez de derrubar TODA a autenticação do backend.
Configurável para fail-closed em ambientes que priorizam contenção sobre
disponibilidade (ver docs/acesso-e-permissoes.md).
"""
from __future__ import annotations

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None

# Circuit breaker: um Redis fora do ar pode custar segundos por chamada (a
# resolução DNS do host parado NÃO é limitada pelo `socket_timeout`). Sem isto,
# uma queda do Redis deixaria TODA requisição autenticada lenta. Ao primeiro
# erro, abrimos o breaker por `_BREAKER_COOLDOWN`s e respondemos pela política
# fail-open/closed na hora, sem tocar no Redis — pagando só uma sondagem lenta a
# cada cooldown, não uma por requisição.
_BREAKER_COOLDOWN = 5.0
_breaker_until = 0.0


def _redis():
    """Cliente Redis preguiçoso, com timeouts curtos e sem retry (a checagem roda
    em toda requisição autenticada; falha rápido para o breaker assumir)."""
    global _client
    if _client is None:
        import redis

        _client = redis.Redis.from_url(
            settings.SESSION_REVOKE_REDIS_URL,
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
            retry_on_timeout=False,
        )
    return _client


def _decisao_degradada() -> bool:
    """Resposta quando o Redis está indisponível: fail-open → não revoga (permite);
    fail-closed → revoga (nega)."""
    return not getattr(settings, "SESSION_REVOCATION_FAIL_OPEN", True)


def is_session_revoked(user_id, token_iat) -> bool:
    """A sessão deste access token foi revogada? True → o caller deve negar (401).

    Compara o ``iat`` do token com o carimbo ``revoked_after`` do usuário: emitido
    ANTES do carimbo (``iat < revoked_after``) → revogado. Ausência de carimbo →
    não revogado. Erro de Redis → decisão degradada (fail-open/closed), com o
    circuit breaker evitando pagar o custo do Redis fora em toda requisição.
    """
    if not getattr(settings, "SESSION_REVOCATION_ENABLED", True):
        return False
    if not user_id or token_iat is None:
        return False

    global _breaker_until
    if time.monotonic() < _breaker_until:
        # Breaker aberto: decide sem tocar no Redis (rápido).
        return _decisao_degradada()

    try:
        raw = _redis().get(f"{settings.SESSION_REVOKE_PREFIX}{user_id}")
    except Exception:  # noqa: BLE001 — Redis fora não pode quebrar a autenticação
        _breaker_until = time.monotonic() + _BREAKER_COOLDOWN
        fail_open = getattr(settings, "SESSION_REVOCATION_FAIL_OPEN", True)
        logger.warning(
            "Redis indisponível na checagem de revogação; abrindo breaker por %.0fs; "
            "fail-%s.", _BREAKER_COOLDOWN, "open (permitindo)" if fail_open else "closed (negando)",
        )
        return _decisao_degradada()

    if raw is None:
        return False
    try:
        revoked_after = int(raw)
    except (TypeError, ValueError):
        return False
    return int(token_iat) < revoked_after
