# backend/funcoesimpexp/apps.py
from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class FuncoesImpExpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "funcoesimpexp"
    verbose_name = "Importação e exportação — função de plataforma"

    def ready(self):
        """Carrega o `impexp.py` de cada app instalado.

        É o que faz um módulo ganhar import/export **sem tocar no motor**: ele
        escreve `<modulo>/impexp.py` e a declaração se registra sozinha no boot.
        Mesmo mecanismo do `admin.autodiscover()` do próprio Django.

        Importar no `ready()`, e não sob demanda no primeiro request, é o que
        mantém a promessa de `Recurso.validar`: declaração torta derruba o boot
        com traceback, em vez de esperar o clique de um usuário para falhar.
        """
        autodiscover_modules("impexp")
