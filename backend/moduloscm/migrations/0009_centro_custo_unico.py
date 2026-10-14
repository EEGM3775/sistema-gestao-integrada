"""O centro de custo é um só, o do ERP — docs/modulos/entidades.md §2.

Cada centro de custo do SCM vira um do ERP: o que já existe com o mesmo nome, a
mesma obra e o mesmo empreendimento é reaproveitado; o resto é criado com o tipo
e a referência de estoque de lá, e a entidade da obra (ou do empreendimento, ou
a matriz). A demanda e o pedido passam a apontar para ele, e a tabela do SCM sai.

As tabelas têm RLS fail-closed; a passada liga o bypass só na transação dela.
"""
import django.db.models.deletion
from django.db import migrations, models


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def unificar(apps, schema_editor):
    _bypass(schema_editor)
    Antigo = apps.get_model("moduloscm", "CentroCusto")
    Novo = apps.get_model("moduloerp", "CentroCusto")
    Demanda = apps.get_model("moduloscm", "Demanda")
    PedidoCompra = apps.get_model("moduloscm", "PedidoCompra")
    Obra = apps.get_model("obras", "Obra")
    Empreendimento = apps.get_model("empreendimentos", "Empreendimento")
    Entidade = apps.get_model("entidades", "Entidade")

    def entidade_de(cc):
        if cc.obra_id:
            ent = Obra._base_manager.filter(pk=cc.obra_id).values_list("entidade_id", flat=True).first()
            if ent:
                return ent
        if cc.empreendimento_id:
            propria = (
                Empreendimento._base_manager.filter(pk=cc.empreendimento_id)
                .values_list("entidade_propria_id", "entidade_propria__externa").first()
            )
            if propria and propria[0] and not propria[1]:
                return propria[0]
        return (
            Entidade.objects.filter(tenant_id=cc.tenant_id, externa=False, papel="matriz")
            .order_by("pk").values_list("pk", flat=True).first()
        )

    for cc in Antigo.objects.all():
        novo = Novo.objects.filter(
            tenant_id=cc.tenant_id, nome=cc.nome, obra_id=cc.obra_id, empreendimento_id=cc.empreendimento_id,
        ).order_by("pk").first()
        if novo is None:
            novo = Novo.objects.create(
                tenant_id=cc.tenant_id, entidade_id=entidade_de(cc), nome=cc.nome, codigo=cc.codigo,
                tipo=cc.tipo, empreendimento_id=cc.empreendimento_id, obra_id=cc.obra_id,
                local_estoque_ref=cc.local_estoque_ref, ativo=cc.ativo,
            )
        else:
            novo.tipo = cc.tipo
            novo.local_estoque_ref = novo.local_estoque_ref or cc.local_estoque_ref
            novo.save(update_fields=["tipo", "local_estoque_ref"])
        Demanda.objects.filter(centro_custo_id=cc.pk).update(centro_custo_erp_id=novo.pk)
        PedidoCompra.objects.filter(centro_custo_id=cc.pk).update(centro_custo_erp_id=novo.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("moduloscm", "0008_cobranca_nfe_recebimento"),
        ("moduloerp", "0024_entidades"),
        ("entidades", "0002_dados"),
    ]

    operations = [
        migrations.AddField(
            model_name="demanda",
            name="centro_custo_erp",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+",
                to="moduloerp.centrocusto",
            ),
        ),
        migrations.AddField(
            model_name="pedidocompra",
            name="centro_custo_erp",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+",
                to="moduloerp.centrocusto",
            ),
        ),
        migrations.RunPython(unificar, migrations.RunPython.noop),
        # A troca do esquema fica na 0010: alterar a FK depois de gravar linhas
        # na mesma transação dá "pending trigger events" no Postgres.
    ]
