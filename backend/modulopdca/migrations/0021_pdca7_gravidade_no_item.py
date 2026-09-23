"""A gravidade desce para o item — e as fichas já respondidas vêm junto.

*(Decisão do dono, 16/09/2026 — planta §11.15.)* O peso do defeito passou a ser
perguntado **no item**, e a `CheckConstraint` cobra isso de toda linha
reprovada. Item reprovado antes desta migration tem `gravidade` nula, e a
constraint **não entra** com ele assim: o `AddConstraint` cru falha com
`IntegrityError` no primeiro banco que já tenha uma ficha respondida — foi o que
aconteceu no ambiente de desenvolvimento, e aconteceria igual num cliente.

**O backfill não inventa o valor: ele o resgata.** Na escrita anterior a
gravidade era escolhida uma vez na conclusão e gravada **na NC**; então a linha
que gerou NC recebe de volta o peso que aquela NC carregou — é o que a pessoa de
fato escolheu, mesmo que ela tenha escolhido um só para todos. A reprova que
nunca virou NC cai em `menor`, que é o degrau que **não acusa**: subir de menor
é gesto de quem olha; descer de maior seria o sistema tendo afirmado uma
gravidade que ninguém declarou.

**E ele roda sob `rls_bypass()`, que é o que o faz rodar.** A política é
fail-closed e migration não tem tenant armado: sem o bypass a varredura enxerga
**zero linhas**, o backfill não faz nada e o `AddConstraint` seguinte falha —
falha em silêncio pela metade, que é a classe de defeito do D21. Foi exatamente
isso que aconteceu na primeira tentativa desta migration.
"""
from django.db import migrations, models

from nucleo.tenancy import rls_bypass


def herdar_gravidade_da_nc(apps, schema_editor):
    ItemVerificacao = apps.get_model("modulopdca", "ItemVerificacao")
    NaoConformidade = apps.get_model("modulopdca", "NaoConformidade")

    with rls_bypass():
        # A NC guarda o item de origem; o caminho de volta é este.
        de_origem = dict(
            NaoConformidade.objects.filter(item_verificacao__isnull=False)
            .values_list("item_verificacao_id", "gravidade")
        )
        reprovados = ItemVerificacao.objects.filter(
            resultado="nao_conforme", gravidade__isnull=True,
        )
        for item in reprovados.iterator():
            item.gravidade = de_origem.get(item.pk) or "menor"
            item.save(update_fields=["gravidade"])

        # E o outro lado da constraint: peso pendurado em quem não reprovou.
        ItemVerificacao.objects.exclude(resultado="nao_conforme").exclude(
            gravidade__isnull=True,
        ).update(gravidade=None)


def desfazer(apps, schema_editor):
    """Nada a desfazer: o campo inteiro cai com o `AddField` revertido."""


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0020_pdca5_peso_arrasto_encerramento'),
        ('nucleo', '0026_rls_lixo'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemverificacao',
            name='gravidade',
            field=models.CharField(blank=True, choices=[('menor', 'Menor — corrige-se na frente'), ('maior', 'Maior — o serviço não é aceito assim'), ('critica', 'Crítica — para o serviço')], max_length=8, null=True, verbose_name='Gravidade do defeito'),
        ),
        migrations.RunPython(herdar_gravidade_da_nc, desfazer),
        migrations.AddConstraint(
            model_name='itemverificacao',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('gravidade__isnull', False), ('resultado', 'nao_conforme')), models.Q(models.Q(('resultado', 'nao_conforme'), _negated=True), ('gravidade__isnull', True)), _connector='OR'), name='pdca_item_verif_gravidade_coerente'),
        ),
    ]
