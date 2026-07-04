# backend/moduloapi/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from nucleo.tenancy import TenantScopedModel

class BaseModel(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_("Data de Criação"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Última Atualização"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

class GoogleAccount(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='google_account')
    access_token = models.CharField(max_length=2048)
    refresh_token = models.CharField(max_length=2048, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Conta Google de {self.user.username}"

    class Meta(BaseModel.Meta):
        verbose_name = _("Conta Google")
        verbose_name_plural = _("Contas Google")
