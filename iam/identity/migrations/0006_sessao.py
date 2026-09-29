import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0005_segundo_fator"),
    ]

    operations = [
        migrations.CreateModel(
            name="Sessao",
            fields=[
                ("sid", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("revogada_em", models.DateTimeField(blank=True, null=True)),
                ("motivo", models.CharField(blank=True, max_length=40)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name="sessoes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Sessão",
                "verbose_name_plural": "Sessões",
                "indexes": [models.Index(fields=["usuario", "revogada_em"], name="identity_se_usuario_86083c_idx")],
            },
        ),
    ]
