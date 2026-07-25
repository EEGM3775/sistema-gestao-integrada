# backend/catalogo/migrations/0002_migrar_produto_do_scm.py
"""Promove o antigo `moduloscm.Produto` ao catálogo-mestre `catalogo.Item` (SIL.0).

Copia **preservando o PK** (`produto_id` → `item_id`) para que as 3 FKs do SCM
(oferta/itemdemanda/itempedido) sigam válidas por valor após o repoint em
moduloscm/0004 (que depende desta). Greenfield-safe e idempotente
(`update_or_create`). Cruza tenants → arma o bypass da RLS, como o backfill de
nucleo/0012."""
from django.db import migrations, models


def copiar(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor == "postgresql":
        with conn.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")
    Produto = apps.get_model("moduloscm", "Produto")
    Item = apps.get_model("catalogo", "Item")
    for p in Produto.objects.all().iterator():
        Item.objects.update_or_create(
            item_id=p.produto_id,
            defaults=dict(
                tenant_id=p.tenant_id,
                codigo_interno=p.codigo_interno,
                descricao=p.descricao,
                unidade=p.unidade,
                categoria=p.categoria,
                tipo=p.tipo_item,  # 'material'|'servico' já são válidos no novo enum
                estocavel=(p.tipo_item == "material"),
                consumivel=(p.tipo_item == "material"),
                gtin=p.gtin,
                item_rede_id=p.item_rede_id,
                ativo=p.ativo,
            ),
        )
    # Ressincroniza a sequência do AutoField para novos inserts não colidirem
    # com os PKs preservados.
    max_id = Item.objects.aggregate(m=models.Max("item_id"))["m"]
    if max_id and conn.vendor == "postgresql":
        with conn.cursor() as c:
            c.execute(
                "SELECT setval(pg_get_serial_sequence('catalogo_item', 'item_id'), %s)",
                [max_id],
            )


def reverter(apps, schema_editor):
    # Irreversível na prática (as FKs do SCM passam a apontar catalogo.Item).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0001_initial"),
        ("moduloscm", "0003_pedidocompra_itempedido_avaliacaofornecedor_and_more"),
    ]

    operations = [
        migrations.RunPython(copiar, reverter),
    ]
