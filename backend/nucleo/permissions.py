from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsDataAdminOrStaff(BasePermission):
    """Allows access only to authenticated staff/superusers/data-admins."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "is_data_admin", False)
        )


class RequireModule(BasePermission):
    """Camada 1 — entitlement de módulo (genérico, reutilizável por QUALQUER app).

    Espelho do `MODULE_drone` do funcoesODM: o ViewSet declara
    ``required_module = "<codigo>"`` e o acesso só é liberado se esse código
    estiver no claim ``modules`` do JWT da IAM (interseção
    AssinaturaTenant ∩ AcessoUsuarioModulo). Caso contrário, **403**.
    Sem ``required_module`` declarado (apps base), não exige módulo.
    Ver docs/acesso-e-permissoes.md.
    """

    message = "Seu plano/usuário não inclui este módulo."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        required = getattr(view, "required_module", None)
        if not required:
            return True
        modules = getattr(user, "iam_modules", []) or []
        return required in modules


class RequireRole(BasePermission):
    """Camada 2 — RBAC por papel (genérico). O ViewSet declara
    ``required_role = "<papel>"`` (ou ``required_roles = [...]``); o acesso exige
    que o usuário tenha o papel no claim ``roles`` do JWT. Admin do tenant passa.
    """

    message = "Seu papel não tem acesso a este recurso."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        required = getattr(view, "required_roles", None)
        if not required:
            single = getattr(view, "required_role", None)
            required = [single] if single else []
        if not required:
            return True
        if getattr(user, "is_tenant_admin", False) or getattr(user, "is_superuser", False):
            return True
        roles = getattr(user, "iam_roles", []) or []
        return any(r in roles for r in required)
