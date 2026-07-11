# Trilha de auditoria imutável (Fase 9.E).
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0014_incidentelgpd_rls'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('usuario_nome', models.CharField(blank=True, default='', max_length=150, verbose_name='Usuário (rótulo)')),
                ('acao', models.CharField(choices=[('criar', 'Criação'), ('atualizar', 'Atualização'), ('excluir', 'Exclusão'), ('baixa', 'Baixa financeira'), ('emitir_nf', 'Emissão de NF'), ('gerar_cobranca', 'Geração de cobrança'), ('exportar_lgpd', 'Exportação LGPD (portabilidade)'), ('anonimizar_lgpd', 'Anonimização LGPD (esquecimento)'), ('visualizar_pii', 'Visualização de PII')], max_length=32, verbose_name='Ação')),
                ('modelo', models.CharField(max_length=100, verbose_name='Modelo')),
                ('objeto_id', models.CharField(blank=True, default='', max_length=64, verbose_name='ID do objeto')),
                ('detalhes', models.JSONField(blank=True, null=True, verbose_name='Detalhes (não-PII)')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Timestamp')),
                ('usuario', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='auditorias', to=settings.AUTH_USER_MODEL, verbose_name='Usuário')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
            ],
            options={
                'verbose_name': 'Registro de Auditoria',
                'verbose_name_plural': 'Trilha de Auditoria',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['tenant', 'modelo', 'objeto_id'], name='audit_tenant_obj_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['tenant', 'timestamp'], name='audit_tenant_ts_idx'),
        ),
    ]
