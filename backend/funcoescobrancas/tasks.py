# backend/funcoescobrancas/tasks.py
"""
Tarefas Celery do `funcoescobrancas` — seguem o AD-8 (nova integração externa
→ Celery task em Python). São wrappers finos sobre `services.py`: a lógica
fica testável sem Celery, e aqui só entra retry/Dead Letter Queue.

Em dev, `CELERY_TASK_ALWAYS_EAGER` roda estas tarefas in-process (sem Redis/
worker) — ver `config.settings`.
"""
import logging

from celery import shared_task

from nucleo.tasks import DLQTask

from . import services
from .client import AsaasAPIError
from .services import CobrancaBloqueada

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def criar_cobranca(self, conta_receber_id, vencimento=None, item_lote_id=None):
    """Garante o customer e cria o `payment`/`Boleto` no Asaas para a ContaReceber.

    `vencimento` (ISO) é a data que a pessoa escolheu na prévia — a segunda via
    de um título vencido. Vazio: a data do contrato, ajustada para o dia útil.
    `item_lote_id` é o item do lote de cobrança (item 52) que esta task resolve:
    ele recebe o boleto ou o motivo de não ter saído.
    """
    from datetime import date

    from django.db import transaction

    from moduloerp.models import ContaReceber
    from nucleo.tenancy import rls_bypass, tenant_context

    from .segunda_via import VencimentoInvalido

    # A task roda fora de request (sem JWT/tenant): a própria conta carrega o
    # tenant. Sem armar o contexto, a RLS fail-closed esconde a linha do worker
    # (mesmo padrão da task de NF e do processamento de webhook Asaas).
    with rls_bypass():
        tenant_id = (
            ContaReceber.objects.filter(pk=conta_receber_id)
            .values_list('tenant_id', flat=True).first()
        )
    if tenant_id is None:
        logger.warning("Geração de cobrança ignorada: ContaReceber #%s não existe.", conta_receber_id)
        return None

    try:
        falha = None
        with tenant_context(tenant_id), transaction.atomic():
            # A linha da conta trancada durante a emissão: dois cliques (ou o
            # lote e o botão ao mesmo tempo) viram duas tasks, e sem o lock as
            # duas veriam "sem boleto ativo" e criariam duas cobranças.
            conta = (
                ContaReceber.objects.select_for_update(of=('self',))
                .select_related('cliente', 'empreendimento', 'cliente_empreendimento')
                .get(pk=conta_receber_id)
            )
            try:
                boleto = services.gerar_cobranca_asaas(
                    conta, date.fromisoformat(vencimento) if vencimento else None,
                )
            except (AsaasAPIError, CobrancaBloqueada) as exc:
                # O que já aconteceu no gateway precisa ficar gravado: o boleto
                # ERRO que a tela mostra e o anterior que a segunda via já
                # cancelou no Asaas. Propagar aqui dentro desfaria os dois.
                falha = exc
        if falha is not None:
            if not isinstance(falha, AsaasAPIError) or self.request.retries >= self.max_retries:
                _anotar_item(tenant_id, item_lote_id, erro=falha)
            raise falha
        _anotar_item(tenant_id, item_lote_id, boleto=boleto)
        logger.info("Cobrança Asaas garantida para ContaReceber #%s — Boleto #%s (gateway_id=%s)",
                    conta_receber_id, boleto.boleto_id, boleto.gateway_id)
        return boleto.boleto_id
    except VencimentoInvalido as exc:
        # A data escolhida passou enquanto a task esperava na fila: dado, não
        # falha transitória — retry não resolve.
        logger.error("Cobrança recusada para ContaReceber #%s: %s", conta_receber_id, exc.mensagem)
        _anotar_item(tenant_id, item_lote_id, erro=exc)
        raise
    except CobrancaBloqueada as exc:
        # Trava de identidade (nome/CPF divergente, sem documento): é um
        # problema de DADO, não transitório — retry não resolve. A view já
        # barra isso de forma síncrona; se chegou aqui (ex.: corrida com o
        # gateway), NÃO reemitir e deixar a falha visível na DLQ (FailedTask).
        logger.error("Cobrança Asaas BLOQUEADA para ContaReceber #%s [%s]: %s",
                     conta_receber_id, exc.code, exc.mensagem)
        raise
    except AsaasAPIError as exc:
        logger.warning("Falha ao criar cobrança Asaas para ContaReceber #%s (tentativa %s/%s): %s",
                       conta_receber_id, self.request.retries + 1, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=60)


def _anotar_item(tenant_id, item_lote_id, *, boleto=None, erro=None):
    """O desfecho de uma conta do lote, na frase que a tela mostra."""
    if not item_lote_id:
        return
    from moduloerp.models import ItemLoteCobranca
    from nucleo.tenancy import tenant_context

    if boleto is not None:
        campos = {'situacao': ItemLoteCobranca.Situacao.EMITIDO, 'boleto': boleto, 'mensagem': ''}
    else:
        mensagem = getattr(erro, 'mensagem', None) or 'O Asaas não aceitou a cobrança desta conta.'
        campos = {'situacao': ItemLoteCobranca.Situacao.ERRO, 'mensagem': str(mensagem)[:500]}
    with tenant_context(tenant_id):
        ItemLoteCobranca.objects.filter(pk=item_lote_id).update(**campos)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def processar_evento_webhook(self, *, evento_id, tipo, payload):
    """ Processa (idempotente) um evento recebido do webhook do Asaas. """
    evento = services.processar_evento_webhook(evento_id=evento_id, tipo=tipo, payload=payload)
    logger.info("Evento Asaas %s (%s) processado: %s", evento_id, tipo, evento.resultado)
    return evento.pk
