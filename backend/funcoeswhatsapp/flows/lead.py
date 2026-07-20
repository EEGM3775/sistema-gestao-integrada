# backend/funcoeswhatsapp/flows/lead.py
"""
Fluxo de pré-cadastro → Lead (Fase C, §5 / decisão D2).

Porte do `preCadastroFlow.js`. Número desconhecido vira **Lead no `modulocrm`**
(consolida com a absorção do `funcoeslead`, Fase 11.2) — não o `nucleo.PreCadastro`
legado. A escrita roda in-process, sob o `tenant_context` da task; o Lead é
pontuado pelo serviço reusável do CRM (`services.pontuar_lead`).
"""
import logging

from ..steps import LEAD_NOME, LEAD_INTERESSE

logger = logging.getLogger(__name__)

_INTERESSES = ('cliente', 'fornecedor', 'outro')


def start(conversa):
    conversa.set_state({
        'flow': 'lead',
        'step': LEAD_NOME,
        'mensagem_inicial': conversa.texto,
    })
    conversa.responder(
        "Olá! Verifiquei que seu número não está em nosso sistema. Para agilizar "
        "seu atendimento, informe seu nome completo."
    )


def handle(conversa, estado):
    step = estado.get('step')

    if step == LEAD_NOME:
        nome = conversa.texto
        if not nome:
            conversa.responder("Por favor, informe seu nome completo.")
            return
        conversa.set_state({**estado, 'step': LEAD_INTERESSE, 'nome': nome})
        conversa.responder(
            f"Obrigado, {nome}. Qual é o seu interesse? "
            "(responda com 'cliente', 'fornecedor' ou 'outro')"
        )
        return

    if step == LEAD_INTERESSE:
        interesse = conversa.texto.lower()
        if interesse not in _INTERESSES:
            conversa.responder("Por favor, responda apenas com 'cliente', 'fornecedor' ou 'outro'.")
            return
        _criar_lead(conversa, estado.get('nome', ''), interesse)
        conversa.responder(
            "Obrigado! Suas informações foram registradas e nossa equipe entrará "
            "em contato em breve."
        )
        conversa.clear_state()


def _criar_lead(conversa, nome_completo, interesse):
    from modulocrm.models import Lead
    from modulocrm import services

    partes = (nome_completo or '').strip().split(' ', 1)
    first_name = partes[0] or 'Contato'
    last_name = partes[1] if len(partes) > 1 else 'WhatsApp'

    lead = Lead.objects.create(
        tenant_id=conversa.tenant_id,
        first_name=first_name[:100],
        last_name=last_name[:100],
        email='',
        phone=f"+{conversa.telefone}"[:20],
        source=f"WhatsApp ({interesse})",
    )
    # Reaproveita o scoring por regras absorvido do funcoeslead (Fase 11.2).
    services.pontuar_lead(lead)
    logger.info("Lead %s criado via WhatsApp (tenant %s).", lead.pk, conversa.tenant_id)
    return lead
