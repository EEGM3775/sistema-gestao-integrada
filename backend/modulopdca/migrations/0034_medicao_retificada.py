"""A retificadora passa a guardar a medição corrigida **inteira** (11/10/2026).

Até aqui ela guardava só a diferença e a original continuava aprovada — duas
medições aprovadas para o mesmo período. Agora a original aprovada que uma
retificadora substituiu vira `retificada`, e a retificadora é a medição certa.

A conversão dos dados que já existem:

- retificadora **cancelada sem título** é apagada — nunca produziu efeito, e o
  dono pediu que esse lixo saia do banco;
- toda outra retificadora ganha as linhas inteiras: `original + diferença` por
  item (o estoque já era gravado como saldo, então vale o dela quando há linha);
  e os descontos da original entram antes dos dela;
- a original de retificadora **aprovada** vira `retificada`.

Corre em ordem de número, para que a retificadora de uma retificadora leia a
anterior já convertida.
"""
from django.db import migrations, models


def converter(apps, schema_editor):
    Medicao = apps.get_model("modulopdca", "Medicao")
    ItemMedicao = apps.get_model("modulopdca", "ItemMedicao")
    DeducaoMedicao = apps.get_model("modulopdca", "DeducaoMedicao")

    ContentType = apps.get_model("contenttypes", "ContentType")
    PedidoAprovacao = apps.get_model("nucleo", "PedidoAprovacao")
    tipo = ContentType.objects.filter(app_label="modulopdca", model="medicao").first()

    retificadoras = Medicao.objects.filter(retifica__isnull=False).order_by("contrato_id", "numero")
    for nova in retificadoras:
        if nova.status == "cancelada" and not nova.conta_pagar_ref and not nova.conta_receber_ref:
            # A `GenericRelation` não existe no model histórico: a escada da
            # retificadora sai à mão.
            if tipo is not None:
                PedidoAprovacao.objects.filter(alvo_tipo=tipo, alvo_id=nova.pk).delete()
            nova.delete()
            continue
        if nova.status == "cancelada":
            continue

        original = Medicao.objects.get(pk=nova.retifica_id)
        dela = {l.item_contrato_id: l for l in ItemMedicao.objects.filter(medicao=nova)}
        for linha in ItemMedicao.objects.filter(medicao=original):
            minha = dela.pop(linha.item_contrato_id, None)
            if minha is None:
                ItemMedicao.objects.create(
                    tenant_id=nova.tenant_id, medicao=nova,
                    item_contrato_id=linha.item_contrato_id,
                    quantidade=linha.quantidade,
                    quantidade_estocada=linha.quantidade_estocada,
                    quantidade_proposta=linha.quantidade_proposta,
                    preco_unitario=linha.preco_unitario,
                    percentual_avanco_periodo=linha.percentual_avanco_periodo,
                    origem=linha.origem, observacao=linha.observacao,
                )
            else:
                minha.quantidade = linha.quantidade + minha.quantidade
                minha.save(update_fields=["quantidade"])
        for d in DeducaoMedicao.objects.filter(medicao=original):
            DeducaoMedicao.objects.create(
                tenant_id=nova.tenant_id, medicao=nova, tipo=d.tipo,
                descricao=d.descricao, base_calculo=d.base_calculo,
                percentual=d.percentual, valor=d.valor,
            )
        if nova.status == "aprovada" and original.status == "aprovada":
            Medicao.objects.filter(pk=original.pk).update(status="retificada")


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0033_liberacaoretencao_conta_receber_ref'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medicao',
            name='status',
            field=models.CharField(choices=[('rascunho', 'Rascunho'), ('em_aprovacao', 'Em aprovação'), ('aprovada', 'Aprovada'), ('reprovada', 'Reprovada'), ('cancelada', 'Cancelada'), ('retificada', 'Retificada')], default='rascunho', max_length=12, verbose_name='Status'),
        ),
        migrations.RunPython(converter, migrations.RunPython.noop),
    ]
