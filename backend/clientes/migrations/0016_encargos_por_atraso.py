"""Multa e juros de mora na venda (item 55 do dono) — o que a segunda via de um
título vencido soma ao saldo. Padrão e teto em `payment/planos.py` §5.5s."""
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0015_remove_plano_de_campos_soltos'),
    ]

    operations = [
        migrations.AddField(
            model_name='clienteempreendimento',
            name='multa_atraso_percentual',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('2.00'), max_digits=5,
                help_text='Cobrada uma vez sobre o saldo vencido. Venda a consumidor: até 2% (CDC).',
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0')),
                    django.core.validators.MaxValueValidator(Decimal('10.00')),
                ],
                verbose_name='Multa por atraso (%)',
            ),
        ),
        migrations.AddField(
            model_name='clienteempreendimento',
            name='juros_mora_mensal_percentual',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('1.00'), max_digits=5,
                help_text='Pró-rata por dia de atraso.',
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0')),
                    django.core.validators.MaxValueValidator(Decimal('1.00')),
                ],
                verbose_name='Juros de mora (% ao mês)',
            ),
        ),
    ]
