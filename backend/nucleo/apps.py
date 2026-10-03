# nucleo/apps.py
import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def analisar_depois_de_migrar(sender, plan=None, using="default", **kwargs):
    """`ANALYZE` depois de toda migração que aplicou alguma coisa.

    **O defeito que isto previne (item 51 do dono, 30/09/2026).** A migração que
    criou a coluna `excluido_em` (lixeira) deixou o Postgres sem estatística
    dela. O planejador supôs que `excluido_em IS NULL` filtrava 99,5% das contas
    — filtrava nenhuma —, escolheu um laço aninhado, e cada página de Contas a
    receber passou a levar 1,9 s; com a estatística, 110 ms. O autovacuum só
    reanalisa quando 10% da tabela muda, então uma coluna nova numa tabela
    estável fica cega por meses. Coluna nova sem estatística é plano ruim sem
    aviso: o custo de analisar o banco inteiro depois de migrar é de segundos.

    Sem permissão de dono numa tabela, o Postgres só avisa e segue — nunca
    derruba o `migrate`.
    """
    from django.db import connections

    if not plan:
        return
    conexao = connections[using]
    if conexao.vendor != "postgresql":
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute("ANALYZE")
    except Exception as exc:  # estatística é otimização: nunca derruba o deploy
        logger.warning("ANALYZE depois da migração falhou: %s", exc)


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

        # `sender=self`: o `post_migrate` sai uma vez por app; preso ao núcleo, o
        # ANALYZE roda uma vez por `migrate`.
        post_migrate.connect(analisar_depois_de_migrar, sender=self, dispatch_uid="nucleo_analyze")
