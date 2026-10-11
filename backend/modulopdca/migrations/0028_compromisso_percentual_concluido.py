"""O julgamento da semana pelo % concluído da atividade (decisão do dono, 09/10/2026)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0027_contrato_pedido_servico'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemprogramacao',
            name='percentual_concluido',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Concluído no fim da semana (%)'),
        ),
    ]
