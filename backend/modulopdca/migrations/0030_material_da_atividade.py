"""O material informado na atividade — necessidade de compra sem orçamento (dono, 10/10/2026).

A tabela nova nasce com RLS fail-closed, na forma estimável (D238, ver
nucleo/migrations/0029_rls_estimavel.py), como toda tabela de tenant. Helper
repetido em vez de importado porque nome de módulo de
migration começa com dígito e não é importável; é o padrão do repo.
"""

import django.db.models.deletion
from django.db import migrations, models

_TABLES = ("modulopdca_materialdaatividade",)
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
        ('catalogo', '0006_orc8b_embasa_pdf'),
        ('modulopdca', '0029_equipe_da_obra'),
        ('nucleo', '0029_rls_estimavel'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaterialDaAtividade',
            fields=[
                ('material_id', models.AutoField(primary_key=True, serialize=False)),
                ('descricao', models.CharField(max_length=255, verbose_name='Descrição')),
                ('unidade', models.CharField(max_length=20, verbose_name='Unidade')),
                ('categoria', models.CharField(choices=[('material', 'Material'), ('equipamento', 'Equipamento')], default='material', max_length=12, verbose_name='Categoria')),
                ('quantidade', models.DecimalField(decimal_places=3, max_digits=14, verbose_name='Quantidade')),
                ('custo_unitario', models.DecimalField(blank=True, decimal_places=4, max_digits=15, null=True, verbose_name='Custo unitário')),
                ('atividade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materiais', to='modulopdca.atividade', verbose_name='Atividade')),
                ('item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='catalogo.item', verbose_name='Item do catálogo')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Material da atividade',
                'verbose_name_plural': 'Materiais das atividades',
                'ordering': ['atividade_id', 'descricao'],
                'constraints': [models.CheckConstraint(condition=models.Q(('quantidade__gt', 0)), name='pdca_material_atividade_qtd_positiva')],
            },
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
