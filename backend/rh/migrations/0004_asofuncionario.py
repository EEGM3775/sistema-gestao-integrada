# Generated manually — refatoração do ASO: de campos únicos em DadoMedicoFuncionario
# para registros múltiplos (um por exame ocupacional/ano) em ASOFuncionario.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0003_cargo_tenant_dadobancariofuncionario_tenant_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='dadomedicofuncionario',
            name='tipo_exame_aso',
        ),
        migrations.RemoveField(
            model_name='dadomedicofuncionario',
            name='data_exame_aso',
        ),
        migrations.RemoveField(
            model_name='dadomedicofuncionario',
            name='data_validade_aso',
        ),
        migrations.RemoveField(
            model_name='dadomedicofuncionario',
            name='status_aso',
        ),
        migrations.RemoveField(
            model_name='dadomedicofuncionario',
            name='link_documento_aso',
        ),
        migrations.CreateModel(
            name='ASOFuncionario',
            fields=[
                ('aso_id', models.AutoField(primary_key=True, serialize=False, verbose_name='ASO ID')),
                ('tipo_exame', models.CharField(choices=[('admissional', 'Admissional'), ('periodico', 'Periódico'), ('demissional', 'Demissional')], max_length=50, verbose_name='Tipo de Exame')),
                ('status', models.CharField(choices=[('ativo', 'Ativo'), ('inativo', 'Inativo'), ('pendente', 'Pendente'), ('cancelado', 'Cancelado')], default='ativo', max_length=50, verbose_name='Status')),
                ('data_exame', models.DateField(verbose_name='Data do Exame')),
                ('data_validade', models.DateField(blank=True, null=True, verbose_name='Data de Validade')),
                ('arquivo', models.FileField(blank=True, null=True, upload_to='asos_funcionarios/', verbose_name='Documento ASO')),
                ('observacoes', models.TextField(blank=True, null=True, verbose_name='Observações')),
                ('funcionario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asos', to='rh.funcionario', verbose_name='Funcionário')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'ASO do Funcionário',
                'verbose_name_plural': 'ASOs dos Funcionários',
                'ordering': ['-data_exame'],
            },
        ),
    ]
