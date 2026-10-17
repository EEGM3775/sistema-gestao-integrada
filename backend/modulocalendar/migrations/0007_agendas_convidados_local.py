# Calendário, Fatias D e E — agendas (pessoal/equipe/empresa), membros,
# convidados com resposta, local do evento e o UID do .ics importado.
#
# RLS fail-closed nas três tabelas novas, na forma estimável (D238, ver
# nucleo/migrations/0029_rls_estimavel.py): a política da nucleo/0011 só cobre
# as tabelas que existiam naquele ponto do grafo.
#
# Começa ligando o bypass da RLS: o `calendarevent` ganha uma FK nova, e o
# Postgres a valida lendo as tabelas com o papel da aplicação — sem tenant na
# sessão, a RLS esconde as linhas (o que derrubou a moduloerp.0025 no servidor).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

TABELAS = (
    "modulocalendar_calendar",
    "modulocalendar_calendarmember",
    "modulocalendar_eventattendee",
)
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
        for tabela in TABELAS:
            c.execute(f'ALTER TABLE "{tabela}" ENABLE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{tabela}" FORCE ROW LEVEL SECURITY;')
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{tabela}";')
            c.execute(
                f'CREATE POLICY {POLICY} ON "{tabela}" '
                f"USING ({USING_CLOSED}) WITH CHECK ({USING_CLOSED});"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for tabela in TABELAS:
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{tabela}";')
            c.execute(f'ALTER TABLE "{tabela}" NO FORCE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{tabela}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):

    dependencies = [
        ('modulocalendar', '0006_eventreminder'),
        ('nucleo', '0031_notificacao_nivel'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(ligar_bypass, migrations.RunPython.noop),
        migrations.AddField(
            model_name='calendarevent',
            name='ical_uid',
            field=models.CharField(blank=True, db_index=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='calendarevent',
            name='location',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.CreateModel(
            name='Calendar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('color', models.CharField(default='#1e40af', max_length=7)),
                ('scope', models.CharField(choices=[('pessoal', 'Pessoal'), ('equipe', 'Equipe'), ('empresa', 'Empresa')], default='pessoal', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendars', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'ordering': ['name', 'id'],
            },
        ),
        migrations.AddField(
            model_name='calendarevent',
            name='calendar',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='events', to='modulocalendar.calendar'),
        ),
        migrations.CreateModel(
            name='CalendarMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('calendar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='modulocalendar.calendar')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('calendar', 'user'), name='uniq_calendar_member')],
            },
        ),
        migrations.CreateModel(
            name='EventAttendee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pendente', 'Pendente'), ('aceito', 'Aceito'), ('recusado', 'Recusado')], default='pendente', max_length=10)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendees', to='modulocalendar.calendarevent')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_invites', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['id'],
                'constraints': [models.UniqueConstraint(fields=('event', 'user'), name='uniq_event_attendee')],
            },
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
