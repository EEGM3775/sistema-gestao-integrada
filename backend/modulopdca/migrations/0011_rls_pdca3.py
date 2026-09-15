# backend/modulopdca/migrations/0011_rls_pdca3.py
"""RLS fail-closed nas cinco tabelas da PDCA.3.

A mesma política das nove anteriores, e aqui ela protege o dado mais caro que o
módulo já guardou: **quanto a empresa paga a quem, e sob que condição**.

O apontamento de avanço (0007) já vazava ritmo de execução; isto vaza a
**margem**. Preço unitário contratado com empreiteiro é o número que um
concorrente usa para montar a proposta contra a construtora, e a cláusula de
retenção diz quanto de caixa ela consegue segurar. Pior que a leitura seria a
escrita cruzada: um `ItemMedicao` gravado no tenant vizinho termina, pela escada
de atesto, num `ContaPagar` de uma empresa que nunca contratou aquele serviço.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulopdca_contratoobra",
    "modulopdca_itemcontrato",
    "modulopdca_medicao",
    "modulopdca_itemmedicao",
    "modulopdca_liberacaoretencao",
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
        ("modulopdca", "0010_pdca3_contrato_medicao"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
