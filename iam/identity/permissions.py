from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    """Administrador da plataforma (superuser) — gere tenants/módulos/assinaturas."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsTenantAdmin(BasePermission):
    """Administrador do próprio tenant — gere usuários/perfis/acessos do tenant."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_tenant_admin or u.is_superuser))
