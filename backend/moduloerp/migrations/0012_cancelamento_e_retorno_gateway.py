from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Cancelamento e retorno do gateway visíveis na UI (erros clicáveis + aba
    Cancelados): `data_cancelamento` na NFS-e/NF-e e no Boleto, e
    `dados_retorno_api` no Boleto (payload cru do Asaas — erro/cancelamento/
    verificação), espelhando o que a NF já tinha.
    """

    dependencies = [
        ('moduloerp', '0011_transacao_data_competencia_lancamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='notafiscalservico',
            name='data_cancelamento',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Data e Hora do Cancelamento'),
        ),
        migrations.AddField(
            model_name='notafiscalproduto',
            name='data_cancelamento',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Data e Hora do Cancelamento'),
        ),
        migrations.AddField(
            model_name='boleto',
            name='data_cancelamento',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Data de Cancelamento'),
        ),
        migrations.AddField(
            model_name='boleto',
            name='dados_retorno_api',
            field=models.JSONField(blank=True, null=True, verbose_name='Retorno do Gateway'),
        ),
    ]
