from django.apps import AppConfig


class ModuloOrcamentoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "moduloorcamento"
    verbose_name = "Orçamento — planilha orçamentária e controle de custo"
    module_code = "orcamento"
