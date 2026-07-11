"""
Autenticação do ERP como *resource server* da IAM.

O ERP não emite mais identidade: ele valida o JWT assinado pela IAM (segredo
compartilhado) e provisiona (JIT) um espelho local de Tenant/Usuário a partir
das claims, preservando as FKs locais que apontam para `nucleo.Usuario`.
Ver docs/arquitetura.md (Fase 0.3).
"""
import logging

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import Tenant
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

        self._sync_user(user, validated_token, tenant)

        # Claims voláteis, disponíveis para permissões/escopo na request.
        user.iam_modules = validated_token.get("modules", []) or []
        user.iam_roles = validated_token.get("roles", []) or []
        # `permissions` (Fase 9.B): conjunto efetivo p/ RequirePermission. Vazio em
        # tokens antigos → RequireRole segue como fallback durante a transição.
        user.iam_permissions = validated_token.get("permissions", []) or []
        # Dono da plataforma (superuser da IAM) — confirma incidente LGPD (Fase 9.D).
        user.is_platform_admin = bool(validated_token.get("is_platform_admin"))
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
