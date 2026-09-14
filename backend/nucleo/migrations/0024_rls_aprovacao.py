# backend/nucleo/migrations/0024_rls_aprovacao.py
"""RLS fail-closed nas quatro tabelas da escada de atesto.

Estas guardam **quem autorizou o pagamento de quem, e por quanto**. É a classe de
dado em que o vazamento não é constrangimento e sim prova: o atesto nomeia o
funcionário que liberou o dinheiro, com data e observação escrita por ele.

Nota de desenho: `PedidoAprovacao` é polimórfico por `ContentType`, e o alvo mora
em tabela de outro app — que tem RLS própria. A política aqui protege o **pedido
e o atesto**; a linha aprovada continua protegida onde ela vive.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "nucleo_fluxoaprovacao",
    "nucleo_nivelaprovacao",
    "nucleo_pedidoaprovacao",
    "nucleo_atesto",
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
        ("nucleo", "0023_aprovacao_multinivel"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
