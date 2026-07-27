# backend/modulomaps/migrations/0002_rls_fail_closed.py
"""RLS fail-closed nas oito tabelas do Maps — mesma política do resto do backend.

Vale com força aqui por uma razão específica do domínio: **coordenada é dado
estratégico**. A carteira georreferenciada de uma construtora diz onde ela está
comprando terreno, onde tem canteiro aberto e de quais fornecedores depende —
vazar isso para outro tenant é entregar o mapa da operação de um concorrente,
mesmo sem um único valor financeiro junto.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulomaps_local",
    "modulomaps_camada",
    "modulomaps_feicao",
    "modulomaps_ortofoto",
    "modulomaps_planovoo",
    "modulomaps_rota",
    "modulomaps_paradarota",
    "modulomaps_geofence",
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
        ("modulomaps", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
