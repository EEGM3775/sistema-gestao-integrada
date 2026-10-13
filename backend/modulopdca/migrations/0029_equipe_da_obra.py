"""A equipe da obra como composição — funcionários e fornecedores (decisão do dono, 09/10/2026).

A tabela nova nasce com RLS fail-closed, na forma estimável (D238, ver
nucleo/migrations/0029_rls_estimavel.py), como toda tabela de tenant. As duas
tabelas de ligação do M2M não têm `tenant_id`: só se chega a elas pela equipe,
que é a protegida. Helper repetido em vez de importado porque nome de módulo de
migration começa com dígito e não é importável; é o padrão do repo.
"""

import django.db.models.deletion
from django.db import migrations, models

_TABLES = ("modulopdca_equipeobra",)
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
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
        ('fornecedores', '0006_remove_fornecedor_fornecedor_razao_unica_por_tenant_and_more'),
        ('modulopdca', '0028_compromisso_percentual_concluido'),
        ('nucleo', '0029_rls_estimavel'),
        ('obras', '0006_remove_obra_unique_obra_empreendimento_and_more'),
        ('rh', '0007_remove_cargo_cargo_nome_unico_por_tenant_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='EquipeObra',
            fields=[
                ('equipe_id', models.AutoField(primary_key=True, serialize=False)),
                ('nome', models.CharField(default='', max_length=150, verbose_name='Nome')),
                ('ativa', models.BooleanField(default=True, verbose_name='Ativa')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('fornecedores', models.ManyToManyField(blank=True, related_name='equipes_pdca', to='fornecedores.fornecedor', verbose_name='Fornecedores')),
                ('funcionarios', models.ManyToManyField(blank=True, related_name='equipes_pdca', to='rh.funcionario', verbose_name='Funcionários')),
                ('obra', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='equipes_pdca', to='obras.obra', verbose_name='Obra')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Equipe da obra',
                'verbose_name_plural': 'Equipes da obra',
                'ordering': ['nome'],
            },
        ),
        migrations.AddField(
            model_name='itemprogramacao',
            name='equipe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compromissos', to='modulopdca.equipeobra', verbose_name='Equipe'),
        ),
        migrations.AddConstraint(
            model_name='equipeobra',
            constraint=models.UniqueConstraint(fields=('tenant', 'obra', 'nome'), name='pdca_equipe_nome_unico_por_obra'),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
