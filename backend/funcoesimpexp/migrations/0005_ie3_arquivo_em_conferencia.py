# backend/funcoesimpexp/migrations/0005_ie3_arquivo_em_conferencia.py
"""IE.3 — a área de conferência passa a guardar binário, não só valores.

Um campo só, e ele é o que permite à R1 valer para arquivo: numa importação de
linhas nada precisa esperar em disco (os valores cabem no JSON e o binário é
lido e descartado), mas um lote de pranchas tem bytes que precisam existir entre
o upload e a decisão — e o lugar deles é a conferência, não o acervo.

Sem RLS nova: o campo entra numa tabela (`LinhaImportacao`) que já está em
`FORCE ROW LEVEL SECURITY` com a política fail-closed desde a
[0002](0002_rls_fail_closed.py). É o contrário do padrão de "RLS na mesma
migration que cria a tabela" — aqui não há tabela nova, e recriar a política
seria repetir o que já vale.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("funcoesimpexp", "0004_rls_mapa_colunas"),
    ]

    operations = [
        migrations.AddField(
            model_name="linhaimportacao",
            name="arquivo",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="impexp/conferencia/%Y/%m/",
                verbose_name="Arquivo em conferência",
            ),
        ),
    ]
