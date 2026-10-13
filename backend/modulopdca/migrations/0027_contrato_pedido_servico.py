"""Medição × compra de serviço: o contrato de empreitada aponta o pedido do Suprimentos."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0026_compromisso_requisicao'),
        ('moduloscm', '0006_demanda_origem_plano'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoobra',
            name='pedido_scm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='contratos_pdca', to='moduloscm.pedidocompra', verbose_name='Pedido de serviço (Suprimentos)'),
        ),
    ]
