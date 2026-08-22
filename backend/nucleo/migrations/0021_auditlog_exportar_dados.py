"""R12 — a ação de exportação do `funcoesimpexp` entra no catálogo do AuditLog.

Só `choices`: não muda coluna nem dado, e existe para o `get_acao_display()` e
os filtros da trilha reconhecerem o valor em vez de mostrarem a string crua.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleo", "0020_indiceeconomico_valorindice"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="acao",
            field=models.CharField(
                choices=[
                    ("criar", "Criação"),
                    ("atualizar", "Atualização"),
                    ("excluir", "Exclusão"),
                    ("baixa", "Baixa financeira"),
                    ("emitir_nf", "Emissão de NF"),
                    ("gerar_cobranca", "Geração de cobrança"),
                    ("exportar_lgpd", "Exportação LGPD (portabilidade)"),
                    ("anonimizar_lgpd", "Anonimização LGPD (esquecimento)"),
                    ("visualizar_pii", "Visualização de PII"),
                    ("exportar_dados", "Exportação de dados (import/export)"),
                ],
                max_length=32,
                verbose_name="Ação",
            ),
        ),
    ]
