# Centro de notificações in-app (Calendário, Fatia C).
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0017_auditlog_imutavel'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notificacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('mensagem', models.TextField(blank=True, default='', verbose_name='Mensagem')),
                ('tipo', models.CharField(choices=[('lembrete', 'Lembrete de evento'), ('sistema', 'Sistema')], default='sistema', max_length=20)),
                ('url', models.CharField(blank=True, default='', max_length=300, verbose_name='Link')),
                ('lida_em', models.DateTimeField(blank=True, null=True, verbose_name='Lida em')),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='nucleo.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notificacoes', to='nucleo.usuario')),
            ],
            options={
                'verbose_name': 'Notificação',
                'verbose_name_plural': 'Notificações',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='notificacao',
            index=models.Index(fields=['tenant', 'user', 'lida_em'], name='notif_user_lida_idx'),
        ),
    ]
