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
from contextlib import contextmanager

from django.db import connection, models, transaction


def _set_config(key, value):
    """Grava um GUC de sessão com `is_local=true` (vale só até o fim da
    transação corrente). No-op fora do PostgreSQL. Requer estar dentro de uma
    transação — `ATOMIC_REQUESTS=True` garante isso em toda requisição; fora de
    request use os context managers abaixo (que abrem `atomic()`)."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [key, value or ""])


def arm_rls_for_tenant(tenant_id):
    """Arma o contexto RLS da requisição a partir do tenant do usuário.

    - tenant normal  → `app.current_tenant = <id>` (a política fail-closed só
      libera as linhas desse tenant);
    - superusuário (admin de plataforma) ou `None` de sistema → não é tratado
      aqui; use `arm_rls_bypass()` para os caminhos de plataforma.

    Fail-closed (migration `0010`): sessão sem `app.current_tenant` **não
    enxerga nenhuma** linha de negócio. No-op fora do Postgres.

    Armar um tenant concreto **desliga** qualquer bypass ativo: a semântica é
    "eu sou este tenant, aplique a política". Isso torna a função autocontida e
    remove a dependência de ordem — importante porque `SET LOCAL` tem escopo de
    transação (não de savepoint), então um bypass ligado num bloco anterior da
    mesma transação (ex.: seed sob `rls_bypass()` num `TestCase`) vazaria."""
    _set_config("app.rls_bypass", "off")
    _set_config("app.current_tenant", str(tenant_id) if tenant_id else "")


def arm_rls_bypass():
    """Liga o bypass explícito da RLS (`app.rls_bypass='on'`) — só para código
    de plataforma confiável que precisa cruzar tenants: admin de plataforma
    (superusuário), webhook do Asaas (localiza o boleto por `gateway_id` global),
    migrações de dados e jobs de manutenção. Vale só na transação corrente."""
    _set_config("app.rls_bypass", "on")


def clear_rls_context():
    """Zera tenant e bypass da transação corrente (fail-closed → 0 linhas)."""
    _set_config("app.current_tenant", "")
    _set_config("app.rls_bypass", "off")


@contextmanager
def tenant_context(tenant_id):
    """Executa um bloco com o contexto RLS de um tenant específico — para
    caminhos **fora de request** (Celery tasks, management commands, shell).
    Abre `atomic()` para garantir que o `set_config(is_local=true)` persista
    pelos statements do bloco."""
    with transaction.atomic():
        arm_rls_for_tenant(tenant_id)
        yield


@contextmanager
def rls_bypass():
    """Como `tenant_context`, mas liga o bypass de plataforma no bloco."""
    with transaction.atomic():
        arm_rls_bypass()
        yield


def arm_rls_for_request(user):
    """Arma o contexto RLS a partir do usuário autenticado da requisição:
    superusuário (admin de plataforma) → bypass; caso contrário, o tenant dele.
    Ponto único usado tanto pela autenticação (cobre TODA request, mesmo views
    que não herdam o mixin) quanto pelos mixins (defesa em profundidade)."""
    if user is not None and getattr(user, "is_superuser", False):
        arm_rls_bypass()
    else:
        arm_rls_for_tenant(getattr(user, "tenant_id", None))


def scope_queryset_by_tenant(queryset, user, tenant_field="tenant_id"):
    """Filtra `queryset` pelo tenant do `user`. Superusuário (admin de
    plataforma) vê tudo. Compartilhado pelos mixins de ViewSet e de APIView."""
    if user is None or getattr(user, "is_superuser", False):
        return queryset
    return queryset.filter(**{tenant_field: getattr(user, "tenant_id", None)})


class TenantScopedModel(models.Model):
    # `tenant` é OBRIGATÓRIO (Fase 8.2): toda linha de negócio pertence a um
    # tenant. O `perform_create` dos mixins injeta o tenant do usuário e a RLS
    # fail-closed barra qualquer INSERT sem contexto — a coluna NOT NULL é a
    # terceira camada (banco). Backfill de linhas legadas: migration de dados
    # antes do AlterField (ver nucleo/migrations).
    tenant = models.ForeignKey(
        "nucleo.Tenant",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
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
        arm_rls_for_request(getattr(request, "user", None))

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
        arm_rls_for_request(getattr(request, "user", None))

    def scope_qs(self, queryset):
        return scope_queryset_by_tenant(
            queryset, getattr(self.request, "user", None), self.tenant_field
        )
