"""O centro de custo é um só, o do ERP — a troca do esquema (docs/modulos/entidades.md §2).

A 0009 copiou os centros do SCM para o ERP e apontou a demanda e o pedido para
eles numa coluna nova. Aqui a coluna antiga sai, a nova toma o nome dela e a
tabela do SCM é apagada. Fica numa migration à parte porque o Postgres recusa
alterar a FK na mesma transação em que as linhas foram gravadas ("pending
trigger events").
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("moduloscm", "0009_centro_custo_unico"),
    ]

    operations = [
        migrations.RemoveField(model_name="demanda", name="centro_custo"),
        migrations.RemoveField(model_name="pedidocompra", name="centro_custo"),
        migrations.RenameField(model_name="demanda", old_name="centro_custo_erp", new_name="centro_custo"),
        migrations.RenameField(model_name="pedidocompra", old_name="centro_custo_erp", new_name="centro_custo"),
        migrations.AlterField(
            model_name="demanda",
            name="centro_custo",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="demandas", to="moduloerp.centrocusto", verbose_name="Centro de custo",
            ),
        ),
        migrations.AlterField(
            model_name="pedidocompra",
            name="centro_custo",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="pedidos", to="moduloerp.centrocusto", verbose_name="Centro de custo",
            ),
        ),
        migrations.DeleteModel(name="CentroCusto"),
    ]
