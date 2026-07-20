"""Imutabilidade forte do EventoSeguranca no banco (D11).

Espelha o que a Fase 9.E fez com o `AuditLog` do backend
(`nucleo/migrations/0017`): além do bloqueio app-level (`save`/`delete` no
modelo), um trigger no PostgreSQL barra UPDATE/DELETE mesmo por SQL cru,
`queryset.update()` ou `queryset.delete()`.

Isto importa mais aqui do que em qualquer outra tabela da IAM: a trilha existe
justamente para atribuir ações a um admin que pode estar comprometido. Uma
trilha que o próprio admin consegue editar não serve de prova de nada.

As FKs da tabela são `db_constraint=False` + `DO_NOTHING` (linha congelada), então
excluir um usuário não dispara UPDATE aqui e não esbarra no trigger.

No-op fora do PostgreSQL (a suíte da IAM roda em SQLite).
"""
from django.db import migrations

FUNC = "identity_eventoseguranca_no_mutate"
TABLE = "identity_eventoseguranca"

CREATE = f"""
CREATE OR REPLACE FUNCTION {FUNC}() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'EventoSeguranca é imutável (append-only): % bloqueado', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS eventoseguranca_block_update ON {TABLE};
DROP TRIGGER IF EXISTS eventoseguranca_block_delete ON {TABLE};
CREATE TRIGGER eventoseguranca_block_update BEFORE UPDATE ON {TABLE}
    FOR EACH ROW EXECUTE FUNCTION {FUNC}();
CREATE TRIGGER eventoseguranca_block_delete BEFORE DELETE ON {TABLE}
    FOR EACH ROW EXECUTE FUNCTION {FUNC}();
"""

DROP = f"""
DROP TRIGGER IF EXISTS eventoseguranca_block_update ON {TABLE};
DROP TRIGGER IF EXISTS eventoseguranca_block_delete ON {TABLE};
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
    dependencies = [("identity", "0002_recuperacao_senha_e_eventos")]
    operations = [migrations.RunPython(up, down)]
