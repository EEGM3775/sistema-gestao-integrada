"""Cookies HttpOnly da sessão: o do refresh (Fase 10.6 / F1) e o do BFF (fase 5).

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


def set_sessao_cookie(response, credencial: str, max_age: int, *, persistent: bool) -> None:
    """O cookie da sessão do BFF (fase 5, §10.5) — o que o navegador tem no
    lugar do token. Vai para **todo** caminho (`/`), porque é com ele que o
    gateway pede o access de `/api/`, `/odm-api/` e `/ws/`; o gateway o tira do
    pedido antes de repassá-lo aos serviços. Com HTTPS, o nome tem o prefixo
    `__Host-`, que o navegador só aceita com `Secure`, `Path=/` e sem `Domain`:
    nenhum subdomínio consegue plantar um cookie com esse nome.

    Mesma regra de persistência do refresh: sem "manter conectado", cookie de
    sessão do navegador; com, dura até o refresh expirar."""
    kwargs = dict(
        path="/",
        httponly=True,
        secure=settings.SESSAO_COOKIE_SECURE,
        samesite=settings.SESSAO_COOKIE_SAMESITE,
    )
    if persistent:
        kwargs["max_age"] = int(max_age)
    response.set_cookie(settings.SESSAO_COOKIE_NAME, credencial, **kwargs)


def clear_sessao_cookie(response) -> None:
    response.delete_cookie(
        settings.SESSAO_COOKIE_NAME, path="/", samesite=settings.SESSAO_COOKIE_SAMESITE,
    )
