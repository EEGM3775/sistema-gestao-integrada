"""Unidade na linha do pedido — o item livre da compra avulsa não tinha onde guardá-la."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloscm', '0006_demanda_origem_plano'),
    ]

    operations = [
        migrations.AddField(
            model_name='itempedido',
            name='unidade',
            field=models.CharField(blank=True, max_length=20, verbose_name='Unidade'),
        ),
    ]
