"""Ajudas dos testes da IAM para a sessão do BFF (fases 5 e 6 da remodelagem).

Desde a fase 5 o corpo do login não traz token: o navegador fica com o cookie da
sessão, e quem recebe o access é o serviço, pelo gateway. Estes testes pedem o
access como o gateway pede (`/auth/interno/bff/<serviço>/`, com os cookies do
`APIClient`) e o leem sem conferir a assinatura — o que se cobra aqui é o
conteúdo; a assinatura tem teste próprio (`decodificar`).
"""
import base64
import json
import time

import jwt
from django.conf import settings


def carga(token) -> dict:
    parte = str(token).split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


def cabecalho(token) -> dict:
    return jwt.get_unverified_header(str(token))


def access_do_bff(client, servico="api", **extra):
    """O `Authorization` que o gateway injetaria, sem o `Bearer ` — ou `None`."""
    r = client.get(f"/auth/interno/bff/{servico}/", **extra)
    valor = r.get("X-BFF-Authorization", "") if r.status_code == 204 else ""
    return valor.removeprefix("Bearer ") or None


def decodificar(token, audiencia) -> dict:
    """Confere assinatura, `exp` e `aud` com a chave da plataforma."""
    cfg = settings.SIMPLE_JWT
    chave = cfg.get("VERIFYING_KEY") or cfg["SIGNING_KEY"]
    return jwt.decode(str(token), chave, algorithms=[cfg["ALGORITHM"]], audience=audiencia)


def confirmado_agora(client, usuario):
    """Autentica com uma prova de identidade de agora — para os testes em que o
    ato grave (papel, acesso a módulo) não é o que se testa. O step-up tem os
    testes dele (`test_step_up.py`)."""
    client.force_authenticate(usuario, token={"auth_time": int(time.time())})
