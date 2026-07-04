"""
Utilitários de multi-tenancy do ERP.

- `TenantScopedModel`: base abstrata para entidades de negócio isoladas por
  tenant (adiciona o FK `tenant`).
- `TenantScopedViewSetMixin`: filtra o queryset pelo tenant do usuário e injeta
  o tenant ao criar. Defesa-em-profundidade adicional via RLS (Fase 0.3d).
- `TenantScopedAPIViewMixin`: mesmo isolamento para `APIView`s puras (que não
  têm `get_queryset`/`filter_queryset`) — arma a RLS em `initial()` e escopa
  cada queryset via `scope_qs()`. Correção do achado S1 (dashboard/NF cruzavam
  tenants por serem `APIView` fora do mixin de ViewSet).
"""
from django.db import connection, models


def arm_rls_for_tenant(tenant_id):
    """Define `app.current_tenant` para a RLS do PostgreSQL (defesa em
    profundidade — Fase 0.3d). No-op fora do Postgres. Requer
    `ATOMIC_REQUESTS=True` para que `set_config(..., is_local=true)` valha por
    toda a requisição."""
    if tenant_id and connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_tenant', %s, true)", [str(tenant_id)]
            )


def scope_queryset_by_tenant(queryset, user, tenant_field="tenant_id"):
    """Filtra `queryset` pelo tenant do `user`. Superusuário (admin de
    plataforma) vê tudo. Compartilhado pelos mixins de ViewSet e de APIView."""
    if user is None or getattr(user, "is_superuser", False):
        return queryset
    return queryset.filter(**{tenant_field: getattr(user, "tenant_id", None)})


class TenantScopedModel(models.Model):
    tenant = models.ForeignKey(
        "nucleo.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="+",
    )

    class Meta:
        abstract = True


class TenantScopedViewSetMixin:
    """
    Aplica isolamento por tenant em ViewSets do DRF. Superusuário (admin de
    plataforma) vê tudo.

    Escopa em DOIS pontos para cobrir todos os caminhos, mesmo quando o ViewSet
    sobrescreve `get_queryset` sem chamar `super()`:
    - `get_queryset`: pega `list()` customizados que chamam `self.get_queryset()`.
    - `filter_queryset`: pega o caminho padrão de `list()` e de `get_object()`
      (detail/update/destroy). Filtrar duas vezes pelo mesmo tenant é idempotente.

    Escrita: `perform_create` injeta o tenant do usuário; `perform_update`
    reforça o tenant (impede mover um registro para outro tenant via payload).
    A defesa final é a RLS do PostgreSQL (Fase 0.3d).
    """

    tenant_field = "tenant_id"

    def initial(self, request, *args, **kwargs):
        """Após a autenticação, define o tenant da requisição para a RLS do
        PostgreSQL (defesa em profundidade). Requer ATOMIC_REQUESTS=True para que
        set_config(..., is_local=true) valha por toda a requisição."""
        super().initial(request, *args, **kwargs)
        arm_rls_for_tenant(getattr(getattr(request, "user", None), "tenant_id", None))

    def _scope(self, queryset):
        return scope_queryset_by_tenant(
            queryset, getattr(self.request, "user", None), self.tenant_field
        )

    def get_queryset(self):
        return self._scope(super().get_queryset())

    def filter_queryset(self, queryset):
        return self._scope(super().filter_queryset(queryset))

    def perform_create(self, serializer):
        serializer.save(tenant_id=getattr(getattr(self.request, "user", None), "tenant_id", None))

    def perform_update(self, serializer):
        user = getattr(self.request, "user", None)
        tid = getattr(user, "tenant_id", None)
        if tid and not getattr(user, "is_superuser", False):
            serializer.save(tenant_id=tid)
        else:
            serializer.save()


class TenantScopedAPIViewMixin:
    """
    Isolamento por tenant para `APIView`s puras (que não têm o `get_queryset`/
    `filter_queryset` do ViewSet). Espelha o `TenantScopedViewSetMixin`:

    - `initial()` arma a RLS do PostgreSQL (defesa em profundidade);
    - `scope_qs()` filtra um queryset pelo tenant do usuário (superusuário vê
      tudo) — chame-o em CADA queryset lido/gravado pela view.

    Correção do achado S1: views de dashboard e de NF eram `APIView` puras, logo
    liam/gravavam dados de qualquer tenant.
    """

    tenant_field = "tenant_id"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        arm_rls_for_tenant(getattr(getattr(request, "user", None), "tenant_id", None))

    def scope_qs(self, queryset):
        return scope_queryset_by_tenant(
            queryset, getattr(self.request, "user", None), self.tenant_field
        )
