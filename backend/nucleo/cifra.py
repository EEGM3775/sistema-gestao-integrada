# backend/nucleo/cifra.py
"""Cifra simétrica para segredos guardados no banco (chave de API de integração).

A chave de API da NFE.io passou a ser **por empresa** (decisão do dono,
10/10/2026: "como vou cadastrar minha API?"), e isso a tirou do cofre de
deploy (`/etc/sgi/segredos`) para uma linha do banco. Guardá-la em claro faria
de qualquer backup, réplica ou `SELECT` de suporte um vazamento da conta fiscal
do cliente. Fernet (AES-128-CBC + HMAC-SHA256, da `cryptography`) cifra e
autentica: um byte trocado no banco vira erro, não uma chave errada enviada.

A chave da cifra vem de `CHAVE_CIFRA_SEGREDOS` (ou do arquivo em
`CHAVE_CIFRA_SEGREDOS_FILE`, como os demais segredos do cofre); sem ela, é
derivada da `SECRET_KEY`. Trocar a chave torna ilegíveis os segredos gravados —
e `decifrar` devolve vazio em vez de quebrar a tela: a empresa recadastra.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _material() -> bytes:
    caminho = os.getenv("CHAVE_CIFRA_SEGREDOS_FILE")
    if caminho and os.path.exists(caminho):
        with open(caminho, "rb") as arquivo:
            bruto = arquivo.read().strip()
    else:
        bruto = (os.getenv("CHAVE_CIFRA_SEGREDOS") or settings.SECRET_KEY).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(b"sgi-segredos:" + bruto).digest())


def cifrar(texto: str) -> str:
    if not texto:
        return ""
    return Fernet(_material()).encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    if not token:
        return ""
    try:
        return Fernet(_material()).decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
