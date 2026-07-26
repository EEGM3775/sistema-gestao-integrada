# backend/funcoesimpexp/migrations/0002_rls_fail_closed.py
"""RLS fail-closed nas três tabelas do IE.0 — mesma política do resto do backend.

Vale com força total para a **área de conferência**: ela guarda o arquivo que a
empresa subiu *antes* de qualquer decisão, e arquivo em conferência é o dado mais
cru que existe no sistema — carteira de clientes, tabela de custo, folha. Vazar
ali é vazar tudo, e antes mesmo de alguém ter escolhido importar.

Helper repetido em vez de importado porque nome de módulo de migration começa com
dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "funcoesimpexp_importacao",
    "funcoesimpexp_linhaimportacao",
    "funcoesimpexp_exportacao",
)
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for table in _TABLES:
            c.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            c.execute(
                f'CREATE POLICY {POLICY} ON "{table}" '
                f"USING ({USING_CLOSED}) WITH CHECK ({USING_CLOSED});"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for table in _TABLES:
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            c.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):

    dependencies = [
        ("funcoesimpexp", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
