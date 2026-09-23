# backend/modulopdca/migrations/0015_rls_pdca5.py
"""RLS fail-closed nas quatro tabelas da PDCA.5.

As anteriores protegeram *quanto a empresa paga a quem*. Estas protegem o que a
empresa **sabe sobre a própria execução**, e cada uma por uma razão distinta:

- `restricao` é o inventário do que trava a obra — quais projetos não chegaram,
  qual fornecedor está atrasado, que licença não saiu. Lido de fora, é o mapa
  das fraquezas do concorrente na semana que vem. Escrito de fora, trava a
  programação de uma obra alheia sem nenhum documento daquela empresa pedindo.
- `programacaosemanal`/`itemprogramacao` guardam **compromissos com nome de
  responsável**. Um INSERT cruzado põe uma pessoa real assumindo um serviço que
  ela nunca assumiu, e o erro só aparece no encerramento, quando o PPC dela cai.
- `causanaocumprimento` parece catálogo inofensivo e não é: o `UniqueConstraint`
  é por tenant, e sem RLS uma leitura cruzada mostraria o vocabulário de falha
  de outra empresa — que é, literalmente, a lista dos problemas dela.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulopdca_restricao",
    "modulopdca_programacaosemanal",
    "modulopdca_itemprogramacao",
    "modulopdca_causanaocumprimento",
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
        ("modulopdca", "0014_pdca5_lastplanner"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
