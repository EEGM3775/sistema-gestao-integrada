# backend/funcoeswhatsapp/tasks.py
"""
Orquestração da conversa fora de request (Fase C, §3) — porte do `bot/bot.js`.

A view do webhook enfileira; aqui o worker Celery processa: resolve o canal
(→ tenant), identifica o remetente e avança a máquina de estados. Toda leitura/
escrita no ORM roda sob `tenant_context` (a RLS é fail-closed — sem contexto,
zero linhas). O envio de respostas (HTTP) acontece dentro do bloco, mas o cliente
nunca levanta exceção (só loga), então não afeta a transação.

Sem JWT: a autoria vem de telefone→pessoa e a escrita é in-process (padrão da
Fase B). O JWT de serviço da Fase 10.8 fica de plano B (canal como processo
separado) — ver docs/modulos/funcoeswhatsapp.md §4.3.
"""
import logging

from celery import shared_task

from nucleo.tasks import DLQTask
from nucleo.tenancy import tenant_context

from . import router
from .conversa import Conversa
from .flows import FLOWS
from .identity import identificar, ROLE_UNKNOWN
from .tenant_resolver import resolver_canal
from .whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def processar_mensagem_whatsapp(self, phone_number_id, mensagem):
    """Processa uma mensagem normalizada do webhook (ver `payload.extrair_mensagem`)."""
    canal = resolver_canal(phone_number_id)
    if canal is None:
        logger.warning("WhatsApp: canal %s sumiu antes do processamento; descartado.", phone_number_id)
        return

    client = WhatsAppClient(canal)
    telefone = mensagem.get('from') or ''
    texto = (mensagem.get('body') or '').strip()

    with tenant_context(canal.tenant_id):
        # Comando global: 'sair' encerra qualquer conversa.
        if texto.lower() == 'sair':
            from . import state
            state.clear_state(canal.tenant_id, telefone)
            client.enviar_texto(telefone, "Sessão encerrada. Para recomeçar, envie uma mensagem.")
            return

        pessoa, role = identificar(telefone)
        conversa = Conversa(
            canal=canal, client=client, telefone=telefone,
            mensagem=mensagem, pessoa=pessoa, role=role,
        )

        estado = conversa.get_state()
        if estado:
            # Conversa em andamento. Mudança de cadastro no meio → reinicia (segurança).
            if estado.get('role') != role:
                conversa.clear_state()
                conversa.responder(
                    "Notamos uma alteração no seu cadastro. Por segurança, a sessão "
                    "foi reiniciada. Envie sua mensagem novamente."
                )
                return
            fluxo = FLOWS.get(estado.get('flow'))
            if fluxo is None:
                conversa.clear_state()
                conversa.responder("Sua sessão expirou e foi reiniciada. Envie a mensagem novamente.")
                return
            fluxo.handle(conversa, estado)
        else:
            # Conversa nova.
            if role == ROLE_UNKNOWN:
                FLOWS['lead'].start(conversa)
            else:
                router.handle_command(conversa)
