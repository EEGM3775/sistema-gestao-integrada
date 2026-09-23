# backend/modulopdca/migrations/0019_rls_pdca7.py
"""RLS fail-closed nas sete tabelas da PDCA.7.

As da PDCA.5 protegiam o que a empresa sabe sobre a própria **execução**. Estas
protegem o que ela sabe sobre os próprios **defeitos**, que é a informação mais
cara de vazar em todo o módulo:

- `naoconformidade` é a lista do que saiu errado numa obra, com foto, endereço e
  gravidade. Lida de fora, é a peça que um concorrente levaria a um cliente em
  disputa — ou que a outra parte levaria a uma perícia. Escrita de fora, planta
  um defeito numa obra alheia, e o registro nasce com aparência de auditoria.
- `verificacao`/`itemverificacao` são a **prova** que o organismo certificador
  audita no PBQP-H. Um UPDATE cruzado reescreve o que um inspetor respondeu num
  dia em que ele estava no canteiro — e a ficha continua parecendo legítima,
  porque nada nela denuncia a origem da escrita.
- `planoacao` e `verificacaoeficacia` carregam **nome de responsável** e custo do
  retrabalho. Valem a mesma leitura do `itemprogramacao`: um INSERT cruzado põe
  uma pessoa real assumindo um conserto que ela nunca assumiu.
- `modeloverificacao`/`itemmodeloverificacao` parecem catálogo inofensivo e não
  são, pelo mesmo argumento que a `causanaocumprimento` recebeu na 0015: a
  biblioteca de fichas de uma construtora é o método dela escrito — o que ela
  aprendeu a conferir, e onde já se queimou.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulopdca_modeloverificacao",
    "modulopdca_itemmodeloverificacao",
    "modulopdca_verificacao",
    "modulopdca_itemverificacao",
    "modulopdca_naoconformidade",
    "modulopdca_planoacao",
    "modulopdca_verificacaoeficacia",
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
        ("modulopdca", "0018_pdca7_verificacao"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
