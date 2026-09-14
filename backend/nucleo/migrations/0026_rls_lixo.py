# backend/nucleo/migrations/0026_rls_lixo.py
"""RLS fail-closed na lixeira.

A tabela guarda **o que cada empresa apagou, quem apagou e por quê** — e o
`rotulo` carrega o nome do objeto ("Residencial Aurora", "Construtora X Ltda").
É um índice do acervo inteiro do tenant num lugar só: sem política, uma consulta
que escapasse do filtro de aplicação devolveria a lista de obras, clientes e
fornecedores de todas as empresas de uma vez. É a mesma classe do `AuditLog`.

Nota de desenho: `Lixo` é polimórfica por `ContentType`, e o alvo mora na tabela
do módulo dono — que tem RLS própria. A política aqui protege **o índice**; a
linha sob a lápide continua protegida onde ela vive.

A lápide em si (`excluido_em`/`excluido_por`/`motivo_exclusao`) não precisa de
política nova: ela são três colunas **dentro** de tabelas que já têm a sua.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = ("nucleo_lixo",)
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
        ("nucleo", "0025_lixo"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
