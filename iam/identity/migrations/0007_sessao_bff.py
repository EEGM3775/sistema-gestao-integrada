"""Remodelagem da segurança, fase 5: a sessão guarda o que o BFF precisa (§10.5).

A credencial do cookie fica só como hash (sha256 em hex); a sessão aberta antes
desta migration não tem credencial, e ganha uma na primeira renovação.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0006_sessao"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessao",
            name="credencial_hash",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="sessao",
            name="lembrar",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="sessao",
            name="amr",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="sessao",
            name="auth_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sessao",
            name="expira_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
