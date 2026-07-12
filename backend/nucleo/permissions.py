from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission


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
    """Camada 2 — RBAC por papel (**depreciado**, Fase 9.B). Mantido durante a
    transição: `RequirePermission` cai aqui quando o token não traz `permissions`
    (legado). Alvo (fatia E): remover, deixando só a checagem por permissão.

    O ViewSet declara ``required_role``/``required_roles``; o acesso exige o papel
    no claim ``roles`` do JWT. Admin do tenant passa.
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


class RequirePermission(BasePermission):
    """Camada 2 (Fase 9.B) — checagem por **permissão** (claim ``permissions`` do
    JWT), substitui `RequireRole`. Lê o catálogo `modulo.recurso.acao` da IAM.
    O ViewSet declara UMA das formas:

      - ``required_resource = "rh.dado_medico"`` — atalho: métodos seguros exigem
        ``.view``; métodos de escrita exigem ``.edit`` (o comum p/ um CRUD de PII);
      - ``permission_map = {"view": "...view", "write": "...emitir"}`` — por método,
        quando a escrita não é ``.edit`` (verbos de domínio);
      - ``action_permission_map = {"dar_baixa": "erp.conta_receber.baixar", …}`` —
        por **ação** do DRF (``view.action``), p/ verbos de domínio em `@action`
        que exigem uma permissão diferente do CRUD do próprio recurso (tem
        precedência sobre `permission_map`/`required_resource`);
      - ``required_permission = "modulo.recurso.acao"`` — fixa p/ todas as ações.

    Admin de tenant / superuser passam. Sem declaração → não exige (apps base).

    **Transição (D4, fail-closed):** só o token **legado** — claim `permissions`
    **ausente** (a autenticação seta `iam_permissions = None`) — cai no `RequireRole`
    do ViewSet (que segue declarando ``required_role``). Um token da **era das
    permissões** com conjunto **vazio** (`[]`) é negado sem fallback: sem isso, um
    usuário sem nenhuma permissão passaria em endpoints sem `required_role`.
    """

    message = "Você não tem permissão para esta ação."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        needed = self._needed(request, view)
        if not needed:
            return True
        if getattr(user, "is_tenant_admin", False) or getattr(user, "is_superuser", False):
            return True
        perms = getattr(user, "iam_permissions", None)
        # D4 — fail-closed: `None` = claim ausente (token legado) → fallback de
        # transição por papel; lista (mesmo VAZIA) = era das permissões → estrito.
        if perms is None:
            return RequireRole().has_permission(request, view)
        return needed in perms

    def _needed(self, request, view):
        # Verbo de domínio por ação (ex.: dar_baixa → erp.conta_receber.baixar) —
        # precede o CRUD do recurso. `view.action` existe só em ViewSet.
        action_map = getattr(view, "action_permission_map", None)
        action = getattr(view, "action", None)
        if action_map and action in action_map:
            return action_map[action]
        pm = getattr(view, "permission_map", None)
        if pm:
            chave = "view" if request.method in SAFE_METHODS else "write"
            return pm.get(chave)
        recurso = getattr(view, "required_resource", None)
        if recurso:
            sufixo = "view" if request.method in SAFE_METHODS else "edit"
            return f"{recurso}.{sufixo}"
        return getattr(view, "required_permission", None)
