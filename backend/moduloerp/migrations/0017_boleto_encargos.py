"""Multa e juros embutidos no boleto de segunda via (item 55 do dono)."""
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloerp', '0016_indices_da_grade'),
    ]

    operations = [
        migrations.AddField(
            model_name='boleto',
            name='valor_multa',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Multa embutida'),
        ),
        migrations.AddField(
            model_name='boleto',
            name='valor_juros',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Juros embutidos'),
        ),
    ]
