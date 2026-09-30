"""A emissão do access por audiência e do token de serviço (fase 5, §10.6).

O SimpleJWT assina todo token com um `aud` só (o `AUDIENCE` do settings) e sem
`typ` no cabeçalho. A fase 5 precisa de um access **por serviço** e de um tipo
que separe pessoa de serviço, então a assinatura dos tokens que saem da IAM
mora aqui — com a mesma chave e o mesmo algoritmo do SimpleJWT (RS256 fora do
dev), e com as claims que o SimpleJWT dos validadores exige (`token_type`,
`jti`, `user_id`). O refresh continua sendo do SimpleJWT: ele não sai da IAM.
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import jwt
from django.conf import settings

from funcoesautorizacao import audiencias

from .tokens import build_claims


def _assinar(carga: dict, tipo: str) -> str:
    cfg = settings.SIMPLE_JWT
    cabecalho = {"typ": tipo}
    publica = getattr(settings, "JWT_PUBLIC_KEY", "") or ""
    if cfg["ALGORITHM"].startswith("RS") and publica:
        from .views import jwk_kid  # o mesmo `kid` que o JWKS publica

        cabecalho["kid"] = jwk_kid(publica)
    return jwt.encode(carga, cfg["SIGNING_KEY"], algorithm=cfg["ALGORITHM"], headers=cabecalho)


def _padrao(audiencia, vida: timedelta, agora: int | None = None) -> dict:
    agora = int(agora or time.time())
    return {
        "iss": audiencias.EMISSOR,
        "aud": audiencia,
        "iat": agora,
        "nbf": agora,
        "exp": agora + int(vida.total_seconds()),
        "jti": uuid.uuid4().hex,
        "token_type": "access",  # o SimpleJWT do backend confere
    }


def _acr(amr) -> str:
    """A força da autenticação (RFC 9470), dita pelo `amr`, nos níveis do NIST
    SP 800-63B: `aal1` só senha, `aal2` senha e segundo fator. Curto de
    propósito — o token enxuto tem teto (test_d194_token)."""
    return "aal2" if "otp" in (amr or []) else "aal1"


def access_da_pessoa(user, *, audiencia, sid, amr, auth_time: int, sst: int | None = None) -> str:
    """O access de uma pessoa para **um** serviço: identidade, sessão e a idade
    da autenticação — o que a fase 4 fixou, mais `aud`, `acr` e o `typ`."""
    carga = _padrao(audiencia, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])
    carga.update({
        "user_id": str(user.id),
        **build_claims(user),
        "sid": str(sid),
        "amr": list(amr or ["pwd"]),
        "acr": _acr(amr),
        "auth_time": int(auth_time),
    })
    if sst:
        carga["sst"] = int(sst)
    return _assinar(carga, audiencias.TIPO_PESSOA)


def access_da_sessao(sessao, audiencia) -> str:
    """O access que o BFF injeta: tudo sai da linha da sessão."""
    return access_da_pessoa(
        sessao.usuario, audiencia=audiencia, sid=sessao.sid, amr=sessao.amr,
        auth_time=int(sessao.auth_time.timestamp()),
        sst=int(sessao.criada_em.timestamp()) if sessao.criada_em else None,
    )


def exp_de(token: str) -> int:
    return int(jwt.decode(token, options={"verify_signature": False})["exp"])


def token_de_servico(*, caller: str, tenant_id: str, produto: str,
                     ttl_seconds: int | None = None) -> str:
    """JWT **serviço→serviço** (Fase 10.8, separado por tipo e audiência na
    fase 5): `typ` próprio, `aud` do produto de destino e um `scope` só — o que
    o chamador veio fazer. Não representa pessoa: sem `user_id`, sem `sid`.

    `produto` é o nome curto que o backend sempre pediu (`drone`); o que ele
    vira está em `audiencias.SERVICOS`, e nome desconhecido é recusado."""
    if produto not in audiencias.SERVICOS:
        raise ValueError(f"Produto sem token de serviço: {produto!r}")
    audiencia, escopo = audiencias.SERVICOS[produto]
    ttl = ttl_seconds if ttl_seconds is not None else settings.SERVICE_TOKEN_TTL_SECONDS
    carga = _padrao(audiencia, timedelta(seconds=ttl))
    carga.update({
        "sub": f"svc-{caller}",
        "svc": True,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "scope": escopo,
    })
    return _assinar(carga, audiencias.TIPO_SERVICO)
