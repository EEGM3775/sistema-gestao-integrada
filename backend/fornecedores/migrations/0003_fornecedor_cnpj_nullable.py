from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fornecedores', '0002_dadobancariofornecedor_tenant_fornecedor_tenant_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fornecedor',
            name='cnpj',
            field=models.CharField(
                blank=True, max_length=18, null=True,
                unique=True, verbose_name='CNPJ'
            ),
        ),
    ]
