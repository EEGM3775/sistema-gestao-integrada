"""Os campos soltos do plano saem: o plano é a lista `meios` (ver 0014)."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0014_meios_de_pagamento"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="balao_periodicidade",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="balao_primeiro_vencimento",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="balao_quantidade",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="balao_valor",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="entrada_parcelas",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="entrada_primeiro_vencimento",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="entrada_valor",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="juros_mensal",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="num_parcelas",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="primeiro_vencimento",
        ),
        migrations.RemoveField(
            model_name="clienteempreendimento",
            name="sistema_amortizacao",
        ),
    ]
