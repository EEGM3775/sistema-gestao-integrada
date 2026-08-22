"""PRA.1c — o desenho vira entidade, e a escala vai morar nele.

**A premissa que esta migration corrige:** desde a PRA.0 o módulo tratava *uma
revisão* como *uma prancha*. O acervo real desmente: o `confrontantes.dwg` traz a
mesma área desenhada na origem e em coordenada UTM, a 8,5 milhões de unidades uma
da outra, e o `MaxPlast.dwg` traz o projeto e um destaque separado. Emitidos numa
folha só, viravam uma página de 469 m × 8,5 km — que nenhum navegador rasteriza e
onde cada desenho ocupa 0,2% da largura.

Três movimentos, e a ordem entre eles é o que impede perda de dado:

1. **tudo o que é aditivo primeiro** — a tabela nova, as três FKs e a RLS dela;
2. **o backfill**, que cria um `DesenhoProjeto` por revisão já convertida,
   **copiando a escala que estava na revisão** e pendurando nele as derivadas 2D,
   as marcações e as medições que já existiam;
3. **só então a remoção** dos campos de escala da revisão.

Inverter 2 e 3 (que é o que o `makemigrations` propõe, porque ele não sabe que os
dois lados são o mesmo dado) apagaria a calibração de toda prancha já medida no
canteiro antes de haver onde copiá-la.

**A RLS entra aqui, na mesma migration que cria a tabela** — a razão da `0004`,
literal: criar numa migration e proteger na seguinte abre uma janela, curta mas
real, em que a folha de um cliente é legível por qualquer sessão. E o desenho
carrega o projeto.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Helper repetido em vez de importado porque nome de módulo de migration começa
# com dígito e não é importável; é o padrão do repo (ver `0002_rls_fail_closed`).
_TABLES = ("moduloprancheta_desenhoprojeto",)
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for table in _TABLES:
            c.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            c.execute(
                f'CREATE POLICY {POLICY} ON "{table}" '
                f"USING ({USING_CLOSED}) WITH CHECK ({USING_CLOSED});"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for table in _TABLES:
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            c.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


def criar_desenho_das_revisoes(apps, schema_editor):
    """Um desenho por revisão já convertida, herdando a escala que ela tinha.

    **Uma só, e `ordem = 1`**, porque é exatamente o que a revisão era até aqui:
    uma folha. Os desenhos de verdade aparecem na próxima conversão, quando o
    motor separar os aglomerados — e a reconversão é barata porque a
    idempotência do pipeline já compara `hash` + versão de motor.

    Roda com `rls_bypass` pela mesma razão de sempre: migration de dados atravessa
    todos os tenants, e a política fail-closed devolveria zero linha para uma
    sessão sem `app.current_tenant`.
    """
    Revisao = apps.get_model("moduloprancheta", "RevisaoDocumento")
    Desenho = apps.get_model("moduloprancheta", "DesenhoProjeto")
    Derivada = apps.get_model("moduloprancheta", "DerivadaProjeto")
    Marcacao = apps.get_model("moduloprancheta", "Marcacao")
    Medicao = apps.get_model("moduloprancheta", "Medicao")

    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true);")

    # Só revisão que tem derivada 2D: é a que de fato virou folha. Miniatura de
    # PDF e modelo 3D não têm desenho separável, e criar um para elas poria na
    # tela uma folha que ninguém consegue abrir.
    com_folha = set(
        Derivada.objects.filter(tipo="vetor_2d").values_list("revisao_id", flat=True)
    )
    if not com_folha:
        return

    for revisao in Revisao.objects.filter(pk__in=com_folha).iterator():
        desenho = Desenho.objects.create(
            tenant_id=revisao.tenant_id,
            revisao_id=revisao.pk,
            ordem=1,
            nome="",
            caixa={},
            tracos=0,
            escala_valor=revisao.escala_valor,
            escala_unidade=revisao.escala_unidade or "m",
            escala_referencia=revisao.escala_referencia or {},
            escala_origem=revisao.escala_origem or "",
            escala_calibrada_por_id=revisao.escala_calibrada_por_id,
            escala_calibrada_em=revisao.escala_calibrada_em,
        )
        # A âncora das marcações e os vértices das medições já existentes estão
        # no espaço desta folha, que é a mesma de antes — então elas apontam para
        # este desenho sem reposicionamento nenhum. É a compatibilidade que a
        # decisão de **não recortar quando há um desenho só** compra: enquanto a
        # revisão não for reconvertida em várias folhas, nada se move.
        Derivada.objects.filter(revisao_id=revisao.pk, tipo="vetor_2d").update(desenho=desenho.pk)
        Marcacao.objects.filter(revisao_id=revisao.pk).update(desenho=desenho.pk)
        Medicao.objects.filter(revisao_id=revisao.pk).update(desenho=desenho.pk)


def desfazer_backfill(apps, schema_editor):
    """Devolve a escala para a revisão e apaga os desenhos.

    Existe para a migration ser reversível de verdade — a reversão que só derruba
    o esquema perderia a calibração humana, que é justamente o dado que ninguém
    consegue reconstruir sozinho (foi alguém que foi ao desenho conferir a cota).
    """
    Desenho = apps.get_model("moduloprancheta", "DesenhoProjeto")

    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true);")

    for desenho in Desenho.objects.filter(ordem=1).select_related("revisao").iterator():
        revisao = desenho.revisao
        revisao.escala_valor = desenho.escala_valor
        revisao.escala_unidade = desenho.escala_unidade
        revisao.escala_referencia = desenho.escala_referencia
        revisao.escala_origem = desenho.escala_origem
        revisao.escala_calibrada_por_id = desenho.escala_calibrada_por_id
        revisao.escala_calibrada_em = desenho.escala_calibrada_em
        revisao.save()
    Desenho.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('moduloprancheta', '0005_pra3b_escala_do_desenho'),
        ('nucleo', '0020_indiceeconomico_valorindice'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ---- 1. aditivo -----------------------------------------------------
        migrations.CreateModel(
            name='DesenhoProjeto',
            fields=[
                ('desenho_id', models.AutoField(primary_key=True, serialize=False)),
                ('ordem', models.PositiveSmallIntegerField(verbose_name='Ordem')),
                ('nome', models.CharField(blank=True, max_length=120, verbose_name='Nome dado ao desenho')),
                ('caixa', models.JSONField(blank=True, default=dict, verbose_name='Envolvente (unidades de desenho)')),
                ('tracos', models.PositiveIntegerField(default=0, verbose_name='Traços')),
                ('escala_valor', models.FloatField(blank=True, null=True, verbose_name='Unidades reais na largura do desenho')),
                ('escala_unidade', models.CharField(blank=True, default='m', max_length=4, verbose_name='Unidade')),
                ('escala_referencia', models.JSONField(blank=True, default=dict, verbose_name='Referência da calibração')),
                ('escala_origem', models.CharField(blank=True, choices=[('desenho', 'Declarada pelo desenho'), ('calibrada', 'Calibrada por uma pessoa')], default='', max_length=10, verbose_name='Procedência da escala')),
                ('escala_calibrada_em', models.DateTimeField(blank=True, null=True, verbose_name='Calibrada em')),
                ('renomeado_em', models.DateTimeField(blank=True, null=True, verbose_name='Renomeado em')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Desenho de projeto',
                'verbose_name_plural': 'Desenhos de projeto',
                'ordering': ['revisao', 'ordem'],
            },
        ),
        migrations.AddField(
            model_name='desenhoprojeto',
            name='escala_calibrada_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='desenhos_projeto_calibrados', to=settings.AUTH_USER_MODEL, verbose_name='Calibrada por'),
        ),
        migrations.AddField(
            model_name='desenhoprojeto',
            name='herdado_de',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='herdeiros', to='moduloprancheta.desenhoprojeto', verbose_name='Herdou o nome de'),
        ),
        migrations.AddField(
            model_name='desenhoprojeto',
            name='renomeado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='desenhos_projeto_renomeados', to=settings.AUTH_USER_MODEL, verbose_name='Renomeado por'),
        ),
        migrations.AddField(
            model_name='desenhoprojeto',
            name='revisao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='desenhos', to='moduloprancheta.revisaodocumento', verbose_name='Revisão'),
        ),
        migrations.AddField(
            model_name='desenhoprojeto',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant'),
        ),
        migrations.AddIndex(
            model_name='desenhoprojeto',
            index=models.Index(fields=['tenant', 'revisao'], name='prancheta_desenho_revisao_idx'),
        ),
        migrations.AddConstraint(
            model_name='desenhoprojeto',
            constraint=models.UniqueConstraint(fields=('revisao', 'ordem'), name='prancheta_desenho_ordem_por_revisao'),
        ),
        migrations.AddField(
            model_name='derivadaprojeto',
            name='desenho',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='derivadas', to='moduloprancheta.desenhoprojeto', verbose_name='Desenho'),
        ),
        migrations.AddField(
            model_name='marcacao',
            name='desenho',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marcacoes', to='moduloprancheta.desenhoprojeto', verbose_name='Desenho'),
        ),
        migrations.AddField(
            model_name='medicao',
            name='desenho',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medicoes', to='moduloprancheta.desenhoprojeto', verbose_name='Desenho'),
        ),

        # ---- 2. a política, antes de a tabela ter linha ----------------------
        migrations.RunPython(enable_rls, disable_rls),

        # ---- 3. o dado, antes de a origem dele sumir -------------------------
        migrations.RunPython(criar_desenho_das_revisoes, desfazer_backfill),

        # ---- 4. só agora a remoção ------------------------------------------
        migrations.RemoveField(model_name='revisaodocumento', name='escala_calibrada_em'),
        migrations.RemoveField(model_name='revisaodocumento', name='escala_calibrada_por'),
        migrations.RemoveField(model_name='revisaodocumento', name='escala_origem'),
        migrations.RemoveField(model_name='revisaodocumento', name='escala_referencia'),
        migrations.RemoveField(model_name='revisaodocumento', name='escala_unidade'),
        migrations.RemoveField(model_name='revisaodocumento', name='escala_valor'),

        # ---- 5. a chave da derivada, que agora inclui o desenho --------------
        migrations.RemoveConstraint(
            model_name='derivadaprojeto',
            name='prancheta_derivada_unica_por_motor',
        ),
        migrations.AddConstraint(
            model_name='derivadaprojeto',
            constraint=models.UniqueConstraint(condition=models.Q(('desenho__isnull', True)), fields=('revisao', 'tipo', 'motor'), name='prancheta_derivada_unica_por_motor'),
        ),
        migrations.AddConstraint(
            model_name='derivadaprojeto',
            constraint=models.UniqueConstraint(condition=models.Q(('desenho__isnull', False)), fields=('revisao', 'tipo', 'motor', 'desenho'), name='prancheta_derivada_unica_por_desenho'),
        ),
    ]
