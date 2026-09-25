# backend/nucleo/migrations/0027_autorizacao_pdp.py
"""Remodelagem da segurança, fases 2 e 3: a flag por módulo e o registro da sombra.

Sem RLS, de propósito — as duas tabelas são da plataforma, não do cliente (ver o
comentário acima dos modelos em `nucleo/models.py`). A divergência não guarda
conteúdo: ids, códigos do catálogo e booleanos.

O gatilho que barra UPDATE/DELETE na divergência é o reforço de banco do
append-only: o modelo já recusa, e o trigger recusa também o `queryset.update()`
e o SQL de quem entrou no banco pela porta dos fundos.
"""
from django.db import migrations, models

_IMUTAVEL = """
CREATE OR REPLACE FUNCTION nucleo_divergencia_imutavel() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'nucleo_divergenciaautorizacao é append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER nucleo_divergencia_imutavel
    BEFORE UPDATE OR DELETE ON nucleo_divergenciaautorizacao
    FOR EACH ROW EXECUTE FUNCTION nucleo_divergencia_imutavel();
"""

_SEM_IMUTAVEL = """
DROP TRIGGER IF EXISTS nucleo_divergencia_imutavel ON nucleo_divergenciaautorizacao;
DROP FUNCTION IF EXISTS nucleo_divergencia_imutavel();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0026_rls_lixo'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModoAutorizacao',
            fields=[
                ('modulo', models.CharField(max_length=40, primary_key=True, serialize=False, verbose_name='Módulo')),
                ('modo', models.CharField(choices=[('token', 'Token (como sempre foi)'), ('pdp', 'PDP (SpiceDB)')], default='token', max_length=10)),
                ('alterado_em', models.DateTimeField(auto_now=True)),
                ('alterado_por', models.CharField(blank=True, max_length=150)),
            ],
            options={
                'verbose_name': 'Modo de autorização',
                'verbose_name_plural': 'Modos de autorização',
                'ordering': ['modulo'],
            },
        ),
        migrations.CreateModel(
            name='DivergenciaAutorizacao',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('tenant_id', models.UUIDField(null=True)),
                ('usuario_id', models.CharField(max_length=64)),
                ('pergunta', models.CharField(max_length=100)),
                ('modulo', models.CharField(max_length=40)),
                ('classe', models.CharField(max_length=1)),
                ('modo', models.CharField(max_length=10)),
                ('decisao_token', models.BooleanField()),
                ('decisao_pdp', models.BooleanField(null=True)),
                ('tipo', models.CharField(choices=[('real', 'Real — defeito a investigar'), ('token_defasado', 'Token emitido antes da última troca de acesso'), ('pdp_indisponivel', 'PDP não respondeu'), ('fora_do_esquema', 'Pergunta que o PDP não conhece')], max_length=20)),
                ('idade_do_token_s', models.IntegerField(null=True)),
            ],
            options={
                'verbose_name': 'Divergência de autorização',
                'verbose_name_plural': 'Divergências de autorização',
                'ordering': ['-criado_em'],
                'indexes': [models.Index(fields=['tipo', '-criado_em'], name='authz_div_tipo_idx')],
            },
        ),
        migrations.RunSQL(_IMUTAVEL, _SEM_IMUTAVEL),
    ]
