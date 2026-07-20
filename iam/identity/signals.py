"""D12 — revogação de sessão amarrada ao MODELO, não ao endpoint.

Antes, cortar o acesso de alguém só funcionava quando a ação passava pelas views
da IAM. Qualquer outro caminho — Django admin, `manage.py shell`, script de
manutenção, comando de migração — mudava o banco sem carimbar nada, e a sessão
seguia viva. Três eventos exigem revogação, e os três são tratados aqui:

- **desativação** (`is_active` True→False): o access residual seguia válido até
  expirar (só o `/auth/refresh/` barraria, por conferir `is_active`);
- **exclusão**: pior — o backend faz JIT `get_or_create` do espelho local, então
  um token ainda vivo **recriava** o usuário que acabara de ser excluído;
- **troca de senha**: o access residual valia até expirar e, pior, o refresh
  antigo continuava renovando **indefinidamente** — o `/auth/refresh/` confere
  `is_active`, não a senha. Trocar a senha de uma conta comprometida pelo admin
  do Django parecia cortar o acesso sem cortar.

Ligar em `post_save`/`post_delete` cobre todo caminho que passe pelo ORM. O que
continua de fora, por construção: `UPDATE`/`DELETE` em SQL cru e `queryset
.update()`, que não disparam signals — daí o comentário no modelo.

A revogação é idempotente (carimbo de época + blacklist), então rodar aqui e no
serializer não faria mal; ainda assim o serializer deixou de revogar, para
existir **um** lugar responsável. Ele segue dono da auditoria (que precisa saber
QUEM desativou — informação que o signal não tem).
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Usuario

logger = logging.getLogger(__name__)

# Atributo efêmero que transporta o estado ANTERIOR do pre_save para o post_save
# (no post_save a instância já traz os valores novos).
_ESTADO_ANTERIOR = "_d12_estado_anterior"


@receiver(pre_save, sender=Usuario)
def _capturar_estado_anterior(sender, instance, **kwargs):
    if instance.pk is None:
        instance.__dict__[_ESTADO_ANTERIOR] = None  # criação: nada a revogar
        return
    instance.__dict__[_ESTADO_ANTERIOR] = (
        sender.objects.filter(pk=instance.pk).values("is_active", "password").first()
    )


@receiver(post_save, sender=Usuario)
def _revogar_em_mudanca_sensivel(sender, instance, created, **kwargs):
    if created:
        return
    anterior = instance.__dict__.pop(_ESTADO_ANTERIOR, None)
    if not anterior:
        return

    if anterior["is_active"] and not instance.is_active:
        _revogar(instance.pk, motivo="desativacao")
        return

    # Troca de senha por QUALQUER caminho (Django admin, shell, script). Os três
    # caminhos de aplicação — troca pela API, reset por token e o `redefinir-senha`
    # do admin — já carimbavam a época explicitamente; fora deles, trocar a senha
    # não encerrava nada: o access residual seguia valendo até expirar E o refresh
    # antigo continuava renovando indefinidamente (o /auth/refresh/ confere
    # `is_active`, não a senha). Ou seja, trocar a senha de uma conta suspeita pelo
    # admin do Django dava a sensação de ter cortado o acesso sem ter cortado.
    #
    # Comparar o HASH, não a senha: é o que está no banco, e o hash muda a cada
    # `set_password` mesmo para a mesma senha (salt novo) — o que só causa uma
    # revogação a mais, nunca a menos.
    if anterior["password"] != instance.password:
        _revogar(instance.pk, motivo="troca_de_senha")


@receiver(post_delete, sender=Usuario)
def _revogar_ao_excluir(sender, instance, **kwargs):
    """Exclusão é o caso mais grave: sem carimbo, o access residual não só
    continuava valendo como RECRIAVA o espelho no backend (JIT).

    Blacklistar refresh aqui é inócuo — as linhas de `OutstandingToken` caem em
    cascata com o usuário —, então o que conta é o carimbo de época: enquanto ele
    existir, nenhum access anterior passa. Como o TTL do carimbo cobre a vida de
    um access, depois disso não há token vivo para ressuscitar nada.
    """
    _revogar(instance.pk, motivo="exclusao", blacklist=False)


def _revogar(user_id, *, motivo: str, blacklist: bool = True) -> None:
    from .revocation import bump_session_epoch

    if blacklist:
        from .tokens import revoke_all_sessions

        try:
            # `revoke_all_sessions` espera um objeto com `.id`; um stub evita
            # recarregar o usuário só para isso.
            revoke_all_sessions(type("_U", (), {"id": user_id})())
        except Exception:  # noqa: BLE001 — blacklist é o reforço, não a trava principal
            logger.exception("D12: falha ao blacklistar refresh de user=%s", user_id)

    bump_session_epoch(user_id)
    logger.info("D12: sessões revogadas para user=%s (motivo=%s)", user_id, motivo)
