"""O cronograma puxa a compra: antecedência por obra/insumo e por atividade.

A tabela nova nasce com RLS fail-closed, na forma estimável (D238, ver
nucleo/migrations/0029_rls_estimavel.py), como toda tabela de tenant. Helper
repetido em vez de importado porque nome de módulo de migration começa com
dígito e não é importável; é o padrão do repo.
"""

import django.db.models.deletion
from django.db import migrations, models

_TABLES = ("modulopdca_antecedenciadecompra",)
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
        ('modulopdca', '0024_restricao_reaberta'),
        ('nucleo', '0029_rls_estimavel'),
        ('obras', '0006_remove_obra_unique_obra_empreendimento_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='atividade',
            name='antecedencia_compra_dias',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Antecedência de compra (dias)'),
        ),
        migrations.CreateModel(
            name='AntecedenciaDeCompra',
            fields=[
                ('antecedencia_id', models.AutoField(primary_key=True, serialize=False)),
                ('dias', models.PositiveSmallIntegerField(verbose_name='Dias de antecedência')),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='catalogo.item', verbose_name='Insumo (vazio = padrão da obra)')),
                ('obra', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='antecedencias_compra', to='obras.obra', verbose_name='Obra')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Antecedência de compra',
                'verbose_name_plural': 'Antecedências de compra',
                'constraints': [models.UniqueConstraint(condition=models.Q(('item__isnull', False)), fields=('tenant', 'obra', 'item'), name='pdca_antecedencia_unica_por_insumo'), models.UniqueConstraint(condition=models.Q(('item__isnull', True)), fields=('tenant', 'obra'), name='pdca_antecedencia_padrao_unico')],
            },
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
