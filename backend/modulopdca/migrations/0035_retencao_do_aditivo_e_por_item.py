"""O aditivo mexe na retenção (decisão do dono, 11/10/2026): a do contrato
(`retencao_percentual_nova`) e a própria de cada item que ele traz ou toca
(`ItemAditivo` → `ItemContrato.retencao_percentual`), copiada para a linha da
medição no dia em que ela nasce (`ItemMedicao.retencao_percentual`)."""
import django.core.validators
from django.db import migrations, models


def _pct(rotulo):
    return models.DecimalField(
        blank=True, decimal_places=2, max_digits=5, null=True,
        validators=[
            django.core.validators.MinValueValidator(0),
            django.core.validators.MaxValueValidator(100),
        ],
        verbose_name=rotulo,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0034_medicao_retificada'),
    ]

    operations = [
        migrations.AddField(
            model_name='aditivocontrato',
            name='retencao_percentual_nova',
            field=_pct('Nova retenção do contrato (%)'),
        ),
        migrations.AddField(
            model_name='itemaditivo',
            name='retencao_percentual',
            field=_pct('Retenção própria do item (%)'),
        ),
        migrations.AddField(
            model_name='itemcontrato',
            name='retencao_percentual',
            field=_pct('Retenção própria (%)'),
        ),
        migrations.AddField(
            model_name='itemmedicao',
            name='retencao_percentual',
            field=_pct('Retenção própria (%)'),
        ),
    ]
