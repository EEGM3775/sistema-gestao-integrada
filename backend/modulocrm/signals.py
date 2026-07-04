# backend/modulocrm/signals.py
from django.dispatch import Signal

# Sinal que será enviado quando uma interação for modificada
# Fornece o user_id para que o receptor saiba qual cache limpar
interaction_changed = Signal()
