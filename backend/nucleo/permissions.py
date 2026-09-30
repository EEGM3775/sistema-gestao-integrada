from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import autorizacao


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
        return autorizacao.usa_modulo(user, required)


class RequirePermission(BasePermission):
    """Camada 2 (Fase 9.B) — checagem por **permissão** (claim ``permissions`` do
    JWT). Lê o catálogo `modulo.recurso.acao` da IAM.
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

    **Fail-closed (D4 / fatia E):** a checagem é sempre estrita — a permissão
    exigida tem de estar no conjunto do token, senão **403**. Não há fallback por
    papel: todo token da IAM traz a claim `permissions` (Fase 9.A), logo conjunto
    ausente/vazio nega tudo.
    """

    message = "Você não tem permissão para esta ação."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        needed = self._needed(request, view)
        if not needed:
            return True
        # Fail-closed: sem a permissão, nega. O admin do tenant e o superusuário
        # local passam — a regra mora em `nucleo/autorizacao.py`, que decide pelo
        # token ou pelo PDP conforme o módulo (remodelagem, fase 3).
        if not autorizacao.pode(user, needed):
            return False
        # Fase 6: o ato da classe C (pagar, atestar, exportar dado pessoal...)
        # pede autenticação recente — senão, 401 com o desafio do step-up.
        autorizacao.exigir_confirmacao(user, needed)
        return True

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
