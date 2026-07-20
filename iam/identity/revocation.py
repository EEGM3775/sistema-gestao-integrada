"""Revogação imediata de sessão por "época" — lado autoridade (Fase 10.7).

Fecha a janela de acesso residual do access token *stateless*: como os resource
servers (backend, drone) validam o access só por assinatura+`exp`, um token já
emitido continua valendo até expirar — mesmo depois de trocar a senha ou
desativar o usuário. Aqui a IAM grava um carimbo ``revoked_after=<agora>`` no
Redis compartilhado; cada resource server rejeita, por requisição, qualquer
access token com ``iat`` anterior a esse carimbo (ver ``nucleo.revocation`` no
backend). Assim a revogação vale **na hora**, não em ``ACCESS_TOKEN_LIFETIME``.

O carimbo tem TTL curto (``SESSION_REVOKE_TTL_SECONDS`` = access TTL + margem):
um access emitido antes do carimbo já terá expirado depois disso, então a chave
é auto-limpante. Redis DB dedicado (2), isolado de celery/cache.

Falha de Redis na **gravação** (bump): logamos e seguimos — o refresh já é
blacklistado à parte pelo chamador, então a sessão não renova; só a revogação
*imediata* do access residual (≤ access TTL) deixa de ser aplicada.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def _redis():
    """Cliente Redis preguiçoso (uma conexão por processo). Timeouts curtos para
    nunca segurar a request/response por causa do Redis."""
    global _client
    if _client is None:
        import redis  # dependência local do IAM (requirements.txt)

        _client = redis.Redis.from_url(
            settings.SESSION_REVOKE_REDIS_URL,
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
        )
    return _client


def bump_session_epoch(user_id) -> bool:
    """Marca *todas as sessões anteriores a agora como revogadas* para o usuário.

    Chamar **antes** de reemitir uma sessão nova para o próprio dispositivo (o
    novo access terá ``iat >= revoked_after`` e passa; a checagem usa ``<``
    estrito). Retorna ``True`` se gravou; ``False`` (com log) se o Redis falhou
    ou a feature está desligada.
    """
    if not settings.SESSION_REVOCATION_ENABLED:
        return False
    try:
        _redis().set(
            f"{settings.SESSION_REVOKE_PREFIX}{user_id}",
            int(time.time()),
            ex=settings.SESSION_REVOKE_TTL_SECONDS,
        )
        return True
    except Exception:  # noqa: BLE001 — Redis fora não pode derrubar a operação de negócio
        logger.exception(
            "Falha ao gravar época de revogação (Redis) p/ user=%s; a sessão foi "
            "blacklistada, mas o access residual só cai em <= access TTL.",
            user_id,
        )
        return False
