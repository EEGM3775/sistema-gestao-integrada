"""
Utilitários de multi-tenancy do backend.

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

from django.conf import settings
from django.db import connection, models, transaction
from django.utils.translation import gettext_lazy as _


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
    # Observabilidade (Fase 10.1): este é o ponto único onde o tenant da
    # requisição fica conhecido — registra-o no contexto de logging para que
    # toda linha emitida depois carregue o `tenant_id` (correlação).
    _set_log_tenant(tenant_id)


def _set_log_tenant(tenant_id):
    """Propaga o tenant para o contexto de logging sem acoplar a tenancy ao
    módulo de observabilidade (import preguiçoso, tolerante)."""
    try:
        from .observability import set_tenant_id

        set_tenant_id(tenant_id)
    except Exception:  # noqa: BLE001 - logging nunca pode quebrar a tenancy
        pass


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

    def perform_destroy(self, instance):
        """`DELETE` em quem é `Excluivel` **marca a lápide**; nos demais, apaga.

        É aqui que a lixeira chega aos módulos sem que nenhum deles saiba dela:
        os 118 ViewSets da casa já passam por este mixin, e quem herdar
        `Excluivel` no modelo muda de comportamento sozinho. O módulo não importa
        o `nucleo/lixo.py` — o `nucleo` é que é importado por todos.

        O motivo vem por query param porque `DELETE` não carrega corpo em boa
        parte dos clientes HTTP; é opcional, e a tela manda o que o usuário
        digitou no modal de confirmação.
        """
        from .lixo import mover_para_lixo

        if isinstance(instance, Excluivel):
            mover_para_lixo(
                instance,
                usuario=getattr(self.request, "user", None),
                motivo=(self.request.query_params.get("motivo") or "").strip(),
            )
        else:
            instance.delete()


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


# ---------------------------------------------------------------------------
# A lápide — exclusão reversível de plataforma (D116)
# ---------------------------------------------------------------------------
# > **Decisão do dono, 23/08/2026:** *"Coloca como «Obra excluída por «usuário»
# > na data xx/xx/xx». Deixa o plano para poder ser usado como modelo em outra
# > obra."* · **13/09/2026:** *"O lixo é uma página à parte. Como é custo para o
# > programa, terá uma paywall. O lixo é apagado depois de 15 dias. O lixo pode
# > ser restaurado através da página de lixo."*
#
# São **duas etapas**, e é isso que resolve o nó do D116:
#
#   1. **Excluir marca a lápide.** A linha continua no banco, fora de toda
#      listagem, e o objeto inteiro — cronograma, orçamento, apontamento, título
#      no ERP — continua de pé. Restaurar é limpar a marca: não há payload para
#      desserializar, nem ID para reinserir, nem sequência para reajustar.
#   2. **A purga do 15º dia apaga de verdade**, e só aí o `CASCADE`/`PROTECT`
#      dos módulos entra em cena (política em `nucleo/lixo.py`).
#
# **Por que a marca fica no próprio modelo, e não numa cópia em JSON.** A prancha
# do lixo (docs/arquitetura/lixo.md) nasceu em 2026 desenhando *hard-delete* +
# snapshot, antes de os módulos existirem. Medido contra o código de hoje, aquele
# mecanismo **contradiz a decisão de 23/08**: `Cronograma.obra` é `CASCADE` e
# `eh_modelo` é uma marca no próprio cronograma, então apagar a obra levaria o
# plano modelo junto — e `Orcamento.obra` é `PROTECT`, então a obra que tem
# orçamento nem sairia. A lápide preserva os dois de graça.
#
# **Por que isto não é o "mecanismo paralelo" que o D116 temia.** O medo era
# obrigar toda consulta de todo módulo a lembrar do filtro. Não é o caso: o
# filtro entra no **gerente padrão**, que é o mesmo caminho por onde 259 modelos
# já leem. Serializer, relação reversa (`obra.etapas`), agregação de serviço e
# ViewSet herdam o corte sem escrever uma linha. Quem precisa do excluído pede
# `Model.todos` **por escrito** — e é só o lixo que precisa.
#
# Django detalhe, e é ele que torna o desenho seguro: com `base_manager_name`
# **não** declarado, o `_base_manager` que o ORM usa para travessia de FK e para
# `refresh_from_db()` é um `Manager` simples criado na hora — sem o filtro. Ou
# seja, `conta_pagar.obra` continua devolvendo a obra na lixeira (o título tem de
# saber de quem ele é), enquanto `Obra.objects` não a lista. Declarar
# `base_manager_name = "todos"` daria no mesmo; não declarar nada é menos código
# e o comportamento é o documentado pelo Django.
class ExcluivelQuerySet(models.QuerySet):
    """Os dois recortes, nomeados — para que o chamador diga qual quer."""

    def vivos(self):
        return self.filter(excluido_em__isnull=True)

    def no_lixo(self):
        return self.filter(excluido_em__isnull=False)


class GerenteVivos(models.Manager.from_queryset(ExcluivelQuerySet)):
    """Gerente **padrão**: enxerga só o que não está na lixeira."""

    def get_queryset(self):
        return super().get_queryset().filter(excluido_em__isnull=True)


class Excluivel(models.Model):
    """Base abstrata de quem pode ir para a lixeira.

    Herdar isto **muda o `DELETE` da API**: o `perform_destroy` do
    `TenantScopedViewSetMixin` passa a marcar a lápide em vez de apagar. Quem não
    herda continua com exclusão física, que é o certo para o que é acessório
    (rateio, item de nota, exceção de calendário) — lixeira de tudo viraria
    depósito de ruído, e o que o dono pediu para poder desfazer é o objeto de
    valor, não a linha filha dele.
    """

    #: A data é a lápide **e** o relógio da purga: `excluido_em + retenção do
    #: plano` é quando esta linha morre de verdade. Indexada porque a varredura
    #: diária da purga filtra exatamente por ela.
    excluido_em = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name=_("Excluído em"),
    )
    #: `SET_NULL` porque a lápide sobrevive ao desligamento de quem apagou — o
    #: registro de que a linha saiu vale mesmo depois de o autor deixar a
    #: empresa. A tela cai para "usuário removido" e a data continua de pé.
    excluido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", verbose_name=_("Excluído por"),
    )
    motivo_exclusao = models.TextField(
        blank=True, default="", verbose_name=_("Motivo da exclusão"),
    )

    #: A ORDEM IMPORTA: o primeiro gerente declarado é o `_default_manager`, e é
    #: ele que a relação reversa e o serializer usam.
    objects = GerenteVivos()
    #: A porta explícita para o que está na lixeira. Só o `nucleo/lixo.py` e o
    #: `admin` deveriam precisar dela.
    todos = models.Manager.from_queryset(ExcluivelQuerySet)()

    class Meta:
        abstract = True

    @property
    def esta_no_lixo(self) -> bool:
        return self.excluido_em is not None
