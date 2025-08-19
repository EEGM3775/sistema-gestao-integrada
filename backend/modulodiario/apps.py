# backend/modulodiario/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class ModuloDiarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulodiario'
    verbose_name = _("Módulo Diário de Obra")
