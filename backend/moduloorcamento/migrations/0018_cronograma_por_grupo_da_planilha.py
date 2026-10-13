from django.db import migrations, models
import django.db.models.deletion


def etapa_obra_para_grupo(apps, schema_editor):
    """O cronograma deixa de apontar para a `EtapaObra` e passa a apontar para o
    **grupo de 1º nível da planilha** (decisão do dono, 11/10/2026).

    Cada plano antigo (orçamento × etapa da obra) vai para o grupo raiz das
    linhas que tinham aquela etapa, e o vínculo com a etapa da obra é guardado
    no próprio grupo (`ItemOrcado.etapa`) — nada se perde, só muda de lugar.
    Duas etapas da obra que caem no mesmo grupo não cabem em um plano só: fica
    a primeira e a outra é descartada (e contada na saída).
    """
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")
    Item = apps.get_model("moduloorcamento", "ItemOrcado")
    Plano = apps.get_model("moduloorcamento", "PlanoEtapa")
    Parcela = apps.get_model("moduloorcamento", "ParcelaEtapa")

    raiz_cache: dict[int, dict[int, int]] = {}

    def raizes(orcamento_id):
        if orcamento_id not in raiz_cache:
            pais = dict(Item.objects.filter(orcamento_id=orcamento_id).values_list("pk", "pai_id"))
            achado = {}
            for pk in pais:
                atual, visto = pk, set()
                while pais.get(atual) is not None and atual not in visto:
                    visto.add(atual)
                    atual = pais[atual]
                achado[pk] = atual
            raiz_cache[orcamento_id] = achado
        return raiz_cache[orcamento_id]

    descartadas = 0
    mapa: dict[tuple[int, int], int] = {}
    usados: set[tuple[int, int]] = set()
    for plano in Plano.objects.all().order_by("pk"):
        itens = list(Item.objects.filter(
            orcamento_id=plano.orcamento_id, etapa_id=plano.etapa_id, tipo_linha="analitico",
        ).values_list("pk", flat=True))
        if not itens:
            descartadas += 1
            continue
        raiz = raizes(plano.orcamento_id)[itens[0]]
        if (plano.orcamento_id, raiz) in usados:
            descartadas += 1
            continue
        usados.add((plano.orcamento_id, raiz))
        mapa[(plano.orcamento_id, plano.etapa_id)] = raiz
        plano.grupo_id = raiz
        plano.save(update_fields=["grupo"])
        Item.objects.filter(pk=raiz, etapa__isnull=True).update(etapa_id=plano.etapa_id)

    for parcela in Parcela.objects.filter(etapa__isnull=False):
        grupo = mapa.get((parcela.orcamento_id, parcela.etapa_id))
        if grupo is None:
            parcela.delete()
            continue
        parcela.grupo_id = grupo
        parcela.save(update_fields=["grupo"])
    Plano.objects.filter(grupo__isnull=True).delete()
    if descartadas:
        print(f"\n  cronograma por grupo: {descartadas} plano(s) sem grupo correspondente descartado(s).")


class Migration(migrations.Migration):

    dependencies = [
        ('moduloorcamento', '0017_reajuste_vai_para_o_contrato'),
    ]

    operations = [
        migrations.AddField(
            model_name='planoetapa', name='grupo',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='plano_cronograma', to='moduloorcamento.itemorcado',
                                    verbose_name='Etapa do orçamento'),
        ),
        migrations.AddField(
            model_name='parcelaetapa', name='grupo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='parcelas_cronograma', to='moduloorcamento.itemorcado',
                                    verbose_name='Etapa do orçamento'),
        ),
        migrations.RunPython(etapa_obra_para_grupo, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name='parcelaetapa', name='orcamento_parcela_unica_por_mes'),
        migrations.RemoveConstraint(model_name='parcelaetapa', name='orcamento_parcela_unica_sem_etapa'),
        migrations.RemoveConstraint(model_name='planoetapa', name='orcamento_plano_etapa_unico'),
        migrations.AlterModelOptions(
            name='parcelaetapa',
            options={'ordering': ['orcamento', 'grupo', 'competencia'],
                     'verbose_name': 'Parcela do cronograma', 'verbose_name_plural': 'Parcelas do cronograma'},
        ),
        migrations.AlterModelOptions(
            name='planoetapa',
            options={'ordering': ['orcamento', 'grupo__ordem', 'grupo_id'],
                     'verbose_name': 'Etapa planejada', 'verbose_name_plural': 'Etapas planejadas'},
        ),
        migrations.RemoveField(model_name='parcelaetapa', name='etapa'),
        migrations.RemoveField(model_name='planoetapa', name='etapa'),
        migrations.AlterField(
            model_name='planoetapa', name='grupo',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name='plano_cronograma', to='moduloorcamento.itemorcado',
                                    verbose_name='Etapa do orçamento'),
        ),
        migrations.AddConstraint(
            model_name='parcelaetapa',
            constraint=models.UniqueConstraint(fields=('orcamento', 'grupo', 'competencia'),
                                               name='orcamento_parcela_unica_por_mes'),
        ),
        migrations.AddConstraint(
            model_name='parcelaetapa',
            constraint=models.UniqueConstraint(condition=models.Q(('grupo__isnull', True)),
                                               fields=('orcamento', 'competencia'),
                                               name='orcamento_parcela_unica_sem_etapa'),
        ),
        migrations.AddConstraint(
            model_name='planoetapa',
            constraint=models.UniqueConstraint(fields=('orcamento', 'grupo'), name='orcamento_plano_etapa_unico'),
        ),
    ]
