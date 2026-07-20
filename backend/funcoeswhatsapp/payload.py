# backend/funcoeswhatsapp/payload.py
"""
Parsing do payload do webhook da Meta (WhatsApp Cloud API).

Porte fiel do `controllers/whatsappController.js` + `utils.js` do serviço Node:
extrai uma mensagem **normalizada** do envelope da Meta e sanitiza o payload
para logging sem vazar PII (número/conteúdo).
"""
import copy


def extrair_phone_number_id(payload):
    """`metadata.phone_number_id` (o número que RECEBEU a mensagem) — chave de
    resolução do tenant na borda. `None` se o envelope não tiver o campo."""
    try:
        value = payload['entry'][0]['changes'][0]['value']
        return value.get('metadata', {}).get('phone_number_id')
    except (KeyError, IndexError, TypeError):
        return None


def extrair_mensagem(payload):
    """Devolve uma mensagem normalizada, ou `None` se o evento não for uma
    mensagem de usuário processável (status de entrega, tipo não suportado…).

    Formato normalizado::

        {'id': str, 'from': str, 'type': str, 'body': str, 'media_id': str|None}
    """
    try:
        value = payload['entry'][0]['changes'][0]['value']
        messages = value.get('messages')
        if not messages:
            return None
        msg = messages[0]
    except (KeyError, IndexError, TypeError):
        return None

    tipo = msg.get('type')
    body = ''
    media_id = None

    if tipo == 'text':
        body = (msg.get('text', {}).get('body') or '').strip()
    elif tipo == 'interactive':
        interativo = msg.get('interactive', {})
        subtipo = interativo.get('type')
        if subtipo == 'button_reply':
            body = interativo.get('button_reply', {}).get('id', '')
        elif subtipo == 'list_reply':
            body = interativo.get('list_reply', {}).get('id', '')
    elif tipo in ('image', 'video', 'audio', 'document'):
        media_id = msg.get(tipo, {}).get('id')
    else:
        # Tipo não suportado (location, contacts, reaction…) — ignora.
        return None

    return {
        'id': msg.get('id'),
        'from': msg.get('from'),
        'type': tipo,
        'body': body,
        'media_id': media_id,
    }


def sanitizar_payload(payload):
    """Cópia do payload segura para logging: mascara número e remove conteúdo
    (PII). Porte do `sanitizeWebhookPayload` do Node."""
    if not isinstance(payload, dict):
        return {'sanitized': True}
    seguro = copy.deepcopy(payload)
    for entry in seguro.get('entry', []) or []:
        for change in entry.get('changes', []) or []:
            value = change.get('value') or {}
            for contact in value.get('contacts', []) or []:
                if contact.get('wa_id'):
                    contact['wa_id'] = f"...{contact['wa_id'][-4:]}"
                if contact.get('profile', {}).get('name'):
                    contact['profile']['name'] = '[REMOVIDO]'
            for message in value.get('messages', []) or []:
                if message.get('from'):
                    message['from'] = f"...{message['from'][-4:]}"
                if message.get('text', {}).get('body'):
                    message['text']['body'] = '[CONTEÚDO REMOVIDO]'
    return seguro
