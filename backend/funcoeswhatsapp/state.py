# backend/funcoeswhatsapp/state.py
"""
Estado da conversa e idempotência no Redis (Fase C, §4.4).

- **Estado** por `(tenant, telefone)` — chave escopada por tenant, nunca cruza;
  TTL deslizante (~30 min) higieniza sessões abandonadas (cada `set` renova).
- **Idempotência** por `message.id` da Meta (que reentrega em falha de ACK):
  `cache.add` é atômico → a primeira chamada grava e devolve "novo", a segunda
  encontra a chave e devolve "repetida".

Usa `django.core.cache` (django_redis, DB 1) — sem cliente Redis próprio.
"""
from django.core.cache import cache

STATE_TTL = 1800   # 30 min (deslizante)
SEEN_TTL = 3600    # 1 h — janela de reentrega da Meta


def _state_key(tenant_id, telefone):
    return f"wa:state:{tenant_id}:{telefone}"


def get_state(tenant_id, telefone):
    return cache.get(_state_key(tenant_id, telefone))


def set_state(tenant_id, telefone, estado):
    cache.set(_state_key(tenant_id, telefone), estado, STATE_TTL)


def clear_state(tenant_id, telefone):
    cache.delete(_state_key(tenant_id, telefone))


def ja_processada(message_id):
    """True se `message_id` já foi vista (reentrega). Marca como vista de forma
    atômica quando é a primeira vez. `None`/vazio → nunca considera repetida."""
    if not message_id:
        return False
    novo = cache.add(f"wa:seen:{message_id}", 1, SEEN_TTL)
    return not novo
