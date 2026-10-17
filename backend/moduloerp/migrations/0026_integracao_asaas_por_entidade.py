"""D293 — a conta do Asaas de cada entidade, e em que conta o boleto nasceu.

Com mais de uma entidade, o boleto de outra que não a matriz saía pela conta
Asaas do ambiente — com o CNPJ da matriz. A entidade ganha a conta própria
(chave cifrada, como a `IntegracaoFiscal`) e o boleto guarda em qual conta foi
emitido, para cancelar e conferir na mesma.

Começa ligando o bypass da RLS: a tabela nova tem FK para `entidades_entidade`
e o `boleto` (com dado) ganha coluna — no servidor a migration roda como o
papel da aplicação, e a RLS sem tenant na sessão esconderia as linhas (o que
derrubou a 0025). A tabela nova nasce com RLS fail-closed, na forma estimável.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLES = ("moduloerp_integracaoasaas",)
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def ligar_bypass(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute("SELECT set_config('app.rls_bypass', 'on', true)")


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
        ('entidades', '0002_dados'),
        ('moduloerp', '0025_entidade_obrigatoria'),
        ('nucleo', '0031_notificacao_nivel'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(ligar_bypass, migrations.RunPython.noop),
        migrations.AddField(
            model_name='boleto',
            name='conta_asaas',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='Conta do Asaas'),
        ),
        migrations.CreateModel(
            name='IntegracaoAsaas',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('api_key_cifrada', models.TextField(blank=True, verbose_name='Chave da API (cifrada)')),
                ('api_key_final', models.CharField(blank=True, max_length=8, verbose_name='Final da chave')),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('atualizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('entidade', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='entidades.entidade', verbose_name='Entidade')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Integração de cobrança (Asaas)',
                'verbose_name_plural': 'Integrações de cobrança (Asaas)',
                'constraints': [models.UniqueConstraint(fields=('tenant', 'entidade'), name='integracao_asaas_por_entidade')],
            },
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
