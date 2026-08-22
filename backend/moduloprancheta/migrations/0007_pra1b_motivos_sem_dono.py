# PRA.1b — os três motivos de erro que não são de ninguém (D45, D49).
#
# Só `choices`: nenhuma coluna muda de tipo e nada é reescrito no banco. A
# migration existe porque `choices` mora no estado do Django, e sem ela
# `makemigrations --check` fica vermelho para sempre.
#
# **Nenhum backfill, de propósito.** As derivadas que já estão em `falha_motor`
# por desenho vazio ou XREF ausente ficam como estão: reclassificá-las exigiria
# reabrir cada arquivo para saber qual era o caso — a conversão é justamente o
# que não temos —, e adivinhar pelo texto do erro carimbaria motivo errado em
# linha que ninguém conferiria. Elas se reclassificam sozinhas no próximo
# `reprocessar/`, e a versão nova do motor já as invalida por comparação.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloprancheta', '0006_pra1c_desenho_por_folha'),
    ]

    operations = [
        migrations.AlterField(
            model_name='derivadaprojeto',
            name='erro_motivo',
            field=models.CharField(blank=True, choices=[('motor_insuficiente', 'Exige o motor de alta fidelidade'), ('motor_indisponivel', 'Motor não instalado neste servidor'), ('arquivo_corrompido', 'Arquivo ilegível ou corrompido'), ('versao_nao_suportada', 'Versão do formato não suportada'), ('tempo_excedido', 'Tempo de conversão excedido'), ('falha_motor', 'Falha interna do motor'), ('desenho_vazio', 'O arquivo não tem desenho dentro'), ('referencia_ausente', 'Referências externas não enviadas'), ('sem_preview', 'O arquivo não traz miniatura embutida')], max_length=22, verbose_name='Motivo do erro'),
        ),
    ]
