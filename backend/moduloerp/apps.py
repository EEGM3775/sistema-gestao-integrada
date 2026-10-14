# backend/moduloerp/apps.py
from django.apps import AppConfig

class ModuloerpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'moduloerp'
    verbose_name = 'ERP - Faturamento e Financeiro'

    def ready(self):
        # Intercompany (docs/modulos/entidades.md §3): o par acompanha a origem a
        # cada gravação dela — vale para o título que o PDCA, o SCM ou a carteira
        # criam, não só o da tela do ERP.
        from django.db.models.signals import post_save

        from .models import ContaPagar, ContaReceber

        def _sincronizar_par(sender, instance, raw=False, **kwargs):
            if raw or instance.natureza or getattr(instance, '_sem_intercompany', False):
                return
            from .intercompany import sincronizar
            sincronizar(instance)

        post_save.connect(_sincronizar_par, sender=ContaPagar, dispatch_uid='erp_intercompany_pagar', weak=False)
        post_save.connect(_sincronizar_par, sender=ContaReceber, dispatch_uid='erp_intercompany_receber', weak=False)
