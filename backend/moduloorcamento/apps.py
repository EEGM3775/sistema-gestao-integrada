from django.apps import AppConfig


class ModuloOrcamentoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "moduloorcamento"
    verbose_name = "Orçamento — planilha orçamentária e controle de custo"
    module_code = "orcamento"

    def ready(self):
        # Receptores de `antes_de_purgar` (lixeira, D116). O import tem de
        # acontecer no `ready()` — no topo do arquivo os modelos ainda não
        # existem e o Django recusa.
        from . import signals  # noqa: F401
