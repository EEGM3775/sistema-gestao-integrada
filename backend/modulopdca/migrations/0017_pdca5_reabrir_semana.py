# backend/modulopdca/migrations/0017_pdca5_reabrir_semana.py
"""A semana encerrada deixa de ser um beco.

`julgar_itens` só aceita programação **comprometida**, então um julgamento
errado — "saiu" no que não saiu, a causa trocada na pressa da reunião — ficava
para sempre. E o que estraga não é o índice: é o **ranking de causas**, que é o
que decide o que a empresa muda na semana seguinte. Uma causa errada contada
durante um ano manda a obra consertar o problema que ela não tem.

Quatro campos, e nenhum deles muda o PPC: ele continua **derivado, nunca
gravado** (§4.9). O que eles guardam é a **correção**, para que ela apareça —
que é o que faz reabrir ser diferente de reescrever a história. Quem lê a série
vê quais semanas foram reabertas, e a reunião que discutiu o número antigo não é
contrariada em silêncio.

Sem prazo para reabrir, de propósito: erro achado tarde é o mais caro de não
poder consertar, e a retificadora da medição — que mexe em dinheiro — também não
tem prazo. O que protege o histórico é a correção aparecer, não a porta trancada.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0016_pdca5_item_prog_unico_sem_local'),
    ]

    operations = [
        migrations.AddField(
            model_name='programacaosemanal',
            name='motivo_reabertura',
            field=models.TextField(blank=True, verbose_name='Motivo da reabertura'),
        ),
        migrations.AddField(
            model_name='programacaosemanal',
            name='reaberta_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Reaberta em'),
        ),
        migrations.AddField(
            model_name='programacaosemanal',
            name='reaberta_por',
            field=models.CharField(blank=True, max_length=150, verbose_name='Reaberta por'),
        ),
        migrations.AddField(
            model_name='programacaosemanal',
            name='vezes_reaberta',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Vezes reaberta'),
        ),
    ]
