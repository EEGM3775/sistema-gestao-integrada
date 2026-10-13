"""Converte as retificadoras que já existem para a medição inteira — **com o
bypass da RLS** (11/10/2026).

A 0034 trazia esta conversão sem armar `app.rls_bypass`, e a RLS fail-closed do
staging escondeu todas as linhas: a migration passou em branco, e a tela seguiu
lendo a retificadora antiga (só a diferença) como medição nova contra o saldo.

Três passos, na ordem:

1. retificadora **cancelada sem título** é apagada — nunca produziu efeito (o
   dono pediu que esse lixo saia do banco), e a escada dela vai junto;
2. toda outra retificadora ganha a medição inteira: `original + diferença` por
   item (o estoque já era saldo, então vale o dela quando há linha) e os
   descontos da original antes dos dela;
3. a retificadora **aprovada** cuja original ainda está aprovada é fechada como
   a de hoje (`services._fechar_retificacao`): a original vira `retificada` e o
   título é acertado — em aberto, cancelado e reemitido pelo líquido inteiro; já
   pago, título da diferença e aviso ao ERP.

O passo 3 usa o serviço vivo de propósito: o acerto do título é regra de
negócio, e duplicá-la aqui criaria a segunda verdade. Num banco novo não há
retificadora, e o laço não roda.

Corre em ordem de número, para que a retificadora de uma retificadora leia a
anterior já convertida.
"""
from django.db import migrations


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def converter(apps, schema_editor):
    _bypass(schema_editor)
    Medicao = apps.get_model("modulopdca", "Medicao")
    ItemMedicao = apps.get_model("modulopdca", "ItemMedicao")
    DeducaoMedicao = apps.get_model("modulopdca", "DeducaoMedicao")
    ContentType = apps.get_model("contenttypes", "ContentType")
    PedidoAprovacao = apps.get_model("nucleo", "PedidoAprovacao")
    tipo = ContentType.objects.filter(app_label="modulopdca", model="medicao").first()

    retificadoras = Medicao.objects.filter(retifica__isnull=False).order_by("contrato_id", "numero")
    for nova in retificadoras:
        if nova.status == "cancelada" and not nova.conta_pagar_ref and not nova.conta_receber_ref:
            # A `GenericRelation` não existe no model histórico: a escada sai à mão.
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


def fechar(apps, schema_editor):
    _bypass(schema_editor)
    from modulopdca import services
    from modulopdca.models import Medicao

    pendentes = (
        Medicao.objects.filter(
            status=Medicao.Status.APROVADA, retifica__isnull=False,
            retifica__status=Medicao.Status.APROVADA,
        )
        .select_related("retifica", "contrato")
        .order_by("contrato_id", "numero")
    )
    for retificadora in pendentes:
        campos = services._fechar_retificacao(retificadora)
        if campos:
            retificadora.save(update_fields=campos)


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0035_retencao_do_aditivo_e_por_item'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('nucleo', '0031_notificacao_nivel'),
        ('moduloerp', '0022_integracao_fiscal_e_nf_por_fornecedor'),
    ]

    operations = [
        migrations.RunPython(converter, migrations.RunPython.noop),
        migrations.RunPython(fechar, migrations.RunPython.noop),
    ]
