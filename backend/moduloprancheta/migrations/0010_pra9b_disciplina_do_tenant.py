"""PRA.9b — a disciplina passa a ser vocabulário do cliente.

As 13 de `Disciplina` são o piso (o que o carimbo brasileiro escreve, e de onde a
taxonomia do lote adivinha a pasta); faltava o andar de cima. Construtora que
separa "Fachada" de "Arquitetura", ou que trabalha com "Impermeabilização", não
tinha onde pôr — tudo caía em *Outra*, e a fileira de filtro da grade perdia o
sentido justamente para quem tem acervo grande.

**Duas mudanças, e a segunda é a que evita migração de dados.** A tabela nova
guarda rótulo, cor e ordem por tenant; o `DocumentoProjeto.disciplina` continua
sendo **texto** e perde os `choices` — com eles, o `full_clean` recusaria a
disciplina que o próprio cliente acabou de cadastrar. Como os slugs das 13
continuam valendo sem nenhuma linha aqui, o acervo que já existe não é tocado.

A RLS entra **nesta** migration, como na `0004` e pelo mesmo motivo: a tabela
nasce agora, e protegê-la na seguinte abriria uma janela em que o vocabulário de
um cliente é legível por qualquer sessão. Aqui o vazamento seria menor que o de
uma marcação — mas nome de disciplina denuncia o que a empresa constrói, e a
política é fail-closed em toda tabela de negócio, sem exceção por tamanho.
"""

import django.db.models.deletion
from django.db import migrations, models

# Helper repetido em vez de importado porque nome de módulo de migration começa
# com dígito e não é importável; é o padrão do repo (ver `0002_rls_fail_closed`).
_TABLES = ("moduloprancheta_disciplinaprojeto",)
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
        ("moduloprancheta", "0009_pra1d_caminho_origem"),
    ]

    operations = [
        migrations.CreateModel(
            name="DisciplinaProjeto",
            fields=[
                ("disciplina_id", models.AutoField(primary_key=True, serialize=False)),
                ("codigo", models.SlugField(max_length=40, verbose_name="Código")),
                ("nome", models.CharField(max_length=60, verbose_name="Nome")),
                (
                    "cor",
                    models.CharField(
                        blank=True,
                        help_text="Hex (#RRGGBB). Em branco, a tela deriva uma estável do código.",
                        max_length=7,
                        verbose_name="Cor",
                    ),
                ),
                ("ordem", models.PositiveIntegerField(default=100, verbose_name="Ordem")),
                ("ativa", models.BooleanField(default=True, verbose_name="Ativa")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
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
                "verbose_name": "Disciplina de projeto",
                "verbose_name_plural": "Disciplinas de projeto",
                "ordering": ["ordem", "nome"],
            },
        ),
        migrations.AddConstraint(
            model_name="disciplinaprojeto",
            constraint=models.UniqueConstraint(
                fields=("tenant", "codigo"), name="prancheta_disciplina_codigo_por_tenant"
            ),
        ),
        migrations.AlterField(
            model_name="documentoprojeto",
            name="disciplina",
            field=models.CharField(default="outra", max_length=40, verbose_name="Disciplina"),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
