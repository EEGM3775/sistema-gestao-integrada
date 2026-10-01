"""Os índices da grade de títulos (itens 51–54 do dono).

A lentidão de Contas a receber não era falta de índice: era o planejador do
Postgres sem estatística da coluna `excluido_em`, criada pela 0015 depois do
último ANALYZE. Ele supunha que `excluido_em IS NULL` deixava 0,5% das linhas
(eram 100%) e escolhia um laço aninhado de 1,9 s por página. O `ANALYZE` depois
de toda migração (`nucleo.apps`) é o conserto; estes índices são a ordem padrão
da grade, só das linhas vivas.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloerp', '0015_remove_notafiscal_nf_numero_unico_por_tenant_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='contapagar',
            index=models.Index(
                condition=models.Q(('excluido_em__isnull', True)),
                fields=['tenant', 'data_vencimento'], name='cp_vencimento_vivo',
            ),
        ),
        migrations.AddIndex(
            model_name='contareceber',
            index=models.Index(
                condition=models.Q(('excluido_em__isnull', True)),
                fields=['tenant', 'data_vencimento'], name='cr_vencimento_vivo',
            ),
        ),
        migrations.AddIndex(
            model_name='boleto',
            index=models.Index(fields=['tenant', 'data_vencimento'], name='boleto_vencimento'),
        ),
    ]
