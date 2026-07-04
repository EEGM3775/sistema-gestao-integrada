# backend/modulocalendar/receivers.py
from django.dispatch import receiver
from django.core.cache import cache
from modulocrm.signals import interaction_changed
import logging

logger = logging.getLogger(__name__)

@receiver(interaction_changed)
def handle_interaction_change(sender, user_id, **kwargs):
    """
    Recebe o sinal de que uma interação mudou e limpa o cache do calendário.
    """
    if user_id:
        try:
            # Abordagem de força bruta: deleta pelo padrão
            cache_key_pattern = f"calendar_events_{user_id}_*"
            logger.info(f"Sinal recebido: Limpando cache do calendário para o usuário {user_id} com o padrão: {cache_key_pattern}")
            cache.delete_pattern(cache_key_pattern)
            logger.info(f"Cache limpo com padrão para usuário {user_id}.")

        except Exception as e:
            logger.error(f"Erro no receiver ao tentar limpar o cache do calendário: {e}")
