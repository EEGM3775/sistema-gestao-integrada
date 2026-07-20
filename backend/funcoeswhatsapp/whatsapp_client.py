# backend/funcoeswhatsapp/whatsapp_client.py
"""
Cliente de saída da WhatsApp Cloud API (Fase C, §4.5).

Porte do `services/whatsappService.js` (Node) com **credenciais por tenant**
(vindas do `CanalWhatsApp`). Erros de envio são **logados** (observabilidade
10.1) e **não** derrubam a task — o pior caso é uma resposta não entregue, nunca
um diário perdido.
"""
import logging

import requests

from nucleo.rate_limit import consumir

logger = logging.getLogger(__name__)

_TIMEOUT = (5, 30)


class WhatsAppClient:
    def __init__(self, canal):
        self.canal = canal
        versao = canal.api_version or 'v20.0'
        self._base = f"https://graph.facebook.com/{versao}"
        self._token = canal.access_token or ''
        self._phone_number_id = canal.phone_number_id

    # --- saída ---------------------------------------------------------------
    def enviar_texto(self, to, texto):
        self._enviar({
            'messaging_product': 'whatsapp', 'to': to, 'type': 'text',
            'text': {'body': texto},
        })

    def enviar_botoes(self, to, texto, botoes):
        """Botões de resposta rápida (máx. 3). `botoes`: [{'id','title'}]."""
        botoes = botoes[:3]
        self._enviar({
            'messaging_product': 'whatsapp', 'to': to, 'type': 'interactive',
            'interactive': {
                'type': 'button',
                'body': {'text': texto},
                'action': {'buttons': [
                    {'type': 'reply', 'reply': {'id': b['id'], 'title': b['title'][:20]}}
                    for b in botoes
                ]},
            },
        })

    def enviar_lista(self, to, texto, texto_botao, itens):
        """Lista de opções (máx. 10). `itens`: [{'id','title','description'?}]."""
        itens = itens[:10]
        self._enviar({
            'messaging_product': 'whatsapp', 'to': to, 'type': 'interactive',
            'interactive': {
                'type': 'list',
                'header': {'type': 'text', 'text': 'Opções'},
                'body': {'text': texto},
                'footer': {'text': 'Selecione uma opção'},
                'action': {
                    'button': (texto_botao or 'Ver opções')[:20],
                    'sections': [{
                        'title': 'Lista',
                        'rows': [{
                            'id': str(i['id'])[:200],
                            'title': (i.get('title') or 'Sem título')[:24],
                            'description': (i.get('description') or '')[:72],
                        } for i in itens],
                    }],
                },
            },
        })

    def _enviar(self, payload):
        # Camada 2: a Meta aplica limite proprio e agressivo, e estourar
        # prejudica a REPUTACAO do numero — nao so a requisicao. Ver
        # docs/arquitetura/rate-limiting.md.
        consumir("whatsapp")
        if not self._token:
            logger.warning("WhatsApp: canal %s sem access_token; envio ignorado.", self._phone_number_id)
            return
        try:
            resp = requests.post(
                f"{self._base}/{self._phone_number_id}/messages",
                json=payload,
                headers={'Authorization': f'Bearer {self._token}'},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("WhatsApp: falha ao enviar mensagem: %s", exc)

    # --- entrada (download de mídia) ----------------------------------------
    def baixar_midia(self, media_id):
        """Baixa a mídia da Meta em dois passos (metadata → URL → bytes).
        Retorna `(bytes, mime_type)` ou `(None, None)` em falha."""
        if not self._token:
            logger.warning("WhatsApp: canal sem access_token; download de mídia ignorado.")
            return None, None
        headers = {'Authorization': f'Bearer {self._token}'}
        try:
            info = requests.get(f"{self._base}/{media_id}", headers=headers, timeout=_TIMEOUT)
            info.raise_for_status()
            url = info.json().get('url')
            if not url:
                raise ValueError("URL de download ausente na resposta da Meta.")
            midia = requests.get(url, headers=headers, timeout=_TIMEOUT)
            midia.raise_for_status()
            return midia.content, midia.headers.get('content-type')
        except (requests.RequestException, ValueError) as exc:
            logger.error("WhatsApp: falha ao baixar mídia %s: %s", media_id, exc)
            return None, None
