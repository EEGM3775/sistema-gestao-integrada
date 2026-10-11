"""A demanda que nasce do cronograma da obra (fila "comprar até" do PDCA)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloscm', '0005_pdca5_lastplanner'),
    ]

    operations = [
        migrations.AlterField(
            model_name='demanda',
            name='origem',
            field=models.CharField(choices=[('manual', 'Manual'), ('estoque', 'Falta no estoque'), ('restricao', 'Restrição de obra (PDCA)'), ('plano', 'Cronograma da obra (PDCA)')], default='manual', max_length=10, verbose_name='Origem'),
        ),
    ]
