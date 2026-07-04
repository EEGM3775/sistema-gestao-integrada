from django.apps import AppConfig


class ModulocalendarConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulocalendar'

    def ready(self):
        # Importa e conecta os receivers de sinal
        import modulocalendar.receivers
