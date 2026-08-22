# backend/moduloprancheta/migrations/0003_pra1_pipeline_conversao.py
"""PRA.1 — o que o pipeline de conversão acrescenta à `DerivadaProjeto`.

Escrita à mão pelo mesmo motivo da `0001` (o venv do host não tem GDAL desde o
MAP.0, então `makemigrations` só roda dentro do container). Confira com
`manage.py makemigrations --check --dry-run` antes de aplicar.

Três mudanças, e todas existem por causa de uma decisão do pipeline:

- **`hash_origem`** — a metade da chave de idempotência que faltava. A outra é
  `motor_versao`, que já existia; juntas respondem "esta derivada ainda vale?"
  sem flag manual. Nasce vazio no acervo já convertido do PRA.0 (não há nenhum),
  e vazio ≠ hash da revisão, então a primeira passada reconverte — que é o
  comportamento certo para uma linha de origem desconhecida.
- **`memoria`** — a memória de conversão que a planta §5 pede. É o que o
  `medir_cobertura_dwg` agrega e o que dá ao projetista uma resposta melhor que
  "deu erro" (qual versão de DWG, qual schema de IFC, se o DXF precisou de
  reparo).
- **`erro_motivo`** ganha `motor_indisponivel`, separando "o seu arquivo exige o
  motor premium" (limite de plano, upsell honesto) de "o motor não está nesta
  imagem" (problema nosso). Trocar os dois mandaria o cliente pagar por um
  binário que esquecemos de instalar.

RLS não muda: a política da `0002` é da tabela, não das colunas.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("moduloprancheta", "0002_rls_fail_closed"),
    ]

    operations = [
        migrations.AddField(
            model_name="derivadaprojeto",
            name="hash_origem",
            field=models.CharField(blank=True, max_length=64, verbose_name="SHA-256 da origem"),
        ),
        migrations.AddField(
            model_name="derivadaprojeto",
            name="memoria",
            field=models.JSONField(blank=True, default=dict, verbose_name="Memória de conversão"),
        ),
        migrations.AlterField(
            model_name="derivadaprojeto",
            name="erro_motivo",
            field=models.CharField(
                blank=True,
                choices=[
                    ("motor_insuficiente", "Exige o motor de alta fidelidade"),
                    ("motor_indisponivel", "Motor não instalado neste servidor"),
                    ("arquivo_corrompido", "Arquivo ilegível ou corrompido"),
                    ("versao_nao_suportada", "Versão do formato não suportada"),
                    ("tempo_excedido", "Tempo de conversão excedido"),
                    ("falha_motor", "Falha interna do motor"),
                ],
                max_length=22,
                verbose_name="Motivo do erro",
            ),
        ),
    ]
