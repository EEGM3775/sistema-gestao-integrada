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


def abrir_disjuntor(*, propagar: bool = True) -> None:
    """Abre o breaker. O Redis da autorização é o mesmo servidor: o disjuntor
    de lá abre junto, para a mesma queda não ser descoberta duas vezes por
    requisição (achado do teste de caos, fase 6)."""
    global _breaker_until
    _breaker_until = time.monotonic() + _BREAKER_COOLDOWN
    if propagar:
        from . import autorizacao_pdp

        autorizacao_pdp.redis_caiu()


def disjuntor_aberto() -> bool:
    return time.monotonic() < _breaker_until


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
        abrir_disjuntor()
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


# --- A sessão (`sid`) — fase 4 da remodelagem (§10.5 e §10.8, classe B) -------

#: Por quanto tempo a resposta sobre um `sid` vale quando o Redis some — o TTL
#: da classe B (`funcoesautorizacao/classes.py`). TTL de cache (§5.6), não teto.
_SID_TTL_S = 5.0
_sids: dict[str, tuple[float, bool]] = {}
# O que é lembrado por processo só serve à queda do Redis; esvaziar de vez em
# quando custa uma ida ao Redis. Tamanho do motor, não teto de cliente (§5.6).
_SIDS_LEMBRADOS = 10_000


def _perguntar_a_iam(sid: str) -> bool | None:
    """A IAM é a autoridade das sessões. ``True``/``False`` (ativa?), ou ``None``
    quando nem ela responde."""
    import json
    import urllib.error
    import urllib.request

    url = f"{settings.IAM_INTERNAL_URL.rstrip('/')}/auth/interno/sessao/{sid}/"
    try:
        with urllib.request.urlopen(url, timeout=1.0) as resp:
            return bool(json.loads(resp.read().decode() or "{}").get("ativa"))
    except urllib.error.HTTPError as exc:
        # 404 é o `<uuid:sid>` recusado: um sid que não é UUID não é sessão nenhuma.
        return False if exc.code == 404 else None
    except Exception:  # noqa: BLE001
        return None


def is_sid_revoked(sid) -> bool:
    """A sessão deste access foi encerrada? True → o caller nega (401).

    A regra da classe B, e não o fail-open do carimbo por época: Redis de pé
    responde na hora; Redis fora serve o que foi visto há até `_SID_TTL_S` e
    depois pergunta à IAM; IAM também fora → **nega**. Token sem `sid` (emitido
    antes da fase 4, ou de serviço) não tem sessão a conferir.
    """
    if not getattr(settings, "SESSION_REVOCATION_ENABLED", True) or not sid:
        return False
    from funcoesautorizacao import chaves

    sid = str(sid)
    agora = time.monotonic()
    global _breaker_until
    if agora >= _breaker_until:
        try:
            revogada = _redis().get(chaves.sessao_revogada(sid)) is not None
            if len(_sids) >= _SIDS_LEMBRADOS:
                _sids.clear()
            _sids[sid] = (agora, revogada)
            return revogada
        except Exception:  # noqa: BLE001
            abrir_disjuntor()
            logger.warning("Redis indisponível na checagem do sid; cache de %.0fs, depois a IAM.",
                           _SID_TTL_S)
    visto = _sids.get(sid)
    if visto is not None and agora - visto[0] < _SID_TTL_S:
        return visto[1]
    ativa = _perguntar_a_iam(sid)
    if ativa is None:
        logger.warning("Nem o Redis nem a IAM responderam sobre o sid — nega.")
        return True
    _sids[sid] = (agora, not ativa)
    return not ativa
