"""A proposta que já existia chegou no dia em que foi registrada.

As tabelas têm RLS fail-closed; a passada liga o bypass só na transação dela.
"""
from django.db import migrations
from django.db.models import F
from django.db.models.functions import TruncDate


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def copiar_data(apps, schema_editor):
    _bypass(schema_editor)
    Proposta = apps.get_model("moduloscm", "Proposta")
    Proposta.objects.update(recebida_em=TruncDate(F("criado_em")))


class Migration(migrations.Migration):

    dependencies = [
        ("moduloscm", "0011_proposta_recebida_em"),
    ]

    operations = [
        migrations.RunPython(copiar_data, migrations.RunPython.noop),
    ]
