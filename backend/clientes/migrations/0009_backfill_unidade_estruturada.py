"""Backfill do rótulo livre `unidade_comprada` para os campos estruturados.

Conservador **por desenho**: só preenche quando o texto é inequívoco
("QD 12 LT 05", "Quadra 3 - Lote 12", "Bloco A Apto 302"). Texto que não casa
fica intacto e a unidade continua se identificando pelo rótulo livre — errar o
lote de um cliente é pior do que deixar o campo vazio para alguém preencher.

Reversível: a migration de volta apenas limpa os campos estruturados, sem tocar
no `unidade_comprada`, que nunca é reescrito aqui.
"""
import re

from django.db import migrations

# "QD 12 LT 05" · "Q12 L5" · "QUADRA 12 - LOTE 05" · "quadra 3, lote 7"
QUADRA_LOTE = re.compile(
    r"\bQ(?:UADRA|D)?\.?\s*[:\-]?\s*([0-9A-Z]{1,6})\b.{0,6}?\bL(?:OTE|T)?\.?\s*[:\-]?\s*([0-9A-Z]{1,6})\b",
    re.IGNORECASE,
)
# "BLOCO A APTO 302" · "TORRE 2 UNIDADE 101" · "Bl. B - Ap 45"
BLOCO_UNIDADE = re.compile(
    r"\b(?:BL(?:OCO|\.)?|TORRE|TR)\s*[:\-]?\s*([0-9A-Z]{1,6})\b.{0,8}?\b(?:AP(?:TO?|ARTAMENTO)?|UN(?:IDADE)?)\.?\s*[:\-]?\s*([0-9A-Z]{1,8})\b",
    re.IGNORECASE,
)


def preencher(apps, schema_editor):
    ClienteEmpreendimento = apps.get_model("clientes", "ClienteEmpreendimento")
    pendentes = []
    for aq in ClienteEmpreendimento.objects.filter(quadra="", lote="", bloco_torre="", unidade=""):
        texto = (aq.unidade_comprada or "").strip()
        if not texto:
            continue
        casou = QUADRA_LOTE.search(texto)
        if casou:
            aq.quadra, aq.lote = casou.group(1).upper(), casou.group(2).upper()
            pendentes.append(aq)
            continue
        casou = BLOCO_UNIDADE.search(texto)
        if casou:
            aq.bloco_torre, aq.unidade = casou.group(1).upper(), casou.group(2).upper()
            pendentes.append(aq)
    if pendentes:
        ClienteEmpreendimento.objects.bulk_update(
            pendentes, ["quadra", "lote", "bloco_torre", "unidade"], batch_size=500
        )


def limpar(apps, schema_editor):
    ClienteEmpreendimento = apps.get_model("clientes", "ClienteEmpreendimento")
    ClienteEmpreendimento.objects.all().update(quadra="", lote="", bloco_torre="", andar="", unidade="")


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0008_clienteempreendimento_andar_and_more"),
    ]

    operations = [
        migrations.RunPython(preencher, limpar),
    ]
