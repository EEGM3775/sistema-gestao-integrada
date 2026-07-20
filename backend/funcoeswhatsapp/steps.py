# backend/funcoeswhatsapp/steps.py
"""Passos das máquinas de estado dos fluxos (Fase C). Porte de
`bot/conversationSteps.js`, adaptado ao modelo novo de **um diário por obra por
dia** (some a seleção de múltiplos diários do dia)."""

# Fluxo Diário de Obra
DIARIO_CONFIRMAR = 'diario:confirmar'
DIARIO_OBRA = 'diario:obra'
DIARIO_COLETA = 'diario:coleta'

# Fluxo Lead (pré-cadastro de número desconhecido)
LEAD_NOME = 'lead:nome'
LEAD_INTERESSE = 'lead:interesse'
