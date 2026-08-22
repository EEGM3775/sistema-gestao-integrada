"""A coordenada de desenho da folha — a ponte de volta ao que o CAD mostra.

Campo novo e vazio por padrão: folha já convertida não ganha o número
retroativamente, porque ele é **medido na emissão** e não dá para deduzir depois
(é a lição do D90 — refazer a conta da página erra de um jeito que cresce com o
zoom). Quem quiser a coordenada nas pranchas antigas reprocessa a revisão; até
lá a tela mostra as réguas dela e não finge coordenada de desenho.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloprancheta', '0013_medicao_valor_anterior'),
    ]

    operations = [
        migrations.AddField(
            model_name='desenhoprojeto',
            name='mundo',
            field=models.JSONField(blank=True, default=dict, verbose_name='Coordenada de desenho'),
        ),
    ]
