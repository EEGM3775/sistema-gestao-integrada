"""
PRA.3b — procedência da escala: o desenho passa a poder declarar a própria régua.

Até aqui toda escala vinha de uma pessoa traçando sobre uma cota conhecida, e o
campo não precisava dizer de onde tinha vindo — só havia uma origem. Com o motor
extraindo a unidade real do DXF/DWG (`$INSUNITS`), passam a existir duas, e elas
**não valem o mesmo**: a derivada pode ser refeita por uma reconversão, a humana
não pode ser tocada por máquina nenhuma.

O backfill é o que impede essa regra de nascer quebrada. Uma revisão calibrada
antes desta migração ficaria com `escala_origem = ''`, que `pode_derivar_escala`
lê como "pode sobrescrever" — e o primeiro reprocessamento apagaria, em silêncio,
o trabalho de quem foi conferir a cota no desenho. Marcar essas linhas como
`calibrada` é barato aqui e impossível depois.

Roda sob **bypass** explícito da RLS, pela mesma razão do backfill da Fase 8.2:
a política fail-closed mostra ao role de aplicação só as linhas do tenant armado,
e uma migração não tem tenant armado — sem o bypass ela varreria zero linha e
diria que deu tudo certo. No-op fora do PostgreSQL.
"""
from django.db import migrations, models


def _arm_bypass(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def marcar_calibracoes_existentes(apps, schema_editor):
    _arm_bypass(schema_editor)
    Revisao = apps.get_model("moduloprancheta", "RevisaoDocumento")
    # `escala_calibrada_em` preenchido é a assinatura do verbo `calibrar/`: era o
    # único caminho que escrevia escala antes desta fatia.
    Revisao.objects.filter(
        escala_calibrada_em__isnull=False, escala_origem=""
    ).update(escala_origem="calibrada")


def desmarcar(apps, schema_editor):
    """Reverso: devolve o campo ao vazio, que é como a coluna nasce.

    A calibração em si (valor, referência, autor, data) não é tocada em nenhuma
    das direções — este campo só carimba a procedência.
    """
    _arm_bypass(schema_editor)
    Revisao = apps.get_model("moduloprancheta", "RevisaoDocumento")
    Revisao.objects.filter(escala_origem="calibrada").update(escala_origem="")


class Migration(migrations.Migration):

    dependencies = [
        ("moduloprancheta", "0004_pra3_marcacao_bcf"),
    ]

    operations = [
        migrations.AddField(
            model_name="revisaodocumento",
            name="escala_origem",
            field=models.CharField(
                blank=True,
                choices=[
                    ("desenho", "Declarada pelo desenho"),
                    ("calibrada", "Calibrada por uma pessoa"),
                ],
                default="",
                max_length=10,
                verbose_name="Procedência da escala",
            ),
        ),
        migrations.RunPython(marcar_calibracoes_existentes, desmarcar),
    ]
