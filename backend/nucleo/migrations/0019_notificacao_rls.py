"""RLS fail-closed para `nucleo_notificacao` (Calendário, Fatia C).

`Notificacao` é tenant-scoped e a migração `0011` só cobre os apps de negócio
(exclui `nucleo`). Esta migração aplica a MESMA política fail-closed (mesmo expr
do `0011`/`0016`) à tabela de notificações: sessão sem `app.current_tenant`
(e sem bypass) não lê nem grava notificação de tenant nenhum. A task de despacho
de lembretes cruza tenants sob `rls_bypass()`. No-op fora do PostgreSQL.
"""
from django.db import migrations

TABLE = "nucleo_notificacao"
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)


def up(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY;')
        c.execute(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY;')
        c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{TABLE}";')
        c.execute(
            f'CREATE POLICY {POLICY} ON "{TABLE}" '
            f"USING ({USING_CLOSED}) WITH CHECK ({USING_CLOSED});"
        )


def down(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{TABLE}";')
        c.execute(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY;')
        c.execute(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0018_notificacao")]
    operations = [migrations.RunPython(up, down)]
