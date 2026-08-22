# D57 — o motivo de erro do teto de recurso.
#
# Só `choices`, como a 0007: nenhuma coluna muda e nada é reescrito. A migration
# existe porque `choices` mora no estado do Django.
#
# **Por que um motivo novo em vez de reusar `tempo_excedido`.** Aquele é
# `retentavel = True`, e repetir uma conversão que estourou o orçamento reproduz o
# estouro — três vezes, por conta da DLQ. E `falha_motor` diria que o motor
# quebrou, quando ele foi **interrompido por nós**: são filas diferentes no
# cockpit (o que consertamos × o limite que impusemos) e frases diferentes na
# tela. Ver `limites.py` e o D57.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moduloprancheta', '0007_pra1b_motivos_sem_dono'),
    ]

    operations = [
        migrations.AlterField(
            model_name='derivadaprojeto',
            name='erro_motivo',
            field=models.CharField(blank=True, choices=[('motor_insuficiente', 'Exige o motor de alta fidelidade'), ('motor_indisponivel', 'Motor não instalado neste servidor'), ('arquivo_corrompido', 'Arquivo ilegível ou corrompido'), ('versao_nao_suportada', 'Versão do formato não suportada'), ('tempo_excedido', 'Tempo de conversão excedido'), ('falha_motor', 'Falha interna do motor'), ('desenho_vazio', 'O arquivo não tem desenho dentro'), ('referencia_ausente', 'Referências externas não enviadas'), ('sem_preview', 'O arquivo não traz miniatura embutida'), ('recurso_excedido', 'Passou do limite de processamento')], max_length=22, verbose_name='Motivo do erro'),
        ),
    ]
