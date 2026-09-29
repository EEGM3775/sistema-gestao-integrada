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


def claims_de_acesso(user):
    """O que o token carregava até a fase 4: listas de acesso, papéis e plano.

    Continua existindo por dois motivos: é o corpo do `/auth/me/` (a tela
    esconde o que a pessoa não pode, e lê isto uma vez — não a cada requisição)
    e é a **volta atrás** da fase 4 (§10.12, "reemitir claims antigas por
    flag"): com `AUTORIZACAO_TOKEN_COM_LISTAS`, `build_claims` as põe de novo no
    token, e os serviços voltam a poder decidir por elas.

    `rate_hora`, `plano` e `quotas` são da empresa, não da pessoa: fora do token
    eles chegam ao backend pela ficha da empresa (`identity/fichas.py`).
    """
    tenant = user.tenant
    claims = {
        "email": user.email,
        "tenant_slug": tenant.slug if tenant else None,
        "roles": user.nomes_perfis(),
        "permissions": user.permissoes_efetivas(),
        "modules": user.modulos_efetivos(),
        "is_tenant_admin": user.is_tenant_admin,
        "is_platform_admin": user.is_superuser,
    }
    if tenant:
        claims.update(dados_do_plano(tenant))
    return claims


def dados_do_plano(tenant) -> dict:
    """Plano, teto de requisições (D23) e quotas de objeto (D24) do tenant —
    quem sabe o que foi CONTRATADO é a IAM; o backend conta o que foi usado."""
    contratados = tenant.limites_contratados()
    return {
        "plano": plano_valido(tenant.plano),
        CLAIM_REQUISICOES_HORA: teto_requisicoes_hora(tenant.plano, contratados),
        CLAIM_QUOTAS: quotas_efetivas(tenant.plano, contratados),
    }


def build_claims(user):
    """As claims que a IAM acrescenta ao token — **quem é, e mais nada** (§10.6).

    Fase 4 da remodelagem: o token prova quem é, não o que pode. Fica `sub`
    (lido pelo drone para o espelho local) e `tenant_id` (a empresa da sessão,
    que confere com a RLS e com a relação no PDP). A sessão (`sid`), o início
    dela (`sst`), a força (`amr`) e a idade da autenticação (`auth_time`) vêm do
    refresh (`issue_refresh`). O "pode?" é do PDP; o tamanho do token não
    depende mais do catálogo (D194).
    """
    tenant = user.tenant
    claims = {
        "sub": user.username,
        "tenant_id": str(tenant.id) if tenant else None,
    }
    if getattr(settings, "AUTORIZACAO_TOKEN_COM_LISTAS", False):
        claims.update(claims_de_acesso(user))
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


def issue_refresh(user, *, remember: bool, sst: int | None = None,
                  amr: list[str] | None = None, sid=None,
                  auth_time: int | None = None) -> RefreshToken:
    """Emite um refresh token **mínimo**: só `user_id` (padrão do SimpleJWT) +
    metadados de sessão. O SimpleJWT copia estes metadados para o access
    (`refresh.access_token`), e é por isso que o access leva `sid`, `amr` e
    `auth_time` sem que `build_claims` os repita.

    `sst` (session start time) marca o início da sessão e é **preservado nas
    rotações** → serve ao teto absoluto. `rem` guarda se é sessão "lembrada"
    (define a validade deslizante em cada rotação).

    `amr` (RFC 8176) diz **como** a sessão provou quem é: `["pwd"]` só senha,
    `["pwd", "otp"]` senha e segundo fator. É preservado nas rotações, como o
    `sst`, e o SimpleJWT o copia para o access. O refresh recusa a sessão sem
    `otp` de quem tem ou é obrigado a ter segundo fator (`RefreshView`).

    `sid` é a sessão (`identity.sessoes`): sem ele, é login — abre uma sessão
    nova; na rotação, o chamador passa o da sessão que continua. `auth_time`
    (RFC 9470) é quando a pessoa provou quem é pela última vez: nasce no login,
    atravessa as rotações, e só a confirmação (step-up) o renova.
    """
    from . import sessoes

    agora = int(timezone.now().timestamp())
    token = RefreshToken.for_user(user)
    token["sst"] = int(sst) if sst else agora
    token["rem"] = bool(remember)
    token["amr"] = list(amr) if amr else ["pwd"]
    token["sid"] = str(sid) if sid else str(sessoes.abrir(user).sid)
    token["auth_time"] = int(auth_time) if auth_time else agora
    _aplicar_validade(token, remember)
    return token


def access_with_claims(refresh: RefreshToken, user):
    """Access token derivado do refresh + claims da plataforma. É o que os
    resource servers (backend, drone) consomem; vale `ACCESS_TOKEN_LIFETIME` (5 min)."""
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
    # O entitlement do produto-alvo, e só ele: token de serviço não tem pessoa
    # para o PDP responder, então decide pela claim (a separação por tipo e
    # audiência é a fase 5).
    token["modules"] = [audience]
    return str(token)


def cookie_max_age(token) -> int:
    """Segundos até o refresh expirar — para casar o `Max-Age` do cookie."""
    return max(0, int(token.payload["exp"]) - int(timezone.now().timestamp()))


def revoke_all_sessions(user, *, motivo: str = "encerrar_todas") -> int:
    """Encerra TODAS as sessões do usuário: blacklista cada refresh token vivo
    (rotacionável) dele e revoga cada `sid` (fase 4) — o access já emitido cai
    na requisição seguinte em todo serviço, e não quando expira. Quem troca a
    própria senha recebe uma sessão nova logo depois. Retorna quantos refresh
    foram revogados."""
    from . import sessoes

    sessoes.revogar_todas(user, motivo)
    # Import tardio: os modelos do blacklist exigem apps carregados.
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    n = 0
    for ot in OutstandingToken.objects.filter(user_id=user.id):
        _, criado = BlacklistedToken.objects.get_or_create(token=ot)
        n += int(criado)
    return n
