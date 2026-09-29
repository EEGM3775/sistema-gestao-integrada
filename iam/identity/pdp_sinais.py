"""Toda troca que muda a resposta de "pode?" chega ao PDP — por qualquer caminho.

Pelo mesmo motivo do D12 (`signals.py`): amarrar ao **modelo**, não ao endpoint.
A tela de papéis, o Django admin, o `seed_demo`, o `sync_authz` e um
`manage.py shell` passam todos pelo ORM; ligar aqui cobre todos. O que fica de
fora por construção é o SQL cru e o `queryset.update()` — e é para isso que a
volta periódica do `sincronizar_pdp --continuo` existe.

Cada sinal só **agenda** a reconciliação do tenant para o fim da transação
(`pdp.agendar`), uma vez por tenant: a escrita no SpiceDB nunca acontece por
uma troca que depois é desfeita por rollback.
"""
from __future__ import annotations

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from . import pdp
from .models import AcessoUsuarioModulo, AssinaturaTenant, Modulo, Perfil, Tenant, Usuario

_ANTERIOR = "_pdp_estado_anterior"


@receiver(pre_save, sender=Usuario)
def _usuario_antes(sender, instance, **kwargs):
    anterior = None
    if instance.pk is not None:
        anterior = (
            sender.objects.filter(pk=instance.pk).values("tenant_id", "is_superuser").first()
        )
    instance.__dict__[_ANTERIOR] = anterior


@receiver(post_save, sender=Usuario)
def _usuario_salvo(sender, instance, **kwargs):
    anterior = instance.__dict__.pop(_ANTERIOR, None) or {}
    pdp.agendar(instance.tenant_id)
    if anterior.get("tenant_id") and anterior["tenant_id"] != instance.tenant_id:
        pdp.agendar(anterior["tenant_id"])  # saiu desta empresa
    if instance.is_superuser or anterior.get("is_superuser"):
        pdp.agendar_plataforma()


@receiver(post_delete, sender=Usuario)
def _usuario_excluido(sender, instance, **kwargs):
    pdp.agendar(instance.tenant_id)
    if instance.is_superuser:
        pdp.agendar_plataforma()


@receiver(m2m_changed, sender=Usuario.perfis.through)
def _perfis_da_pessoa(sender, instance, action, pk_set, **kwargs):
    if not action.startswith("post_"):
        return
    if isinstance(instance, Usuario):
        pdp.agendar(instance.tenant_id)
        for tid in Perfil.objects.filter(pk__in=pk_set or ()).values_list("tenant_id", flat=True):
            pdp.agendar(tid)
    else:  # o lado do papel: `perfil.usuarios.add(...)`
        pdp.agendar(instance.tenant_id)


@receiver(m2m_changed, sender=Perfil.permissoes.through)
def _permissoes_do_papel(sender, instance, action, pk_set, **kwargs):
    if isinstance(instance, Perfil):
        if action.startswith("post_"):
            pdp.agendar(instance.tenant_id)
        return
    # O lado da permissão (`permissao.perfis.add(...)`). No `clear` o `pk_set`
    # vem vazio, então os papéis afetados são lidos ANTES de limpar.
    if action == "pre_clear":
        instance.__dict__[_ANTERIOR] = list(
            instance.perfis.values_list("tenant_id", flat=True)
        )
        return
    if not action.startswith("post_"):
        return
    tenants = instance.__dict__.pop(_ANTERIOR, None) if action == "post_clear" else list(
        Perfil.objects.filter(pk__in=pk_set or ()).values_list("tenant_id", flat=True)
    )
    for tid in set(tenants or ()):
        pdp.agendar(tid)


@receiver(post_save, sender=Perfil)
@receiver(post_delete, sender=Perfil)
def _papel(sender, instance, **kwargs):
    pdp.agendar(instance.tenant_id)


@receiver(post_save, sender=AssinaturaTenant)
@receiver(post_delete, sender=AssinaturaTenant)
def _assinatura(sender, instance, **kwargs):
    pdp.agendar(instance.tenant_id)


@receiver(post_save, sender=AcessoUsuarioModulo)
@receiver(post_delete, sender=AcessoUsuarioModulo)
def _acesso_a_modulo(sender, instance, **kwargs):
    tenant_id = (
        Usuario.objects.filter(pk=instance.usuario_id).values_list("tenant_id", flat=True).first()
    )
    pdp.agendar(tenant_id)


@receiver(post_save, sender=Modulo)
@receiver(post_delete, sender=Modulo)
def _modulo_do_catalogo(sender, instance, **kwargs):
    # Um módulo novo (ou removido) muda a régua do supervisor em toda empresa.
    for tid in Tenant.objects.values_list("id", flat=True):
        pdp.agendar(tid)


@receiver(post_save, sender=Tenant)
def _empresa(sender, instance, created, **kwargs):
    # Toda gravação, e não só a criação: o plano e o slug estão na ficha da
    # empresa (fase 4, `identity/fichas.py`), que sai no mesmo ciclo.
    pdp.agendar(instance.id)


@receiver(post_delete, sender=Tenant)
def _empresa_excluida(sender, instance, **kwargs):
    if not pdp.ativo():
        return
    from django.db import transaction

    tid = str(instance.id)

    def executar():
        try:
            pdp.remover_tenant(tid)
        except Exception:  # noqa: BLE001 - a volta periódica apaga o órfão
            pdp.logger.warning("pdp.remocao_adiada tenant=%s", tid, exc_info=True)

    transaction.on_commit(executar)
