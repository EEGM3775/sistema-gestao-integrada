# Remodelagem da segurança, fase 6: o suporte da plataforma só entra com consentimento (§10.7).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0007_sessao_bff'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventoseguranca',
            name='tipo',
            field=models.CharField(choices=[('reset_solicitado', 'Recuperação de senha solicitada'), ('reset_concluido', 'Senha redefinida por token'), ('senha_alterada', 'Senha alterada'), ('email_troca_solicitada', 'Troca de e-mail solicitada'), ('email_troca_confirmada', 'Troca de e-mail confirmada'), ('email_troca_cancelada', 'Troca de e-mail cancelada'), ('privilegio_alterado', 'Papéis/privilégios alterados'), ('usuario_desativado', 'Usuário desativado'), ('segundo_fator_ativado', 'Segundo fator ativado'), ('segundo_fator_desativado', 'Segundo fator desativado'), ('segundo_fator_redefinido', 'Segundo fator redefinido pelo admin'), ('segundo_fator_codigos', 'Códigos de recuperação trocados'), ('segundo_fator_recuperacao', 'Entrada com código de recuperação'), ('segundo_fator_bloqueado', 'Segundo fator bloqueado por tentativas'), ('suporte_consentido', 'Acesso do suporte da plataforma liberado'), ('suporte_encerrado', 'Acesso do suporte da plataforma encerrado')], max_length=40),
        ),
        migrations.CreateModel(
            name='ConsentimentoSuporte',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('concedido_por_username', models.CharField(blank=True, max_length=150)),
                ('motivo', models.CharField(blank=True, max_length=200)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('ate', models.DateTimeField()),
                ('encerrado_em', models.DateTimeField(blank=True, null=True)),
                ('encerrado_por_username', models.CharField(blank=True, max_length=150)),
                ('concedido_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consentimentos_concedidos', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consentimentos_suporte', to='identity.tenant')),
            ],
            options={
                'verbose_name': 'Consentimento de suporte',
                'verbose_name_plural': 'Consentimentos de suporte',
                'ordering': ['-criado_em'],
                'indexes': [models.Index(fields=['tenant', 'encerrado_em', 'ate'], name='identity_co_tenant__192be9_idx')],
            },
        ),
    ]
