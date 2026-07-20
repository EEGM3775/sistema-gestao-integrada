# backend/funcoeswhatsapp/flows/__init__.py
"""Fluxos plugáveis do canal (Fase C, §5). Cada fluxo expõe `start(conversa)` e
`handle(conversa, estado)`; a regra de negócio vive no **módulo dono** (diário no
`modulodiario`, lead no `modulocrm`) — o fluxo só orquestra a conversa."""
from . import diario, lead

# Registro de fluxos por nome (guardado em `estado['flow']`).
FLOWS = {
    'diario': diario,
    'lead': lead,
}
