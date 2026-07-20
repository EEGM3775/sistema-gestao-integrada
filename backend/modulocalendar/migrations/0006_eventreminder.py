# Lembretes de evento (Fatia C) — modelo + RLS fail-closed na criação da tabela.
#
# A política fail-closed da nucleo/0011 varre as tabelas existentes NAQUELE
# ponto do grafo; uma tabela criada depois (como esta) não é coberta
# automaticamente. Espelhamos a mesma política aqui (idêntica à de
# nucleo/0016/0019) para paridade de isolamento por tenant.
import django.db.models.deletion
from django.db import migrations, models

TABLE = "modulocalendar_eventreminder"
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY;')
        c.execute(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY;')
        c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{TABLE}";')
        c.execute(
            f'CREATE POLICY {POLICY} ON "{TABLE}" '
            f"USING ({USING_CLOSED}) WITH CHECK ({USING_CLOSED});"
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{TABLE}";')
        c.execute(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY;')
        c.execute(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):

    dependencies = [
        ('modulocalendar', '0005_feriadosync_feriado'),
        ('nucleo', '0011_rls_fail_closed'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('offset_minutes', models.PositiveIntegerField(default=10)),
                ('last_sent_occurrence', models.DateTimeField(blank=True, null=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to='modulocalendar.calendarevent')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'ordering': ['offset_minutes'],
            },
        ),
        migrations.AddConstraint(
            model_name='eventreminder',
            constraint=models.UniqueConstraint(fields=('event', 'offset_minutes'), name='uniq_reminder_event_offset'),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
