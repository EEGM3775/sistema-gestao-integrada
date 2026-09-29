"""As fichas que a IAM publica — o que saiu do token na fase 4 (§10.6).

A ficha da empresa (slug, nome, plano, `rate_hora`, quotas) e a da pessoa
(e-mail) moram no Redis da autorização (`funcoesautorizacao.chaves`), escritas
pela IAM a cada troca e a cada volta periódica (`identity/fichas.py`). Aqui elas
são lidas com um cache curto por processo: a ficha muda quando o plano muda,
não a cada requisição.

**Ficha ausente** (Redis fora, ou empresa que a IAM ainda não publicou) devolve
`None`, e quem lê faz o que fazia com a claim ausente: o throttle cai no padrão
do settings, as quotas não travam (fail-open ruidoso do `nucleo/quotas.py`), o
plano é o padrão. É o comportamento de antes para um token sem a claim — só a
fonte mudou.
"""
from __future__ import annotations

import json
import logging
import time

from funcoesautorizacao import chaves

from . import autorizacao_pdp

logger = logging.getLogger(__name__)

# Quanto o processo confia numa ficha lida — TTL de cache (§5.6), não teto.
_TTL_S = 30.0
_memo: dict[str, tuple[float, dict | None]] = {}


def _ler(chave: str) -> dict | None:
    agora = time.monotonic()
    guardada = _memo.get(chave)
    if guardada is not None and agora - guardada[0] < _TTL_S:
        return guardada[1]
    r = autorizacao_pdp.redis()
    if r is None:
        return guardada[1] if guardada else None
    try:
        bruto = r.get(chave)
    except Exception:  # noqa: BLE001 - sem ficha, o comportamento de claim ausente
        autorizacao_pdp.redis_caiu()
        logger.warning("fichas.redis_indisponivel chave=%s", chave)
        return guardada[1] if guardada else None
    valor = json.loads(bruto) if bruto else None
    _memo[chave] = (agora, valor)
    return valor


def da_empresa(tenant_id) -> dict | None:
    return _ler(chaves.ficha_da_empresa(str(tenant_id))) if tenant_id else None


def da_pessoa(usuario_id) -> dict | None:
    return _ler(chaves.ficha_da_pessoa(str(usuario_id))) if usuario_id else None


def esquecer() -> None:
    """Para os testes: a próxima leitura vai ao Redis."""
    _memo.clear()
