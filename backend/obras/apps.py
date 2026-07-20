# obras/apps.py
from django.apps import AppConfig


class ObrasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'obras'
    verbose_name = 'Obras'

    def ready(self):
        # Fase 10.8: ao excluir obra/empreendimento, desvincular (soft) os projetos
        # de drone órfãos. `conectar_sinais` liga ambos os `post_delete` de uma vez
        # (idempotente via dispatch_uid); `empreendimentos` não tem AppConfig
        # próprio, então centralizamos aqui — `obras` sempre carrega.
        from nucleo.drone_sync import conectar_sinais
        conectar_sinais()
