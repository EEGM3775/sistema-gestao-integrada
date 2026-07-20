# backend/funcoeswhatsapp/views.py
"""
Webhook do WhatsApp (Fase C, §3/§4.3) — porte do `controllers/whatsappController.js`.

É uma **view Django simples** (não DRF): precisa do corpo bruto para validar o
HMAC e não usa autenticação de usuário (a borda autentica pela assinatura da
Meta). Princípio "responder rápido, processar depois" (§3.5): valida, enfileira
e devolve `200` em milissegundos; o trabalho é da Celery task.

    GET  → handshake de verificação da Meta (hub.verify_token).
    POST → valida a assinatura, resolve o tenant, dedup e enfileira.
"""
import json
import logging

from django.http import HttpResponse, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .payload import extrair_mensagem, extrair_phone_number_id, sanitizar_payload
from .security import assinatura_valida
from .state import ja_processada
from .tenant_resolver import resolver_canal

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(View):

    def get(self, request):
        """Handshake da Meta: ecoa `hub.challenge` se o `hub.verify_token` bater
        o verify token do canal que recebeu a assinatura."""
        modo = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge', '')
        phone_number_id = request.GET.get('phone_number_id') or request.GET.get('hub.phone_number_id')

        canal = resolver_canal(phone_number_id) if phone_number_id else _canal_por_verify_token(token)
        if modo == 'subscribe' and canal is not None and token and token == canal.verify_token:
            logger.info("Webhook WhatsApp verificado (canal %s).", canal.phone_number_id)
            return HttpResponse(challenge, content_type='text/plain')
        logger.warning("Webhook WhatsApp: verificação recusada.")
        return HttpResponseForbidden("verificação inválida")

    def post(self, request):
        corpo = request.body
        try:
            data = json.loads(corpo.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            logger.warning("Webhook WhatsApp: corpo não é JSON válido.")
            return HttpResponse(status=400)

        phone_number_id = extrair_phone_number_id(data)
        canal = resolver_canal(phone_number_id)
        if canal is None:
            # Número desconhecido: descarta sem vazar existência (ack à Meta).
            logger.warning("Webhook WhatsApp: phone_number_id desconhecido; descartado.")
            return HttpResponse(status=200)

        assinatura = request.headers.get('X-Hub-Signature-256', '')
        if not assinatura_valida(canal.app_secret, corpo, assinatura):
            logger.error("Webhook WhatsApp: assinatura inválida (canal %s).", canal.phone_number_id)
            return HttpResponseForbidden("assinatura inválida")

        logger.info("Webhook WhatsApp recebido: %s", sanitizar_payload(data))

        mensagem = extrair_mensagem(data)
        if mensagem is None:
            # Status de entrega ou tipo não suportado — nada a processar.
            return HttpResponse(status=200)

        if ja_processada(mensagem.get('id')):
            logger.info("Webhook WhatsApp: mensagem repetida ignorada (idempotência).")
            return HttpResponse(status=200)

        # Enfileira e responde já. A task re-resolve o canal por phone_number_id.
        from .tasks import processar_mensagem_whatsapp
        processar_mensagem_whatsapp.delay(canal.phone_number_id, mensagem)
        return HttpResponse(status=200)


def _canal_por_verify_token(token):
    """Fallback do handshake quando a Meta não manda `phone_number_id` na
    verificação: localiza o canal ativo pelo verify token (sob bypass da RLS)."""
    if not token:
        return None
    from nucleo.tenancy import rls_bypass
    from .models import CanalWhatsApp
    with rls_bypass():
        return CanalWhatsApp.objects.filter(verify_token=token, ativo=True).first()
