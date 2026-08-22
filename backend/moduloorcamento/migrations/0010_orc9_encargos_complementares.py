# ORC.9 — encargos complementares (EPI, exame, alimentação, transporte) viram
# classe própria na composição. Antes caíam em "material", o que escondia que
# eles acompanham a hora de mão de obra **sem** receber encargo social por cima.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloorcamento', '0009_orc7b_aviso_item_descontinuado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='itemorcadoinsumo',
            name='categoria',
            field=models.CharField(choices=[('material', 'Material'), ('mao_de_obra', 'Mão de obra'), ('equipamento', 'Equipamento'), ('encargos_complementares', 'Encargos complementares'), ('outro', 'Outro')], default='material', max_length=24, verbose_name='Categoria'),
        ),
    ]
