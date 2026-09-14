# backend/modulopdca/migrations/0004_rls_pdca1.py
"""RLS fail-closed nas três tabelas da PDCA.1 — mesma política das da PDCA.0.

Por que vale aqui, e é mais grave do que na fatia anterior: o cronograma é o
**prazo** da obra. Ele diz quando cada serviço entra, quanto tempo cada frente
leva e onde está a folga — que é a informação com que um concorrente monta a
proposta contra a construtora, e que, a partir da PDCA.3, será a régua de cálculo
da medição que o empreiteiro recebe. Vazamento aqui entrega estratégia comercial,
não só cadastro.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulopdca_cronograma",
    "modulopdca_atividade",
    "modulopdca_precedencia",
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
        ("modulopdca", "0003_pdca1_cronograma"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
