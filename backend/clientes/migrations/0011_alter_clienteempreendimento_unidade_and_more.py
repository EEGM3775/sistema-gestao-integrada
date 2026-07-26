"""A unidade sai da venda e vira cadastro do empreendimento.

**Migration destrutiva, e de propósito.** Os campos antigos (`unidade_comprada`
livre, `endereco_unidade`, quadra/lote/bloco/andar/unidade digitados na venda)
são apagados: o mesmo lote podia ser descrito de dois jeitos em duas aquisições,
e não existe regra automática que decida qual das duas descrições vira a
`Unidade` canônica. Em vez de adivinhar, a base é recriada (decisão do ambiente
de dev, 26/07) e o seed nasce no formato novo.

Rodando sobre uma base com aquisições, o fechamento do campo para não-nulo falha
alto — que é o comportamento certo: migrar em silêncio aqui inventaria vínculos
entre pessoas e imóveis.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0010_alter_clienteempreendimento_unique_together_and_more'),
        ('empreendimentos', '0007_unidade'),
        ('nucleo', '0019_notificacao_rls'),
    ]

    operations = [
        # Fora os campos que a venda não deve mais possuir. `unidade` era um
        # CharField com o número do apartamento; some junto e volta como FK.
        migrations.RemoveField(model_name='clienteempreendimento', name='unidade'),
        migrations.RemoveField(model_name='clienteempreendimento', name='unidade_comprada'),
        migrations.RemoveField(model_name='clienteempreendimento', name='endereco_unidade'),
        migrations.RemoveField(model_name='clienteempreendimento', name='quadra'),
        migrations.RemoveField(model_name='clienteempreendimento', name='lote'),
        migrations.RemoveField(model_name='clienteempreendimento', name='bloco_torre'),
        migrations.RemoveField(model_name='clienteempreendimento', name='andar'),

        # Entra o vínculo. Nasce nulo para o schema poder ser criado e fecha em
        # seguida: numa base com linhas, é o `AlterField` que estoura — o aviso
        # explícito de que há aquisição sem unidade cadastrada.
        migrations.AddField(
            model_name='clienteempreendimento',
            name='unidade',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.RESTRICT,
                related_name='aquisicoes', to='empreendimentos.unidade',
                verbose_name='Unidade',
            ),
        ),
        migrations.AlterField(
            model_name='clienteempreendimento',
            name='unidade',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT, related_name='aquisicoes',
                to='empreendimentos.unidade', verbose_name='Unidade',
            ),
        ),
        migrations.AddConstraint(
            model_name='clienteempreendimento',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'unidade'), name='aquisicao_unica_por_unidade',
            ),
        ),
        migrations.AlterField(
            model_name='clienteempreendimento',
            name='valor_compra',
            field=models.DecimalField(
                decimal_places=2, max_digits=20, verbose_name='Valor negociado (à vista)',
            ),
        ),
    ]
