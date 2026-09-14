# backend/modulopdca/migrations/0007_rls_pdca2.py
"""RLS fail-closed na tabela do apontamento de avanço.

A mesma política das seis anteriores, e aqui ela protege o dado mais sensível da
fatia: o apontamento é o **quanto a obra andou**, e é dele que a medição da
PDCA.3 vai nascer. Vazar para o tenant vizinho entrega produtividade de equipe e
ritmo de execução — o insumo com que um concorrente monta a proposta contra a
construtora — e, pior, seria a porta de uma escrita cruzada num livro que ninguém
pode reescrever depois.

Helper repetido em vez de importado porque nome de módulo de migration começa com
dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = ("modulopdca_apontamentoavanco",)
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
        ("modulopdca", "0006_pdca2_apontamento_avanco"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
