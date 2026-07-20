# backend/funcoeswhatsapp/security.py
"""
Autenticação da borda do webhook (Fase C, §4.6): assinatura HMAC da Meta.

O webhook é **inbound e público** — não há JWT de usuário. A Meta assina o corpo
com o **app secret do tenant** (`X-Hub-Signature-256: sha256=<hex>`); validamos em
tempo constante (`hmac.compare_digest`). Porte fiel do controller Node (já correto
lá). Sem app secret configurado → **fail-closed** (recusa).
"""
import hashlib
import hmac


def assinatura_valida(app_secret, corpo_bruto, header_assinatura):
    """`True` se `header_assinatura` bate o HMAC-SHA256 de `corpo_bruto` com o
    `app_secret`. Fail-closed: segredo ou header ausente → `False`."""
    if not app_secret or not header_assinatura:
        return False
    if not header_assinatura.startswith('sha256='):
        return False
    esperado = hmac.new(
        app_secret.encode('utf-8'),
        corpo_bruto,
        hashlib.sha256,
    ).hexdigest()
    recebido = header_assinatura.split('=', 1)[1]
    return hmac.compare_digest(esperado, recebido)
