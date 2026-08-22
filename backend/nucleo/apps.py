# nucleo/apps.py
from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'nucleo'
    verbose_name = 'Núcleo'

    def ready(self):
        import nucleo.signals

        # `__unaccent__` disponível em todo campo de texto, antes de qualquer
        # view resolver um `search_fields`. Aqui e não no import do módulo
        # porque `register_lookup` mexe em classe de campo do Django, e o lugar
        # contratado para isso é o `ready()`.
        from nucleo.busca import registrar_transformacoes

        registrar_transformacoes()
