# backend/modulosil/signals.py
"""Integração viva SCM → SIL: cada **linha de recebimento** criada no SCM dá
**entrada** no estoque. O gatilho é o `ItemRecebimento` (no SCM o recebimento
nasce antes das linhas). Via signal para o SCM **não** depender do SIL."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("sil.signals")


@receiver(post_save, sender="moduloscm.ItemRecebimento", dispatch_uid="sil_entrada_de_item_recebimento")
def _entrada_de_item_recebimento(sender, instance, created, **kwargs):
    if not created:
        return
    from .services import registrar_entrada_de_item_recebimento

    try:
        registrar_entrada_de_item_recebimento(instance)
    except Exception:  # noqa: BLE001 - a entrada de estoque não derruba o recebimento
        logger.exception(
            "Falha ao dar entrada de estoque do item de recebimento SCM #%s",
            getattr(instance, "item_recebimento_id", None),
        )
