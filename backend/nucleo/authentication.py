"""
Autenticação do backend como *resource server* da IAM.

O backend não emite mais identidade: ele valida o JWT assinado pela IAM (segredo
compartilhado) e provisiona (JIT) um espelho local de Tenant/Usuário a partir
das claims, preservando as FKs locais que apontam para `nucleo.Usuario`.
Ver docs/arquitetura.md (Fase 0.3).
"""
import logging

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import Tenant
from .revocation import is_session_revoked
from .tenancy import arm_rls_for_request

logger = logging.getLogger(__name__)
User = get_user_model()


class IamJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        """Além de validar o JWT, **arma o contexto RLS** assim que o usuário é
        resolvido. Como isto roda em `initial()` → dentro da transação do
        `ATOMIC_REQUESTS`, o `set_config(is_local=true)` vale por toda a
        requisição — cobrindo TODA view autenticada, mesmo as que não herdam o
        `TenantScopedViewSetMixin` (foi a brecha do S1). Com a política
        fail-closed (migration 0010), esquecer o mixin deixa de vazar dados: sem
        contexto, a RLS não devolve linha alguma."""
        resultado = super().authenticate(request)
        if resultado is not None:
            user, _token = resultado
            arm_rls_for_request(user)
        return resultado

    def get_user(self, validated_token):
        username = validated_token.get("sub") or validated_token.get("username")
        if not username:
            raise InvalidToken("Token sem claim 'sub' (username).")

        # Revogação imediata (Fase 9.E / 10.7): a IAM carimba `revoked_after` no
        # Redis ao trocar/resetar senha ou desativar o usuário. Rejeita aqui o
        # access residual (stateless) emitido antes do carimbo — fecha a janela de
        # ≤ access TTL. Fail-open por padrão (ver nucleo/revocation.py).
        if is_session_revoked(validated_token.get("user_id"), validated_token.get("iat")):
            raise InvalidToken("Sessão revogada (senha alterada ou usuário desativado).")

        tenant = self._sync_tenant(validated_token)

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": validated_token.get("email") or "",
                "tenant": tenant,
                "is_tenant_admin": bool(validated_token.get("is_tenant_admin")),
            },
        )
        if created:
            user.set_unusable_password()  # autenticação é sempre via IAM
            user.save(update_fields=["password"])

        # D12 — espelho local desativado não autentica. Este `get_user` substitui
        # o do SimpleJWT, que barra usuário inativo; sem repetir a checagem aqui,
        # desativar o espelho no backend não tinha efeito nenhum e a conta seguia
        # entrando. (A desativação na IAM continua chegando pela revogação por
        # época, acima; esta é a trava do lado de cá.)
        if not user.is_active:
            raise InvalidToken("Usuário inativo neste produto.")

        self._sync_user(user, validated_token, tenant)

        # Quem é a pessoa para o PDP (`usuario:<id da IAM>`), de qual empresa é
        # esta sessão e quando o token nasceu — é o que a sombra usa para dizer
        # se uma divergência é o token velho ou um defeito (nucleo/autorizacao.py).
        user.iam_user_id = validated_token.get("user_id")
        user.iam_tenant_id = validated_token.get("tenant_id")
        user.iam_token_iat = validated_token.get("iat")

        # Claims voláteis. **Só `nucleo/autorizacao.py` as lê** (cobrado por
        # teste): toda pergunta "pode?" passa por lá.
        user.iam_modules = validated_token.get("modules", []) or []
        user.iam_roles = validated_token.get("roles", []) or []
        # `permissions` (Fase 9.B): conjunto efetivo p/ RequirePermission. Desde a
        # fatia E não há mais fallback por papel — todo token da IAM traz a claim;
        # ausente/vazia → conjunto vazio → RequirePermission nega (fail-closed).
        user.iam_permissions = list(validated_token.get("permissions") or [])
        # Dono da plataforma (superuser da IAM) — confirma incidente LGPD (Fase 9.D).
        user.is_platform_admin = bool(validated_token.get("is_platform_admin"))
        # D23 — teto de requisições/hora do tenant, derivado do plano contratado.
        # Vem da IAM porque é ela que conhece os seats: o `Usuario` daqui é espelho
        # JIT (só quem já logou), então contar localmente daria um teto menor que o
        # contratado e crescente durante a implantação do cliente. Ausente (token de
        # serviço, token legado) → o throttle cai no default do settings.
        user.iam_rate_hora = validated_token.get("rate_hora")
        user.iam_plano = validated_token.get("plano")
        # D24 — quotas de objeto do plano contratado (`{"obras": 8, ...}`), pela
        # mesma razão do `rate_hora`: a IAM é quem sabe o que foi contratado, o
        # backend é quem sabe quanto já foi usado. Ausente → `nucleo/quotas.py`
        # não trava nada (fail-open ruidoso; ver o módulo).
        user.iam_quotas = validated_token.get("quotas")
        return user

    def _sync_tenant(self, validated_token):
        tid = validated_token.get("tenant_id")
        if not tid:
            return None
        slug = validated_token.get("tenant_slug") or str(tid)
        tenant, _created = Tenant.objects.get_or_create(
            id=tid, defaults={"slug": slug, "nome": slug}
        )
        if tenant.slug != slug:
            tenant.slug = slug
            tenant.save(update_fields=["slug", "data_sincronizacao"])
        return tenant

    def _sync_user(self, user, validated_token, tenant):
        campos = []
        email = validated_token.get("email")
        if email and user.email != email:
            user.email = email
            campos.append("email")
        if tenant and user.tenant_id != tenant.id:
            user.tenant = tenant
            campos.append("tenant")
        is_admin = bool(validated_token.get("is_tenant_admin"))
        if user.is_tenant_admin != is_admin:
            user.is_tenant_admin = is_admin
            campos.append("is_tenant_admin")
        if campos:
            user.save(update_fields=campos)
