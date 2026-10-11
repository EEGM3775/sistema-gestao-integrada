from django.db import migrations, models


class Migration(migrations.Migration):
    """Os três níveis do `docs/modulos/funcoesnotificacoes.md` (Saber · Decidir ·
    Agir já). O que já existe nasceu como aviso sem ação — nível 1."""

    dependencies = [
        ('nucleo', '0030_indice_unico'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='nivel',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Saber'), (2, 'Decidir'), (3, 'Agir já')], default=1, verbose_name='Nível'),
        ),
    ]
