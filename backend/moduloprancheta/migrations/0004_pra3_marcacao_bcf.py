"""PRA.3 — marcar e medir: as quatro tabelas novas + a escala da revisão.

**A RLS entra nesta migration, e não numa seguinte**, ao contrário do que a
`0002` fez com as três primeiras tabelas. Lá a política veio depois porque a
`0001` já estava aplicada; aqui as tabelas nascem agora, e criá-las numa
migration e protegê-las na próxima abriria uma janela — curta, mas real — em que
a marcação de um cliente é legível por qualquer sessão. Marcação carrega o
apontamento técnico sobre o projeto (onde está errado, quem errou, o que custa
corrigir): vaza menos bytes que o desenho e mais julgamento.

O `Medicao` entra junto pela mesma razão do `DerivadaProjeto` na `0002`: a medida
tirada sobre a planta é informação do projeto, não metadado.
"""

import django.db.models.deletion
import django.utils.timezone
import moduloprancheta.models
import uuid
from django.conf import settings
from django.db import migrations, models

# Helper repetido em vez de importado porque nome de módulo de migration começa
# com dígito e não é importável; é o padrão do repo (ver `0002_rls_fail_closed`).
_TABLES = (
    "moduloprancheta_marcacao",
    "moduloprancheta_pontodevista",
    "moduloprancheta_comentariomarcacao",
    "moduloprancheta_medicao",
)
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


class Migration(migrations.Migration):

    dependencies = [
        ('moduloprancheta', '0003_pra1_pipeline_conversao'),
        ('nucleo', '0020_indiceeconomico_valorindice'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='revisaodocumento',
            name='escala_calibrada_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Calibrada em'),
        ),
        migrations.AddField(
            model_name='revisaodocumento',
            name='escala_calibrada_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisoes_projeto_calibradas', to=settings.AUTH_USER_MODEL, verbose_name='Calibrada por'),
        ),
        migrations.AddField(
            model_name='revisaodocumento',
            name='escala_referencia',
            field=models.JSONField(blank=True, default=dict, verbose_name='Referência da calibração'),
        ),
        migrations.AddField(
            model_name='revisaodocumento',
            name='escala_unidade',
            field=models.CharField(blank=True, default='m', max_length=4, verbose_name='Unidade'),
        ),
        migrations.AddField(
            model_name='revisaodocumento',
            name='escala_valor',
            field=models.FloatField(blank=True, null=True, verbose_name='Unidades reais na largura do desenho'),
        ),
        migrations.CreateModel(
            name='Marcacao',
            fields=[
                ('marcacao_id', models.AutoField(primary_key=True, serialize=False)),
                ('guid', models.UUIDField(default=uuid.uuid4, editable=False, verbose_name='GUID (BCF)')),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                ('tipo', models.CharField(choices=[('Issue', 'Problema'), ('Request', 'Solicitação'), ('Comment', 'Observação'), ('Clash', 'Interferência'), ('Inquiry', 'Dúvida')], default='Issue', max_length=12, verbose_name='Tipo')),
                ('situacao', models.CharField(choices=[('Open', 'Aberta'), ('In Progress', 'Em andamento'), ('Resolved', 'Resolvida'), ('Closed', 'Fechada')], default='Open', max_length=12, verbose_name='Situação')),
                ('prioridade', models.CharField(choices=[('Low', 'Baixa'), ('Normal', 'Normal'), ('High', 'Alta'), ('Critical', 'Crítica')], default='Normal', max_length=8, verbose_name='Prioridade')),
                ('rotulos', models.JSONField(blank=True, default=list, verbose_name='Rótulos (BCF Labels)')),
                ('prazo', models.DateField(blank=True, null=True, verbose_name='Prazo')),
                ('responsavel_email', models.EmailField(blank=True, max_length=254, verbose_name='Responsável (e-mail)')),
                ('autor_nome', models.CharField(blank=True, max_length=180, verbose_name='Autor (externo)')),
                ('criado_em', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Criada em')),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('resolvido_em', models.DateTimeField(blank=True, null=True, verbose_name='Resolvida em')),
                ('origem', models.CharField(choices=[('sistema', 'Criada aqui'), ('bcf', 'Importada de BCF')], default='sistema', max_length=8, verbose_name='Origem')),
                ('ancora', models.JSONField(blank=True, default=dict, verbose_name='Âncora na folha')),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marcacoes_prancheta_criadas', to=settings.AUTH_USER_MODEL, verbose_name='Criada por')),
                ('resolvido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marcacoes_prancheta_resolvidas', to=settings.AUTH_USER_MODEL, verbose_name='Resolvida por')),
                ('responsavel', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marcacoes_prancheta', to=settings.AUTH_USER_MODEL, verbose_name='Responsável (com login)')),
                ('revisao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marcacoes', to='moduloprancheta.revisaodocumento', verbose_name='Revisão')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Marcação',
                'verbose_name_plural': 'Marcações',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.CreateModel(
            name='Medicao',
            fields=[
                ('medicao_id', models.AutoField(primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[('distancia', 'Distância'), ('area', 'Área')], default='distancia', max_length=9, verbose_name='Tipo')),
                ('pontos', models.JSONField(default=list, verbose_name='Vértices (normalizados)')),
                ('valor', models.FloatField(verbose_name='Valor')),
                ('unidade', models.CharField(blank=True, max_length=4, verbose_name='Unidade')),
                ('escala_aplicada', models.FloatField(blank=True, null=True, verbose_name='Escala usada (unidades na largura)')),
                ('rotulo', models.CharField(blank=True, max_length=120, verbose_name='Rótulo')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medicoes_prancheta', to=settings.AUTH_USER_MODEL, verbose_name='Medida por')),
                ('marcacao', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medicoes', to='moduloprancheta.marcacao', verbose_name='Marcação')),
                ('revisao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medicoes', to='moduloprancheta.revisaodocumento', verbose_name='Revisão')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Medição',
                'verbose_name_plural': 'Medições',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.CreateModel(
            name='PontoDeVista',
            fields=[
                ('ponto_de_vista_id', models.AutoField(primary_key=True, serialize=False)),
                ('guid', models.UUIDField(default=uuid.uuid4, editable=False, verbose_name='GUID (BCF)')),
                ('camera', models.JSONField(blank=True, default=dict, verbose_name='Câmera (BCF)')),
                ('snapshot', models.ImageField(blank=True, null=True, upload_to=moduloprancheta.models.caminho_snapshot, verbose_name='Snapshot')),
                ('criado_em', models.DateTimeField(default=django.utils.timezone.now)),
                ('marcacao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pontos_de_vista', to='moduloprancheta.marcacao', verbose_name='Marcação')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Ponto de vista',
                'verbose_name_plural': 'Pontos de vista',
                'ordering': ['ponto_de_vista_id'],
            },
        ),
        migrations.CreateModel(
            name='ComentarioMarcacao',
            fields=[
                ('comentario_id', models.AutoField(primary_key=True, serialize=False)),
                ('guid', models.UUIDField(default=uuid.uuid4, editable=False, verbose_name='GUID (BCF)')),
                ('texto', models.TextField(verbose_name='Comentário')),
                ('autor_nome', models.CharField(blank=True, max_length=180, verbose_name='Autor (externo)')),
                ('criado_em', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Criado em')),
                ('autor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='comentarios_marcacao', to=settings.AUTH_USER_MODEL, verbose_name='Autor (com login)')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
                ('marcacao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comentarios', to='moduloprancheta.marcacao', verbose_name='Marcação')),
                ('ponto_de_vista', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='comentarios', to='moduloprancheta.pontodevista', verbose_name='Ponto de vista')),
            ],
            options={
                'verbose_name': 'Comentário de marcação',
                'verbose_name_plural': 'Comentários de marcação',
                'ordering': ['criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='marcacao',
            index=models.Index(fields=['tenant', 'situacao'], name='prancheta_marc_situacao_idx'),
        ),
        migrations.AddIndex(
            model_name='marcacao',
            index=models.Index(fields=['tenant', 'responsavel'], name='prancheta_marc_resp_idx'),
        ),
        migrations.AddConstraint(
            model_name='marcacao',
            constraint=models.UniqueConstraint(fields=('tenant', 'guid'), name='prancheta_marcacao_guid_unico'),
        ),
        migrations.AddIndex(
            model_name='medicao',
            index=models.Index(fields=['tenant', 'revisao'], name='prancheta_medicao_revisao_idx'),
        ),
        migrations.AddConstraint(
            model_name='pontodevista',
            constraint=models.UniqueConstraint(fields=('tenant', 'guid'), name='prancheta_ponto_vista_guid_unico'),
        ),
        migrations.AddConstraint(
            model_name='comentariomarcacao',
            constraint=models.UniqueConstraint(fields=('tenant', 'guid'), name='prancheta_comentario_guid_unico'),
        ),
        migrations.RunPython(enable_rls, disable_rls),
    ]
