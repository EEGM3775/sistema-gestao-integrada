# backend/modulopdca/migrations/0016_pdca5_item_prog_unico_sem_local.py
"""O cartão duplicado quando o compromisso não tem local.

A `pdca_item_prog_unico_por_atividade_local` (0014) inclui `local`, e no Postgres
NULL ≠ NULL: dois cartões da mesma atividade **sem local** passavam pela trava, e
o PPC contava a mesma falha duas vezes — exatamente o que ela existe para
impedir. E o caso não é exceção: muito compromisso de LPS é da frente inteira,
sem endereço fino.

Constraint **parcial**, e não `nulls_distinct=False`, pelo motivo já registrado
na parcela do Orçamento (`orcamento_parcela_unica_sem_etapa`): não depender de
PG 15+.

Achado pelo `testes/e2e/pdca5_programacao_test.py` — a suíte não pegava porque
monta `ItemProgramacao` pelo ORM, um por atividade.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modulopdca', '0015_rls_pdca5'),
        ('nucleo', '0026_rls_lixo'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='itemprogramacao',
            constraint=models.UniqueConstraint(condition=models.Q(('local__isnull', True)), fields=('programacao', 'atividade'), name='pdca_item_prog_unico_sem_local'),
        ),
    ]
