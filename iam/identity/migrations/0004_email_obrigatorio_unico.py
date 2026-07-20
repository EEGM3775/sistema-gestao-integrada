"""E-mail obrigatório e único no `Usuario` (D11).

O e-mail deixou de ser dado de contato e virou infraestrutura de segurança: é por
ele que se recupera a senha. Conta sem e-mail é conta sem caminho de recuperação
— o travamento que o D11 existe para eliminar — e e-mail duplicado torna o
"esqueci minha senha" ambíguo.

Também remove `origem`/`solicitante` do token: com o e-mail obrigatório, o caminho
"assistido por admin" (token na caixa do admin, para quem não tinha e-mail
próprio) perdeu razão de existir e foi retirado. Passou a haver um caminho só.
"""
from django.db import migrations, models


def checar_emails(apps, schema_editor):
    """Falha com mensagem legível ANTES do UNIQUE, se os dados não permitirem.

    Sem isto, um ambiente com e-mail vazio ou repetido receberia um
    `IntegrityError` cru no meio do deploy, sem dizer qual conta é a culpada.
    """
    Usuario = apps.get_model("identity", "Usuario")

    sem_email = list(
        Usuario.objects.filter(email="").values_list("username", flat=True)
    )
    if sem_email:
        raise RuntimeError(
            "Não é possível tornar o e-mail obrigatório: as contas a seguir estão "
            f"sem e-mail — {', '.join(sem_email)}. Cadastre um endereço para cada "
            "uma (ou desative-as) e rode a migração de novo."
        )

    vistos, duplicados = {}, set()
    for username, email in Usuario.objects.values_list("username", "email"):
        chave = (email or "").lower()
        if chave in vistos:
            duplicados.add(f"{email} ({vistos[chave]} e {username})")
        vistos[chave] = username
    if duplicados:
        raise RuntimeError(
            "Não é possível tornar o e-mail único: há endereços repetidos — "
            f"{'; '.join(sorted(duplicados))}. Cada conta precisa do próprio "
            "endereço para que a recuperação de senha saiba a quem responder."
        )


def nada(apps, schema_editor):
    """Reversão não precisa de checagem: afrouxar a regra nunca conflita."""


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0003_eventoseguranca_imutavel'),
    ]

    operations = [
        migrations.RunPython(checar_emails, nada),
        migrations.RemoveField(
            model_name='tokenrecuperacaosenha',
            name='origem',
        ),
        migrations.RemoveField(
            model_name='tokenrecuperacaosenha',
            name='solicitante',
        ),
        migrations.AlterField(
            model_name='eventoseguranca',
            name='tipo',
            field=models.CharField(choices=[('reset_solicitado', 'Recuperação de senha solicitada'), ('reset_concluido', 'Senha redefinida por token'), ('senha_alterada', 'Senha alterada'), ('email_troca_solicitada', 'Troca de e-mail solicitada'), ('email_troca_confirmada', 'Troca de e-mail confirmada'), ('email_troca_cancelada', 'Troca de e-mail cancelada'), ('privilegio_alterado', 'Papéis/privilégios alterados'), ('usuario_desativado', 'Usuário desativado')], max_length=40),
        ),
        migrations.AlterField(
            model_name='usuario',
            name='email',
            field=models.EmailField(max_length=254, unique=True, verbose_name='E-mail'),
        ),
    ]
