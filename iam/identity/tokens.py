"""Claims do JWT emitido pela IAM e consumido por todos os produtos."""

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken


def build_claims(user):
    """Claims customizadas que viajam no access/refresh token.

    `sub`=username é lido pelo funcoesODM (Java) para buscar/provisionar o
    usuário; `tenant_id` dá o isolamento; `modules` carrega os entitlements.
    """
    tenant = user.tenant
    return {
        "sub": user.username,
        "email": user.email,
        "tenant_id": str(tenant.id) if tenant else None,
        "tenant_slug": tenant.slug if tenant else None,
        "roles": user.nomes_perfis(),
        "permissions": user.permissoes_efetivas(),
        "modules": user.modulos_efetivos(),
        "is_tenant_admin": user.is_tenant_admin,
        "is_platform_admin": user.is_superuser,
    }


def _aplicar_validade(token, remember: bool) -> None:
    """Ajusta o `exp` do refresh conforme a sessão, limitado ao teto absoluto
    desde o início da sessão (`sst`):

    - **sem "lembrar"**: 12h fixas (cap = 12h → nem a rotação estende além disso);
    - **com "lembrar"**: 30d deslizantes (cada rotação renova), teto absoluto 90d.
    """
    lifetime = settings.SESSION_REMEMBER if remember else settings.SESSION_SHORT
    token.set_exp(lifetime=lifetime)
    cap = settings.SESSION_ABS_CAP if remember else settings.SESSION_SHORT
    cap_end = int(token["sst"]) + int(cap.total_seconds())
    if token.payload["exp"] > cap_end:
        token.payload["exp"] = cap_end


def issue_refresh(user, *, remember: bool, sst: int | None = None) -> RefreshToken:
    """Emite um refresh token **mínimo**: só `user_id` (padrão do SimpleJWT) +
    metadados de sessão. As claims pesadas (`permissions`/`roles`/`modules`) NÃO
    entram aqui — senão o token (que vai num cookie) estouraria o limite de ~4KB
    de cookie do browser e o buffer de header do nginx. Elas ficam só no access
    token (ver `access_with_claims`), que trafega no corpo/`Authorization`.

    `sst` (session start time) marca o início da sessão e é **preservado nas
    rotações** → serve ao teto absoluto. `rem` guarda se é sessão "lembrada"
    (define a validade deslizante em cada rotação).
    """
    token = RefreshToken.for_user(user)
    token["sst"] = int(sst) if sst else int(timezone.now().timestamp())
    token["rem"] = bool(remember)
    _aplicar_validade(token, remember)
    return token


def access_with_claims(refresh: RefreshToken, user):
    """Access token derivado do refresh + claims da plataforma. É o que os
    resource servers (ERP, drone) consomem; vale `ACCESS_TOKEN_LIFETIME` (15 min)."""
    access = refresh.access_token
    for chave, valor in build_claims(user).items():
        access[chave] = valor
    return access


def cookie_max_age(token) -> int:
    """Segundos até o refresh expirar — para casar o `Max-Age` do cookie."""
    return max(0, int(token.payload["exp"]) - int(timezone.now().timestamp()))


def revoke_all_sessions(user, *, exceto_jti: str | None = None) -> int:
    """Encerra TODAS as sessões do usuário: blacklista cada refresh token vivo
    (rotacionável) dele. `exceto_jti` preserva uma sessão (ex.: o dispositivo que
    está trocando a própria senha). Os access tokens curtos (15 min) não são
    revogáveis, mas expiram logo — os outros dispositivos caem em ≤15 min ao não
    conseguir renovar. Retorna quantas sessões foram revogadas."""
    # Import tardio: os modelos do blacklist exigem apps carregados.
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    n = 0
    for ot in OutstandingToken.objects.filter(user_id=user.id):
        if exceto_jti and ot.jti == exceto_jti:
            continue
        _, criado = BlacklistedToken.objects.get_or_create(token=ot)
        n += int(criado)
    return n
