from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('empreendimentos', '0002_contabancariaempreendimento_tenant_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='custoempreendimento',
            name='chave_acesso',
            field=models.CharField(
                blank=True, max_length=44, null=True, unique=True,
                verbose_name='Chave de Acesso NF-e'
            ),
        ),
        migrations.AlterField(
            model_name='custoempreendimento',
            name='arquivo_xml',
            field=models.FileField(
                blank=True, null=True, upload_to='nfe_xmls/%Y/%m/',
                verbose_name='Arquivo XML NF-e'
            ),
        ),
    ]
