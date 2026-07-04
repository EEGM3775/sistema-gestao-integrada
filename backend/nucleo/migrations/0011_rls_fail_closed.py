"""
S2 — RLS fail-closed (Fase 8.4).

A política original (migration `0007`) era **fail-open**: liberava TODAS as
linhas quando `app.current_tenant` não estava definido. Como só o mixin de
ViewSet armava o contexto, qualquer caminho fora dele (APIView pura, comando,
shell, Celery task, webhook) rodava sem proteção — silenciosamente (foi a raiz
do S1).

Esta migration troca por **fail-closed**: sem contexto, a política **não
devolve nenhuma** linha. Só há duas formas de enxergar/gravar uma linha:

1. `app.current_tenant` igual ao `tenant_id` da linha — armado por requisição
   pela autenticação (`arm_rls_for_request`); ou
2. `app.rls_bypass = 'on'` — bypass **explícito** de plataforma, ligado só por
   código confiável (superusuário, webhook do Asaas, migrações de dados, jobs)
   via `arm_rls_bypass()`/`rls_bypass()`.

No-op fora do PostgreSQL (SQLite de dev). O role da aplicação (`erp_app`) não é
superuser nem BYPASSRLS e as tabelas estão em `FORCE ROW LEVEL SECURITY`, então
a política vale de fato sobre ele; migrações/jobs que precisem cruzar tenants
rodam sob o role `postgres` (BYPASSRLS) ou sob `rls_bypass()`.
"""
from django.db import migrations

EXCLUDED_APPS = {"nucleo"}
POLICY = "tenant_isolation"

# fail-closed: só o tenant da linha OU o bypass explícito de plataforma.
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)
# fail-open (política antiga, para o reverse).
USING_OPEN = (
    "current_setting('app.current_tenant', true) IS NULL "
    "OR current_setting('app.current_tenant', true) = '' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)


def _tenant_tables(apps):
    tables = []
    for model in apps.get_models():
        if model._meta.app_label in EXCLUDED_APPS:
            continue
        try:
            field = model._meta.get_field("tenant")
        except Exception:
            continue
        if getattr(field, "is_relation", False):
            tables.append(model._meta.db_table)
    return tables


def _apply_policy(apps, schema_editor, expr):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in _tenant_tables(apps):
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
            cursor.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            cursor.execute(
                f'CREATE POLICY {POLICY} ON "{table}" '
                f"USING ({expr}) WITH CHECK ({expr});"
            )


def fail_closed(apps, schema_editor):
    _apply_policy(apps, schema_editor, USING_CLOSED)


def fail_open(apps, schema_editor):
    _apply_policy(apps, schema_editor, USING_OPEN)


class Migration(migrations.Migration):
    dependencies = [
        ("nucleo", "0010_alter_failedtask_task_id"),
    ]

    operations = [migrations.RunPython(fail_closed, fail_open)]
