# backend/funcoeswhatsapp/router.py
"""
Roteador de comandos por palavra-chave e papel (Fase C, §4.4) — porte do
`bot/commandRouter.js`. Inicia um fluxo quando um remetente **conhecido** manda
uma palavra-chave que o papel dele pode acionar.

A checagem de "responsável técnico" do Node foi **removida**: no modelo novo,
quem pode contribuir é equipe ∪ responsáveis técnicos; o fluxo do diário já lista
apenas as obras elegíveis, então a autorização fica garantida por construção.
"""
import logging

from .flows import FLOWS
from .identity import ROLE_FUNCIONARIO

logger = logging.getLogger(__name__)

# palavra-chave → (fluxo, papéis permitidos)
_COMANDOS = {
    'diario': ('diario', {ROLE_FUNCIONARIO}),
    'diário': ('diario', {ROLE_FUNCIONARIO}),
    'relatorio': ('diario', {ROLE_FUNCIONARIO}),
    'relatório': ('diario', {ROLE_FUNCIONARIO}),
    'obra': ('diario', {ROLE_FUNCIONARIO}),
}

_AJUDA = (
    "Olá! Sou o assistente da empresa. Para registrar um Diário de Obra, envie "
    "'diario'. Para cancelar qualquer operação, envie 'sair'."
)


def config_comando(texto):
    return _COMANDOS.get((texto or '').strip().lower())


def handle_command(conversa):
    cfg = config_comando(conversa.texto)
    if cfg is None:
        conversa.responder(_AJUDA)
        return
    fluxo_nome, papeis = cfg
    if conversa.role not in papeis:
        logger.warning("Comando '%s' negado ao papel '%s'.", conversa.texto, conversa.role)
        conversa.responder("Desculpe, você não tem permissão para executar este comando.")
        return
    FLOWS[fluxo_nome].start(conversa)
