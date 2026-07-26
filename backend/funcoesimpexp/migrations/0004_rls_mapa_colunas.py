# backend/funcoesimpexp/migrations/0004_rls_mapa_colunas.py
"""RLS fail-closed no `MapaColunas` (IE.0b) — a tabela nova entra na mesma política.

Tabela nova de tenant **nasce com a política**, nunca depois: um de-para diz em
que coluna do arquivo de um cliente mora cada campo — é a planta da planilha
dele, e o formato da fonte de custo de uma construtora não é dado público.

Helper repetido em vez de importado porque nome de módulo de migration começa com
dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = ("funcoesimpexp_mapacolunas",)
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
        ("funcoesimpexp", "0003_ie0b_job_assincrono_e_mapa_colunas"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
