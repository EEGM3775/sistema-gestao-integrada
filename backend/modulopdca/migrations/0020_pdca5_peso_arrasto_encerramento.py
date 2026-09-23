"""PDCA.5 — o peso do compromisso, o arrasto e o encerramento antecipado.

Três achados do dono na mesma leva (15/09/2026), e os três mexem no mesmo lugar
porque são o mesmo lugar: o quadro da semana.

1. **O PPC passa a ser ponderado.** Contar cartões dizia que assumir a
   concretagem da laje e assumir a limpeza do canteiro valem o mesmo. `peso` e
   `peso_origem` guardam quanto cada compromisso vale e de onde o número saiu —
   orçamento, peso do planejador ou duração, nessa ordem
   (`services.peso_do_compromisso`). **Congelado quando o cartão nasce**, como o
   `retencao_percentual_aplicado` da medição: reprecificar o orçamento em
   dezembro não pode reescrever o PPC que a reunião de agosto leu.

2. **O que não saiu segue para a semana seguinte.** `arrastado_de` aponta para o
   cartão de trás e `vezes_arrastado` conta. Um serviço na quarta semana seguida
   é o que a reunião precisa ver antes do índice, e ninguém enxergaria isso
   cruzando quadros à mão.

3. **A semana que ainda não acabou não se encerra sem alçada e sem motivo.**
   `encerrada_antes_do_fim` e `motivo_encerramento_antecipado` marcam o ponto na
   série: um PPC apurado na terça não é comparável com um apurado no domingo, e
   antes disto os dois eram indistinguíveis.

**O backfill só toca em quadro aberto.** Semana **encerrada** fica sem peso de
propósito: ela cai na base `igual` da leitura, que reproduz exatamente o índice
que aquela reunião já viu. Preencher peso para trás reescreveria história —
o PPC de uma semana de julho mudaria porque alguém vinculou o cronograma ao
orçamento em setembro, e a diretoria que lembra de 60% veria 72% sem explicação.
É a mesma régua que faz a medição aprovada congelar.

Reversível: a volta apaga os campos novos e nada mais.
"""

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def congelar_pesos_dos_quadros_abertos(apps, schema_editor):
    """A escada do `services.peso_do_compromisso`, aplicada uma vez.

    Repetida aqui, e não importada, porque migration que chama `services` passa
    a depender do código de hoje para rodar amanhã — a primeira mudança na
    escada quebraria a reconstrução do banco do zero. O preço é esta duplicação,
    de dez linhas, e ela é o preço certo.
    """
    ItemProgramacao = apps.get_model("modulopdca", "ItemProgramacao")
    pendentes = []
    consulta = (
        ItemProgramacao.objects
        .exclude(programacao__status="encerrada")
        .select_related("atividade", "atividade__item_orcado")
    )
    for item in consulta.iterator(chunk_size=500):
        atividade = item.atividade
        orcado = getattr(atividade, "item_orcado", None)
        if orcado is not None and (orcado.total_com_bdi or 0) > 0:
            item.peso, item.peso_origem = orcado.total_com_bdi, "orcado"
        elif (atividade.peso_informado or 0) > 0:
            item.peso, item.peso_origem = atividade.peso_informado, "informado"
        elif atividade.duracao_dias:
            item.peso, item.peso_origem = (
                Decimal(atividade.duracao_dias), "duracao",
            )
        else:
            # Marco, ou atividade sem régua nenhuma. Nulo é a resposta honesta:
            # o cartão conta em `comprometidos` e fica fora da divisão, e a
            # leitura diz quantos são (`sem_peso`).
            continue
        pendentes.append(item)
        if len(pendentes) >= 500:
            ItemProgramacao.objects.bulk_update(
                pendentes, ["peso", "peso_origem"],
            )
            pendentes = []
    if pendentes:
        ItemProgramacao.objects.bulk_update(pendentes, ["peso", "peso_origem"])


def esquecer_pesos(apps, schema_editor):
    ItemProgramacao = apps.get_model("modulopdca", "ItemProgramacao")
    ItemProgramacao.objects.all().update(peso=None, peso_origem="")


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0019_rls_pdca7'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemprogramacao',
            name='arrastado_de',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='arrastos', to='modulopdca.itemprogramacao', verbose_name='Arrastado do compromisso'),
        ),
        migrations.AddField(
            model_name='itemprogramacao',
            name='peso',
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True, verbose_name='Peso do compromisso'),
        ),
        migrations.AddField(
            model_name='itemprogramacao',
            name='peso_origem',
            field=models.CharField(blank=True, max_length=12, verbose_name='Origem do peso'),
        ),
        migrations.AddField(
            model_name='itemprogramacao',
            name='vezes_arrastado',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Semanas arrastado'),
        ),
        migrations.AddField(
            model_name='programacaosemanal',
            name='encerrada_antes_do_fim',
            field=models.BooleanField(default=False, verbose_name='Encerrada antes do fim da semana'),
        ),
        migrations.AddField(
            model_name='programacaosemanal',
            name='motivo_encerramento_antecipado',
            field=models.TextField(blank=True, verbose_name='Motivo do encerramento antecipado'),
        ),
        migrations.RunPython(
            congelar_pesos_dos_quadros_abertos, esquecer_pesos,
        ),
    ]
