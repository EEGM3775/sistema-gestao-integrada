"""A retificadora passa a guardar a medição corrigida **inteira** (11/10/2026).

Até aqui ela guardava só a diferença e a original continuava aprovada — duas
medições aprovadas para o mesmo período. Agora a original aprovada que uma
retificadora substituiu vira `retificada`, e a retificadora é a medição certa.

A conversão dos dados que já existem mora na 0036 (com o bypass da RLS):

- retificadora **cancelada sem título** é apagada — nunca produziu efeito, e o
  dono pediu que esse lixo saia do banco;
- toda outra retificadora ganha as linhas inteiras: `original + diferença` por
  item (o estoque já era gravado como saldo, então vale o dela quando há linha);
  e os descontos da original entram antes dos dela;
- a original de retificadora **aprovada** vira `retificada`.

Corre em ordem de número, para que a retificadora de uma retificadora leia a
anterior já convertida.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0033_liberacaoretencao_conta_receber_ref'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medicao',
            name='status',
            field=models.CharField(choices=[('rascunho', 'Rascunho'), ('em_aprovacao', 'Em aprovação'), ('aprovada', 'Aprovada'), ('reprovada', 'Reprovada'), ('cancelada', 'Cancelada'), ('retificada', 'Retificada')], default='rascunho', max_length=12, verbose_name='Status'),
        ),
        # A conversão dos dados mudou para a 0036: rodando sem o bypass da RLS, esta
        # não enxergava linha nenhuma e passou em branco no staging (11/10/2026).
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
