from django.apps import AppConfig


class ModuloSilConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modulosil"
    verbose_name = "SIL — Estoque & Logística interna"
    module_code = "sil"

    def ready(self):
        # Integração viva SCM → SIL (Recebimento dá entrada no estoque).
        from . import signals  # noqa: F401
