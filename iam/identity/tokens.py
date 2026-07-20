"""Claims do JWT emitido pela IAM e consumido por todos os produtos."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from payment.regras import (
    CLAIM_QUOTAS,
    CLAIM_REQUISICOES_HORA,
    plano_valido,
    quotas_efetivas,
    teto_requisicoes_hora,
)


def build_claims(user):
    """Claims customizadas que viajam no access/refresh token.

    `sub`=username é lido pelo funcoesODM (Java) para buscar/provisionar o
    usuário; `tenant_id` dá o isolamento; `modules` carrega os entitlements.

    D23 — `rate_hora` e `plano`: o teto de requisições do tenant viaja como claim
    pelo mesmo motivo que `permissions` viaja. A IAM é a única que sabe quantos
    seats a empresa contratou (o `Usuario` do backend é espelho JIT: só existe
    quem já logou, então contar lá daria um número menor e crescente durante a
    implantação). Propagação: vale no próximo refresh (≤ TTL do access), igual à
    mudança de permissão.
    """
    tenant = user.tenant
    claims = {
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
    if tenant:
        contratados = tenant.limites_contratados()
        claims["plano"] = plano_valido(tenant.plano)
        claims[CLAIM_REQUISICOES_HORA] = teto_requisicoes_hora(tenant.plano, contratados)
        # D24 — quotas de objeto: viajam pelo mesmo motivo que `rate_hora`. Os
        # objetos (obra, cliente…) são contados no backend, mas quem sabe o que
        # foi CONTRATADO é a IAM. Mandar o teto junto do token evita que o
        # backend precise consultar a IAM a cada criação — um hop de rede no
        # caminho de escrita, que cairia junto com ela.
        claims[CLAIM_QUOTAS] = quotas_efetivas(tenant.plano, contratados)
    return claims


def _aplicar_validade(token, remember: bool) -> None:
    """Ajusta o `exp` do refresh conforme a sessão, limitado ao teto absoluto
    desde o início da sessão (`sst`):

    - **sem "lembrar"**: janela DESLIZANTE de inatividade (2h) — cada rotação
      renova, então quem está trabalhando não cai — com teto absoluto de 12h
      desde o início da sessão. A rotação só acontece se houver interação real
      do usuário (o front para de renovar quando ocioso), senão a janela de
      inatividade nunca fecharia com a aba aberta;
    - **com "lembrar"**: 7d deslizantes (cada rotação renova), teto absoluto 30d —
      o teto é o que garante que uma sessão roubada morre mesmo sem ninguém notar.
    """
    lifetime = settings.SESSION_REMEMBER if remember else settings.SESSION_IDLE
    token.set_exp(lifetime=lifetime)
    cap = settings.SESSION_ABS_CAP if remember else settings.SESSION_IDLE_CAP
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
    resource servers (backend, drone) consomem; vale `ACCESS_TOKEN_LIFETIME` (15 min)."""
    access = refresh.access_token
    for chave, valor in build_claims(user).items():
        access[chave] = valor
    return access


def issue_service_token(*, caller: str, tenant_id: str, audience: str = "drone",
                        ttl_seconds: int | None = None) -> str:
    """JWT **serviço→serviço** de vida curta (Fase 10.8), assinado com a mesma
    chave da plataforma (RS256 em produção / HS256 em dev) → os resource servers
    (backend, drone) o validam **exatamente** como um access de usuário.

    Diferente do access de usuário: não representa uma pessoa — não carrega
    `user_id` (logo a checagem de revogação por época é no-op: não há sessão a
    revogar) e vem sem permissões/papéis. Carrega só o mínimo que a borda do
    produto-alvo exige: `sub` de serviço (`svc-<caller>`, provisionado JIT no
    drone), o `tenant_id` a que a ação se restringe e o `modules` com o
    entitlement do produto (ex.: `drone`), para passar no gate de módulo.

    Usado hoje pelo backend ao excluir obra/empreendimento, para desvincular
    (soft) no drone os projetos órfãos daquele tenant (pendência da Fase 3).
    """
    token = AccessToken()
    ttl = ttl_seconds if ttl_seconds is not None else settings.SERVICE_TOKEN_TTL_SECONDS
    token.set_exp(lifetime=timedelta(seconds=ttl))
    token["sub"] = f"svc-{caller}"
    token["svc"] = True  # marcador: é um token de serviço, não de usuário
    token["tenant_id"] = str(tenant_id) if tenant_id else None
    token["tenant_slug"] = None
    token["email"] = None
    token["roles"] = []
    token["permissions"] = []
    token["modules"] = [audience]
    token["is_tenant_admin"] = False
    token["is_platform_admin"] = False
    return str(token)


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
