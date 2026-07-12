"""Cookie HttpOnly do refresh token (Fase 10.6 / F1).

O refresh nunca aparece no corpo da resposta nem em `localStorage` — vive só num
cookie HttpOnly (imune a XSS), com path restrito a `/auth/` (não vaza para `/api`)
e `SameSite=Strict` (bloqueia envio cross-site → defesa de CSRF). `Secure` sob
HTTPS (produção, via `IAM_COOKIE_SECURE=1`).
"""
from django.conf import settings


def set_refresh_cookie(response, token_str: str, max_age: int, *, persistent: bool = True) -> None:
    """Grava o cookie do refresh.

    `persistent=True` (sessão "lembrada") → cookie com `Max-Age` → sobrevive a
    fechar o navegador / desligar o PC, até o prazo (30d).
    `persistent=False` (sem "manter conectado") → **cookie de sessão** (sem
    `Max-Age`/`Expires`) → o navegador o descarta ao fechar → exige novo login.
    Em ambos, o token tem expiração no servidor como backstop (12h/30d)."""
    kwargs = dict(
        path=settings.REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )
    if persistent:
        kwargs["max_age"] = int(max_age)
    response.set_cookie(settings.REFRESH_COOKIE_NAME, token_str, **kwargs)


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )
