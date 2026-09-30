"""O BFF — o navegador tem um cookie, e o serviço recebe um token (fase 5, §10.5).

Até a fase 4 o access vivia na memória do JavaScript: um script injetado (XSS)
o lia e o usava fora do navegador (§10.1). Agora o SPA só tem o cookie HttpOnly
da sessão, e quem põe o token no pedido é o gateway: para cada chamada a
`/api/`, `/odm-api/` e `/ws/`, ele pergunta à IAM (`auth_request` para
`/auth/interno/bff/<serviço>/`) e injeta no `Authorization` o access **daquele
serviço**, de 5 minutos. O token existe no servidor e na rede interna; no
navegador, nunca (RFC 10017, "Backend for Frontend").

O cookie viaja sozinho em todo pedido do mesmo site, e é por isso que escrita
exige, além dele, o cabeçalho anti-CSRF: `SameSite=Strict` já barra o envio a
partir de outro site, e o cabeçalho próprio barra o que o `SameSite` não cobre
(navegador antigo, subdomínio irmão) — um formulário de outra origem não
consegue pô-lo sem passar pelo CORS.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from django.conf import settings

from funcoesautorizacao import chaves

from . import emissao, sessoes
from .revocation import _redis, redis_caiu

logger = logging.getLogger(__name__)

CABECALHO_ANTI_CSRF = "X-SGI-CSRF"
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

#: O access guardado sai do cache um minuto antes de vencer: o serviço nunca
#: recebe um token que expira no meio do pedido. É desempenho, não limite
#: (`payment/planos.py` §5.6).
_MARGEM_S = 60


def _mesmo_site(origem: str, host: str) -> bool:
    return (urlparse(origem).hostname or "") == host.split(":")[0]


def _origem_aceita(origem: str | None, host: str) -> bool:
    return bool(origem) and (
        _mesmo_site(origem, host) or origem in set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    )


def escrita_legitima(metodo: str, cabecalhos, host: str) -> bool:
    """A escrita que chega com o cookie veio da nossa própria tela?

    Leitura passa. Escrita precisa do cabeçalho anti-CSRF e, quando o navegador
    diz de onde vem (`Sec-Fetch-Site`, `Origin`), de vir do mesmo site.

    **O WebSocket é a exceção da leitura** (`/ws/`): o upgrade é um GET, e o
    navegador não deixa página nenhuma pôr cabeçalho próprio nele — então quem
    decide é o `Origin`, que ele manda sempre. Sem isto, uma página de outro site
    abriria o canal do drone com a sessão de quem a visitou (CSWSH)."""
    # O nginx não repassa o `Upgrade` (é de salto a salto): o gateway o manda
    # como `X-Original-Upgrade`.
    upgrade = cabecalhos.get("X-Original-Upgrade") or cabecalhos.get("Upgrade") or ""
    if upgrade.lower() == "websocket":
        return _origem_aceita(cabecalhos.get("Origin"), host)
    if (metodo or "GET").upper() in METODOS_SEGUROS:
        return True
    if not cabecalhos.get(CABECALHO_ANTI_CSRF):
        return False
    site = cabecalhos.get("Sec-Fetch-Site")
    if site and site not in ("same-origin", "none"):
        return False
    origem = cabecalhos.get("Origin")
    if origem and not _origem_aceita(origem, host):
        return False
    return True


def token_para(credencial: str, audiencia: str) -> str | None:
    """O access desta sessão para esta audiência, ou `None` se a sessão não vale.

    O mesmo access serve aos pedidos seguintes até perto de vencer (Redis, DB 2),
    para uma tela que dispara vinte chamadas não assinar vinte tokens. Redis
    fora não impede nada: assina de novo a cada pedido."""
    chave = chaves.token_da_sessao(sessoes.hash_da_credencial(credencial), audiencia)
    try:
        guardado = _redis().get(chave)
        if guardado:
            return guardado.decode() if isinstance(guardado, bytes) else str(guardado)
    except Exception:  # noqa: BLE001
        redis_caiu()
        logger.warning("bff.cache_indisponivel")

    sessao = sessoes.pela_credencial(credencial)
    if sessao is None:
        return None
    token = emissao.access_da_sessao(sessao, audiencia)

    agora = time.time()
    vida = min(
        emissao.exp_de(token) - agora - _MARGEM_S,
        sessao.expira_em.timestamp() - agora,
    )
    if vida >= 1:
        try:
            _redis().set(chave, token, ex=int(vida))
        except Exception:  # noqa: BLE001
            redis_caiu()
    return token
