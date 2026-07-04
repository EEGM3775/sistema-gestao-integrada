"""
Remove os modelos legados Perfil e Permissao do ERP.

Papéis (RBAC) e permissões são autoritativos na IAM e viajam no JWT
(claims 'roles'). O ERP nunca teve lógica de negócio dependente desses
modelos — eram um espelho vazio. Ver docs/acesso-e-permissoes.md Fase 6.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nucleo", "0007_enable_rls"),
    ]

    operations = [
        # 1. Remove o FK Usuario.perfil
        migrations.RemoveField(
            model_name="usuario",
            name="perfil",
        ),
        # 2. Remove a tabela M2M Perfil↔Permissao e depois os modelos
        migrations.RemoveField(
            model_name="perfil",
            name="permissoes",
        ),
        migrations.DeleteModel(name="Perfil"),
        migrations.DeleteModel(name="Permissao"),
    ]
