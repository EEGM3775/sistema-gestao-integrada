"""Imutabilidade forte do AuditLog no banco (Fase 9.E — fork Q2).

Além do bloqueio app-level (`AuditLog.save`/`delete`) e da API read-only, um
trigger no PostgreSQL barra UPDATE/DELETE mesmo por SQL cru, `queryset.update()`
ou `queryset.delete()` — a trilha é *append-only* de fato. O FK `usuario` usa
`db_constraint=False` (linha congelada; a durabilidade de QUEM agiu fica em
`usuario_nome`), então nenhuma exclusão de usuário dispara UPDATE nesta tabela.
No-op fora do PostgreSQL.
"""
from django.db import migrations

FUNC = "nucleo_auditlog_no_mutate"
TABLE = "nucleo_auditlog"

CREATE = f"""
CREATE OR REPLACE FUNCTION {FUNC}() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'AuditLog é imutável (append-only): % bloqueado', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS auditlog_block_update ON {TABLE};
DROP TRIGGER IF EXISTS auditlog_block_delete ON {TABLE};
CREATE TRIGGER auditlog_block_update BEFORE UPDATE ON {TABLE}
    FOR EACH ROW EXECUTE FUNCTION {FUNC}();
CREATE TRIGGER auditlog_block_delete BEFORE DELETE ON {TABLE}
    FOR EACH ROW EXECUTE FUNCTION {FUNC}();
"""

DROP = f"""
DROP TRIGGER IF EXISTS auditlog_block_update ON {TABLE};
DROP TRIGGER IF EXISTS auditlog_block_delete ON {TABLE};
DROP FUNCTION IF EXISTS {FUNC}();
"""


def up(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(CREATE)


def down(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0016_auditlog_rls")]
    operations = [migrations.RunPython(up, down)]
