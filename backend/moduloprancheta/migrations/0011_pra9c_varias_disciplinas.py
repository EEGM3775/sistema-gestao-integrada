"""PRA.9c — uma prancha pode ter **várias** disciplinas.

O desenho real não obedece a uma classificação só: a planta de forro é
arquitetura *e* elétrica, o corte de shaft é hidrossanitário *e* incêndio.
Obrigar a escolher uma fazia a pessoa escolher errado — ou não escolher, que era
o caminho para tudo cair em *Outra* e a fileira de filtro virar um botão só.

**Sem migração de dados, e é de propósito.** O `disciplina` do documento
continua existindo como a **principal** (a de `ordem = 0`), porque três coisas
dependem de haver uma: a ordenação do acervo, a coluna do lote e a cor do cartão.
Documento anterior a esta fatia não tem vínculo nenhum, e o
`codigos_de_disciplina` cai no campo — então o acervo existente continua
respondendo certo sem uma única linha escrita aqui. Quem cria vínculo é o
`definir_disciplinas`, na primeira vez que alguém reclassificar a prancha.

RLS na mesma migration, como a `0004` e a `0010`: a tabela nasce agora, e
protegê-la na seguinte abriria a janela em que a classificação do acervo de um
cliente é legível por qualquer sessão.
"""

import django.db.models.deletion
from django.db import migrations, models

# Helper repetido em vez de importado porque nome de módulo de migration começa
# com dígito e não é importável; é o padrão do repo (ver `0002_rls_fail_closed`).
_TABLES = ("moduloprancheta_documentodisciplina",)
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
            c.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):

    dependencies = [
        ("nucleo", "0001_initial"),
        ("moduloprancheta", "0010_pra9b_disciplina_do_tenant"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentoDisciplina",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.SlugField(max_length=40, verbose_name="Disciplina")),
                ("ordem", models.PositiveSmallIntegerField(default=0, verbose_name="Ordem")),
                (
                    "documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vinculos_disciplina",
                        to="moduloprancheta.documentoprojeto",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="nucleo.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Disciplina do documento",
                "verbose_name_plural": "Disciplinas do documento",
                "ordering": ["ordem", "codigo"],
            },
        ),
        migrations.AddIndex(
            model_name="documentodisciplina",
            index=models.Index(fields=["tenant", "codigo"], name="prancheta_docdisc_codigo_idx"),
        ),
        migrations.AddConstraint(
            model_name="documentodisciplina",
            constraint=models.UniqueConstraint(
                fields=("documento", "codigo"), name="prancheta_documento_disciplina_unica"
            ),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
