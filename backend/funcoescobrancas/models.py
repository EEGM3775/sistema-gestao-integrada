# backend/funcoescobrancas/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _


class EventoWebhookAsaas(models.Model):
    """
    Registro de cada evento recebido do webhook do Asaas — garante a
    idempotência exigida pela integração (o Asaas reenvia eventos não
    confirmados). `evento_id` é o `id` do evento no payload do Asaas.

    Não é `TenantScopedModel`: o tenant só é conhecido depois de localizar o
    `Boleto` associado ao `payment.id` recebido (a credencial Asaas é global
    nesta fase — ver moduloerp.md §15).
    """
    evento_id = models.CharField(_("ID do Evento no Asaas"), max_length=100, unique=True, db_index=True)
    tipo = models.CharField(_("Tipo do Evento"), max_length=50, db_index=True)
    payload = models.JSONField(_("Payload Recebido"))
    boleto = models.ForeignKey(
        'moduloerp.Boleto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos_webhook_asaas',
        verbose_name=_("Boleto Associado"),
    )
    recebido_em = models.DateTimeField(_("Recebido em"), auto_now_add=True)
    processado_em = models.DateTimeField(_("Processado em"), null=True, blank=True)
    resultado = models.CharField(_("Resultado do Processamento"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Evento de Webhook Asaas")
        verbose_name_plural = _("Eventos de Webhook Asaas")
        ordering = ['-recebido_em']

    def __str__(self):
        return f"{self.tipo} ({self.evento_id})"
