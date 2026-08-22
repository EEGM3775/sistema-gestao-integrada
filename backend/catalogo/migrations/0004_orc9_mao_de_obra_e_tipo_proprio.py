# ORC.9 — a natureza do item passa a espelhar a classificação da SINAPI
# (`mao_de_obra` e `encargos_complementares` deixam de cair em `servico`/
# `material`) e a empresa ganha tipos próprios por cima dessas naturezas.
#
# RLS fail-closed na tabela nova, pelo mesmo padrão de catalogo/0001: tabela
# criada depois da varredura da nucleo/0011 não é coberta automaticamente.
import django.db.models.deletion
from django.db import migrations, models

_TABLES = ("catalogo_tipoitemproprio",)
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
        ('catalogo', '0003_alter_item_fonte_referencia'),
        ('nucleo', '0022_tarefanafila'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='tipo',
            field=models.CharField(choices=[('material', 'Material'), ('mao_de_obra', 'Mão de obra'), ('equipamento', 'Equipamento / Ferramenta'), ('encargos_complementares', 'Encargos complementares'), ('servico', 'Serviço de terceiro'), ('epi', 'EPI'), ('ativo', 'Ativo / Patrimônio'), ('composicao', 'Composição')], default='material', max_length=24, verbose_name='Tipo'),
        ),
        migrations.CreateModel(
            name='TipoItemProprio',
            fields=[
                ('tipo_item_id', models.AutoField(primary_key=True, serialize=False)),
                ('codigo', models.SlugField(max_length=30, verbose_name='Código')),
                ('nome', models.CharField(max_length=60, verbose_name='Nome')),
                ('descricao', models.CharField(blank=True, max_length=200, verbose_name='Descrição')),
                ('natureza', models.CharField(choices=[('material', 'Material'), ('mao_de_obra', 'Mão de obra'), ('equipamento', 'Equipamento / Ferramenta'), ('encargos_complementares', 'Encargos complementares'), ('servico', 'Serviço de terceiro'), ('epi', 'EPI'), ('ativo', 'Ativo / Patrimônio'), ('composicao', 'Composição')], default='material', help_text='A classificação da SINAPI de que este tipo herda o comportamento.', max_length=24, verbose_name='Natureza (como o sistema calcula)')),
                ('leva_encargo_social', models.BooleanField(default=False, help_text='Só faz sentido em mão de obra: o encargo incide sobre salário.', verbose_name='Leva encargo social')),
                ('compravel', models.BooleanField(default=True, verbose_name='Comprável (SCM)')),
                ('estocavel', models.BooleanField(default=True, verbose_name='Estocável (SIL)')),
                ('vendavel', models.BooleanField(default=False, verbose_name='Vendável (comercial)')),
                ('consumivel', models.BooleanField(default=True, verbose_name='Consumível (baixa por obra)')),
                ('rastreavel', models.BooleanField(default=False, verbose_name='Rastreável (lote/validade)')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Tipo próprio de item',
                'verbose_name_plural': 'Tipos próprios de item',
                'ordering': ['nome'],
            },
        ),
        migrations.AddField(
            model_name='item',
            name='tipo_proprio',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='itens', to='catalogo.tipoitemproprio', verbose_name='Tipo próprio da empresa'),
        ),
        migrations.AddConstraint(
            model_name='tipoitemproprio',
            constraint=models.UniqueConstraint(fields=('tenant', 'codigo'), name='catalogo_tipoitem_codigo_unico'),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
