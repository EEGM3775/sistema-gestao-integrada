# backend/funcoescobrancas/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FuncoesCobrancasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'funcoescobrancas'
    verbose_name = _("Integração de Cobranças (Asaas)")
