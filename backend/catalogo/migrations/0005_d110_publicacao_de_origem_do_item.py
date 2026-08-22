# D110 — o item adotado passa a guardar de qual **edição** ele veio.
#
# Até aqui a procedência inteira do item era o par (fonte, código): dava para
# dizer "veio da SINAPI, código 1379" e não "veio da SINAPI BA 10/2024". Sem a
# edição não há como responder de onde saiu a descrição gravada — que é a
# pergunta da conferência de identidade da adoção.
#
# Campo aditivo e opcional: os itens já adotados ficam com o rótulo vazio (não
# há como inferir a edição retroativamente sem inventar) e o preenchem na
# próxima re-adoção.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0004_orc9_mao_de_obra_e_tipo_proprio"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="publicacao_referencia",
            field=models.CharField(
                blank=True,
                help_text="Edição da base (ou banco) de onde o item foi adotado.",
                max_length=120,
                verbose_name="Publicação de origem",
            ),
        ),
    ]
