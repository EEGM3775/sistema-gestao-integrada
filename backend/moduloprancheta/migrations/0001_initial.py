# backend/moduloprancheta/migrations/0001_initial.py
"""PRA.0 — fundação da Prancheta: documento lógico, revisão e derivada.

Escrita à mão (o venv do host não tem GDAL, então `makemigrations` não roda
fora do container). Confira com `manage.py makemigrations --check --dry-run`
antes de aplicar: divergência entre models.py e migration é a armadilha que o
CLAUDE.md registra.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import moduloprancheta.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('nucleo', '0020_indiceeconomico_valorindice'),
        ('obras', '0005_remove_obra_unique_obra_empreendimento_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentoProjeto',
            fields=[
                ('documento_id', models.AutoField(primary_key=True, serialize=False)),
                ('codigo', models.CharField(max_length=60, verbose_name='Código do documento')),
                ('titulo', models.CharField(max_length=180, verbose_name='Título')),
                ('disciplina', models.CharField(choices=[('arquitetura', 'Arquitetura'), ('estrutural', 'Estrutural'), ('fundacao', 'Fundações'), ('hidrossanitario', 'Hidrossanitário'), ('eletrica', 'Elétrica'), ('incendio', 'Combate a incêndio'), ('climatizacao', 'Climatização'), ('terraplanagem', 'Terraplanagem'), ('pavimentacao', 'Pavimentação'), ('topografia', 'Topografia'), ('implantacao', 'Implantação / urbanismo'), ('legal', 'Projeto legal / aprovação'), ('outra', 'Outra')], default='outra', max_length=18, verbose_name='Disciplina')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                ('projetista', models.CharField(blank=True, max_length=180, verbose_name='Projetista/escritório')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('etapa', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='documentos_projeto', to='obras.etapaobra', verbose_name='Etapa')),
                ('obra', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documentos_projeto', to='obras.obra', verbose_name='Obra')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Documento de projeto',
                'verbose_name_plural': 'Documentos de projeto',
                'ordering': ['obra', 'disciplina', 'codigo'],
            },
        ),
        migrations.CreateModel(
            name='RevisaoDocumento',
            fields=[
                ('revisao_id', models.AutoField(primary_key=True, serialize=False)),
                ('revisao', models.CharField(max_length=10, verbose_name='Revisão')),
                ('arquivo', models.FileField(upload_to=moduloprancheta.models.caminho_revisao, verbose_name='Arquivo')),
                ('nome_original', models.CharField(max_length=255, verbose_name='Nome do arquivo enviado')),
                ('formato', models.CharField(choices=[('pdf', 'PDF'), ('imagem', 'Imagem (JPG/PNG/WebP)'), ('dxf', 'AutoCAD DXF'), ('dwg', 'AutoCAD DWG'), ('dwf', 'Autodesk DWF'), ('ifc', 'IFC (2x3/4/4.3)'), ('rvt', 'Autodesk Revit'), ('nwd', 'Navisworks'), ('dgn', 'MicroStation DGN'), ('skp', 'SketchUp'), ('kmz', 'KML/KMZ'), ('shp', 'Shapefile (ZIP)'), ('geojson', 'GeoJSON'), ('gpkg', 'GeoPackage'), ('qgis', 'Projeto QGIS'), ('geotiff', 'GeoTIFF'), ('las', 'LAS/LAZ'), ('copc', 'COPC'), ('e57', 'E57'), ('bcf', 'BCF (marcação)')], max_length=10, verbose_name='Formato')),
                ('tamanho_bytes', models.PositiveBigIntegerField(default=0, verbose_name='Tamanho (bytes)')),
                ('hash_sha256', models.CharField(blank=True, max_length=64, verbose_name='SHA-256')),
                ('situacao', models.CharField(choices=[('rascunho', 'Rascunho (recebida, não publicada)'), ('vigente', 'Vigente — é esta que se executa'), ('superada', 'Superada por revisão posterior')], default='rascunho', max_length=10, verbose_name='Situação')),
                ('data_emissao', models.DateField(blank=True, null=True, verbose_name='Data de emissão pelo projetista')),
                ('observacao', models.TextField(blank=True, verbose_name='Observação')),
                ('enviado_em', models.DateTimeField(auto_now_add=True)),
                ('publicado_em', models.DateTimeField(blank=True, null=True, verbose_name='Publicado em')),
                ('documento', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='revisoes', to='moduloprancheta.documentoprojeto', verbose_name='Documento')),
                ('enviado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisoes_projeto_enviadas', to=settings.AUTH_USER_MODEL, verbose_name='Enviado por')),
                ('publicado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisoes_projeto_publicadas', to=settings.AUTH_USER_MODEL, verbose_name='Publicado por')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Revisão de documento',
                'verbose_name_plural': 'Revisões de documento',
                'ordering': ['documento', '-revisao'],
            },
        ),
        migrations.CreateModel(
            name='DerivadaProjeto',
            fields=[
                ('derivada_id', models.AutoField(primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[('vetor_2d', 'Vetor 2D (SVG/tiles)'), ('modelo_3d', 'Modelo 3D (Fragments/glTF)'), ('miniatura', 'Miniatura')], max_length=10, verbose_name='Tipo de derivada')),
                ('motor', models.CharField(choices=[('pdf_nativo', 'Render nativo do browser'), ('ezdxf', 'ezdxf (DXF → SVG)'), ('libredwg', 'LibreDWG (dwg2dxf)'), ('ifcopenshell', 'IfcOpenShell + That Open/Fragments'), ('gdal', 'GDAL/OGR'), ('pdal', 'PDAL/Potree'), ('aps', 'Autodesk Platform Services (Model Derivative)')], max_length=14, verbose_name='Motor')),
                ('motor_versao', models.CharField(blank=True, max_length=40, verbose_name='Versão do motor')),
                ('estado', models.CharField(choices=[('pendente', 'Aguardando conversão'), ('lendo', 'Lendo o arquivo'), ('convertendo', 'Convertendo'), ('pronto', 'Pronto'), ('erro', 'Erro')], default='pendente', max_length=12, verbose_name='Estado')),
                ('arquivo', models.FileField(blank=True, null=True, upload_to='prancheta/derivadas/%Y/%m/', verbose_name='Arquivo derivado')),
                ('tamanho_bytes', models.PositiveBigIntegerField(default=0, verbose_name='Tamanho (bytes)')),
                ('erro_motivo', models.CharField(blank=True, choices=[('motor_insuficiente', 'Exige o motor de alta fidelidade'), ('arquivo_corrompido', 'Arquivo ilegível ou corrompido'), ('versao_nao_suportada', 'Versão do formato não suportada'), ('tempo_excedido', 'Tempo de conversão excedido'), ('falha_motor', 'Falha interna do motor')], max_length=22, verbose_name='Motivo do erro')),
                ('erro_detalhe', models.TextField(blank=True, verbose_name='Detalhe do erro')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('concluido_em', models.DateTimeField(blank=True, null=True, verbose_name='Concluído em')),
                ('revisao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='derivadas', to='moduloprancheta.revisaodocumento', verbose_name='Revisão')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Derivada de projeto',
                'verbose_name_plural': 'Derivadas de projeto',
                'ordering': ['revisao', 'tipo'],
            },
        ),
        migrations.AddIndex(
            model_name='documentoprojeto',
            index=models.Index(fields=['tenant', 'obra', 'disciplina'], name='prancheta_doc_obra_disc_idx'),
        ),
        migrations.AddConstraint(
            model_name='documentoprojeto',
            constraint=models.UniqueConstraint(fields=('tenant', 'obra', 'codigo'), name='prancheta_documento_codigo_por_obra'),
        ),
        migrations.AddIndex(
            model_name='revisaodocumento',
            index=models.Index(fields=['tenant', 'situacao'], name='prancheta_rev_situacao_idx'),
        ),
        migrations.AddConstraint(
            model_name='revisaodocumento',
            constraint=models.UniqueConstraint(fields=('tenant', 'documento', 'revisao'), name='prancheta_revisao_unica_por_documento'),
        ),
        migrations.AddConstraint(
            model_name='revisaodocumento',
            constraint=models.UniqueConstraint(condition=models.Q(('situacao', 'vigente')), fields=('tenant', 'documento'), name='prancheta_uma_revisao_vigente'),
        ),
        migrations.AddIndex(
            model_name='derivadaprojeto',
            index=models.Index(fields=['tenant', 'estado'], name='prancheta_deriv_estado_idx'),
        ),
        migrations.AddConstraint(
            model_name='derivadaprojeto',
            constraint=models.UniqueConstraint(fields=('revisao', 'tipo', 'motor'), name='prancheta_derivada_unica_por_motor'),
        ),
    ]
