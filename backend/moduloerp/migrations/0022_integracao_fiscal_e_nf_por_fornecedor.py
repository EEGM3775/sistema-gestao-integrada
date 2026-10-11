"""A conta da empresa na NFE.io (por tenant, chave cifrada) e o número da NF por fornecedor.

Achados do dono, 10/10/2026: "como vou cadastrar minha API?" e a NF de entrada
pelo XML — duas empreiteiras podem mandar a NF 1234, então o número é único
por fornecedor, não por empresa.

A tabela nova nasce com RLS fail-closed, na forma estimável (D238, ver
nucleo/migrations/0029_rls_estimavel.py) — e aqui com mais razão: ela guarda a
credencial fiscal da empresa. Helper repetido em vez de importado porque nome
de módulo de migration começa com dígito e não é importável; é o padrão do repo.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLES = ("moduloerp_integracaofiscal",)
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
        ('empreendimentos', '0009_remove_empreendimento_empreend_razao_unica_por_tenant_and_more'),
        ('fornecedores', '0006_remove_fornecedor_fornecedor_razao_unica_por_tenant_and_more'),
        ('moduloerp', '0021_financeiro_por_obra'),
        ('nucleo', '0029_rls_estimavel'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IntegracaoFiscal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_id', models.CharField(blank=True, max_length=80, verbose_name='ID da empresa na NFE.io')),
                ('api_key_cifrada', models.TextField(blank=True, verbose_name='Chave da API (cifrada)')),
                ('api_key_final', models.CharField(blank=True, max_length=8, verbose_name='Final da chave')),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Integração fiscal (NFE.io)',
                'verbose_name_plural': 'Integrações fiscais (NFE.io)',
            },
        ),
        migrations.RemoveConstraint(
            model_name='notafiscal',
            name='nf_numero_unico_por_tenant',
        ),
        migrations.AddConstraint(
            model_name='notafiscal',
            constraint=models.UniqueConstraint(condition=models.Q(('excluido_em__isnull', True)), fields=('tenant', 'fornecedor', 'numero_nota'), name='nf_numero_unico_por_fornecedor'),
        ),
        migrations.AddField(
            model_name='integracaofiscal',
            name='atualizado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='integracaofiscal',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant'),
        ),
        migrations.AddConstraint(
            model_name='integracaofiscal',
            constraint=models.UniqueConstraint(fields=('tenant',), name='integracao_fiscal_por_tenant'),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
