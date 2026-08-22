from django.apps import AppConfig


class ModuloPdcaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modulopdca"
    # Absorve o planejamento de obra (cronograma físico, Gantt, linha de balanço,
    # avanço × previsto), que a documentação atribuía a um "APS" inexistente —
    # ver docs/modulos/moduloprancheta.md §1.
    verbose_name = "PDCA — Planejamento & Melhoria Contínua"
    module_code = "pdca"
