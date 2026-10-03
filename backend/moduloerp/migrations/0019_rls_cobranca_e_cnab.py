"""RLS fail-closed nas cinco tabelas da cobrança em lote e do CNAB (item 52).

- `contacobrancabancaria` é agência, conta e convênio de cobrança da empresa.
  Lida de fora, entrega o que falta para emitir boleto em nome dela; escrita de
  fora, troca a conta que recebe.
- `remessacnab` e `retornocnab` guardam os arquivos inteiros: nome, documento
  e endereço de cada pagador, e o que cada um pagou.
- `lotecobranca` e `itemlotecobranca` dizem quem foi cobrado e quem não pôde ser.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "moduloerp_contacobrancabancaria",
    "moduloerp_remessacnab",
    "moduloerp_retornocnab",
    "moduloerp_lotecobranca",
    "moduloerp_itemlotecobranca",
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
        ("moduloerp", "0018_cobranca_em_lote_e_cnab"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
