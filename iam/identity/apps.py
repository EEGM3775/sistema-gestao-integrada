from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "identity"
    verbose_name = "Identidade e Acesso"

    def ready(self):
        # D12: registra os signals que revogam a sessão em QUALQUER caminho de
        # desativação/exclusão (admin, shell, script), não só pelo serializer.
        from . import signals  # noqa: F401
