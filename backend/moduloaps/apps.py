from django.apps import AppConfig


class ModuloApsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "moduloaps"
    verbose_name = "APS — Acompanhamento de Serviços"
    # Código do módulo no catálogo da IAM (entitlement camada 1)
    module_code = "aps"
