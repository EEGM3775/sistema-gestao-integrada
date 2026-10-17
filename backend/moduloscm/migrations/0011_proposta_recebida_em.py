"""A proposta digitada pelo comprador (dono, 16/10/2026): quando chegou e o que veio junto.

`recebida_em` nasce com a data de hoje; a 0012 copia para as propostas que já
existem a data em que foram registradas. Ficam separadas porque o Postgres
recusa alterar a tabela na mesma transação em que as linhas foram gravadas.
"""
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("moduloscm", "0010_centro_custo_unico_esquema"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposta",
            name="recebida_em",
            field=models.DateField(default=django.utils.timezone.localdate, verbose_name="Recebida em"),
        ),
        migrations.AddField(
            model_name="proposta",
            name="observacao",
            field=models.TextField(blank=True, verbose_name="Observação"),
        ),
    ]
