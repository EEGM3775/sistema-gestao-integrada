# L7: `data_transacao` passa a ser a data de COMPETÊNCIA (data real do
# pagamento), deixando de ser `auto_now_add`; a data de lançamento no sistema
# (carimbo imutável de auditoria) migra para o novo campo `data_lancamento`.
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloerp', '0010_alter_notafiscal_chave_acesso_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transacao',
            name='data_transacao',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Data da Transação (competência)'),
        ),
        migrations.AddField(
            model_name='transacao',
            name='data_lancamento',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='Data de Lançamento no Sistema'),
            preserve_default=False,
        ),
    ]
