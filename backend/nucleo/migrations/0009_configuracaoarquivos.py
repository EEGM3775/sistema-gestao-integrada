from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0008_remove_perfil_permissao'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracaoArquivos',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_tamanho_mb', models.PositiveSmallIntegerField(default=10, verbose_name='Tamanho máximo (MB)')),
                ('tipos_aceitos', models.JSONField(
                    default=list,
                    help_text='Ex: ["application/pdf","image/jpeg","image/png"]. Lista vazia = todos os tipos.',
                    verbose_name='Tipos MIME aceitos',
                )),
                ('tenant', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='configuracao_arquivos',
                    to='nucleo.tenant',
                    verbose_name='Tenant',
                )),
            ],
            options={
                'verbose_name': 'Configuração de Arquivos',
                'verbose_name_plural': 'Configurações de Arquivos',
            },
        ),
    ]
