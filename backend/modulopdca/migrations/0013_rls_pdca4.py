# backend/modulopdca/migrations/0013_rls_pdca4.py
"""RLS fail-closed nas três tabelas da PDCA.4.

A 0011 protegeu *quanto a empresa paga a quem*. Estas três protegem a mesma
coisa nos dois pontos em que ela **muda**:

- `aditivocontrato`/`itemaditivo` guardam a diferença entre o que foi assinado e
  o que está sendo executado. É o número que um concorrente usa para provar, num
  processo, que a obra estourou o contratado — e, num INSERT cruzado, é o que
  faria o saldo de um contrato de outra empresa crescer sem nenhum documento
  daquela empresa autorizando.
- `deducaomedicao` decide **quanto o empreiteiro recebe de fato**. Uma linha
  gravada no tenant vizinho não vaza informação: ela tira dinheiro do
  pagamento de alguém, e o erro só aparece quando o empreiteiro reclama.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulopdca_aditivocontrato",
    "modulopdca_itemaditivo",
    "modulopdca_deducaomedicao",
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
        ("modulopdca", "0012_pdca4_aditivo_deducao_estocado"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
