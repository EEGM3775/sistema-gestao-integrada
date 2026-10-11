"""A restrição removida pode voltar a ser aberta — registrada, não apagada."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0023_rls_pdca8'),
    ]

    operations = [
        migrations.AddField(
            model_name='restricao',
            name='reaberta_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Reaberta em'),
        ),
        migrations.AddField(
            model_name='restricao',
            name='reaberta_por',
            field=models.CharField(blank=True, max_length=150, verbose_name='Reaberta por'),
        ),
        migrations.AddField(
            model_name='restricao',
            name='vezes_reaberta',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Vezes reaberta'),
        ),
    ]
