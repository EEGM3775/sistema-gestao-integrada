"""
Fase 8.2 — backfill de `tenant` antes de torná-lo NOT NULL.

Toda linha de negócio (modelos que herdam `TenantScopedModel`) passa a exigir
`tenant`. Esta migração roda **antes** dos `AlterField` que fazem `SET NOT NULL`
(as migrações de cada app dependem desta) e atribui um tenant às linhas legadas
com `tenant` NULL:

- **exatamente 1 tenant** no banco → todas as órfãs vão para ele (caso comum de
  dev/greenfield);
- **linhas órfãs com 0 ou >1 tenants** → **aborta** com mensagem: é ambíguo, o
  operador precisa atribuir manualmente antes de migrar.
- **sem linhas órfãs** → no-op (dev atual e prod greenfield).

Roda sob **bypass** explícito da RLS: a política fail-closed esconde linhas com
`tenant` NULL do role de aplicação, então sem o bypass o backfill não as
enxergaria. No-op fora do PostgreSQL.
"""
from django.db import migrations


def _arm_bypass(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def _tenant_scoped_models(apps):
    for model in apps.get_models():
        if model._meta.app_label == "nucleo":
            continue
        try:
            field = model._meta.get_field("tenant")
        except Exception:
            continue
        if getattr(field, "is_relation", False):
            yield model


def backfill_tenant(apps, schema_editor):
    _arm_bypass(schema_editor)
    Tenant = apps.get_model("nucleo", "Tenant")
    default_tenant = None  # resolvido só quando houver órfã (evita erro em banco vazio)

    for model in _tenant_scoped_models(apps):
        orphans = model.objects.filter(tenant__isnull=True)
        if not orphans.exists():
            continue
        if default_tenant is None:
            n = Tenant.objects.count()
            if n != 1:
                raise RuntimeError(
                    f"Backfill de tenant ambíguo: {n} tenants no banco e há linhas "
                    f"com tenant NULL em {model._meta.label}. Atribua um tenant a "
                    "essas linhas manualmente antes de aplicar a migração 8.2."
                )
            default_tenant = Tenant.objects.first()
        orphans.update(tenant=default_tenant)


def noop_reverse(apps, schema_editor):
    # Não há como distinguir as linhas backfilladas para reverter — no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("nucleo", "0011_rls_fail_closed"),
    ]

    operations = [migrations.RunPython(backfill_tenant, noop_reverse)]
