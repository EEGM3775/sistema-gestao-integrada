from django.apps import AppConfig


class ModuloPranchetaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "moduloprancheta"
    verbose_name = "Prancheta — Projetos e Modelos"
    # Código do módulo no catálogo da IAM (entitlement camada 1)
    module_code = "prancheta"
