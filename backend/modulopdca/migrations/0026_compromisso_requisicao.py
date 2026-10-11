"""O compromisso da semana guarda a requisição de material que pediu ao almoxarifado."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0025_suprimento_antecedencia'),
        ('modulosil', '0002_movimentacaoestoque_etapa_requisicao_etapa_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemprogramacao',
            name='requisicao_sil',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compromissos_pdca', to='modulosil.requisicao', verbose_name='Requisição de material'),
        ),
    ]
