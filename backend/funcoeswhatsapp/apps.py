# backend/funcoeswhatsapp/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FuncoesWhatsappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'funcoeswhatsapp'
    verbose_name = _("Canal WhatsApp")
