# backend/funcoesia/tasks.py
"""
Pipeline de análise de imagem por IA — Celery task Python (Fase 11.3).

Substitui o microsserviço Node `funcoesia`: em vez de o backend chamar o Node
por HTTP (com o `Token` legado que hoje devolve 401 — achado **D1**), o worker
Python roda a análise *in-process*:

  1. localiza o `DocumentoDiario` e o seu tenant (fora de request → bypass da RLS);
  2. lê a imagem do FileField **local** (sem download HTTP);
  3. chama a LLM de visão local (`llm_client.analisar_imagem`);
  4. grava o `AnaliseImagemIA` no tenant correto (contexto RLS armado).

Segue o AD-8 (integração externa → Celery task) e o padrão de RLS fora de
request de `nucleo.tenancy` (`rls_bypass`/`tenant_context`). Falha transitória
(LLM indisponível) → retry; esgotado → `erro` + DLQ. Resposta malformada da LLM
→ `erro` (permanente, sem retry).
"""
import logging
import mimetypes

from celery import shared_task

from nucleo.tasks import DLQTask
from nucleo.tenancy import rls_bypass, tenant_context

from .llm_client import analisar_imagem, LLMIndisponivel, LLMResultadoInvalido

logger = logging.getLogger(__name__)


def _marcar_status(tenant_id, documento_id, *, status, resultado=None):
    """Grava/atualiza o `AnaliseImagemIA` do documento no seu tenant."""
    from .models import AnaliseImagemIA

    with tenant_context(tenant_id):
        analise, _created = AnaliseImagemIA.objects.get_or_create(
            documento_id=documento_id,
            defaults={'tenant_id': tenant_id, 'status': status},
        )
        analise.status = status
        campos = ['status', 'data_atualizacao']
        if resultado is not None:
            analise.resultado_analise = resultado
            campos.insert(0, 'resultado_analise')
        analise.save(update_fields=campos)
    return analise


@shared_task(bind=True, base=DLQTask, max_retries=3)
def analisar_documento_ia(self, documento_id, tipo_analise='completa'):
    """Analisa a imagem de um `DocumentoDiario` e grava o `AnaliseImagemIA`."""
    from modulodiario.models import DocumentoDiario

    # 1. Documento + tenant. A task roda fora de request (sem JWT/tenant), então
    #    localiza sob bypass — o próprio documento carrega o tenant de destino.
    with rls_bypass():
        try:
            documento = DocumentoDiario.objects.get(pk=documento_id)
        except DocumentoDiario.DoesNotExist:
            logger.warning("Análise de IA ignorada: documento %s não existe.", documento_id)
            return
        tenant_id = documento.tenant_id
        arquivo = documento.arquivo

    if not arquivo:
        logger.warning("Análise de IA: documento %s sem arquivo.", documento_id)
        _marcar_status(tenant_id, documento_id, status='erro',
                       resultado={'erro': 'Documento sem arquivo para analisar.'})
        return

    # Marca em processamento (também cria a linha no primeiro disparo / reset no reprocesso).
    _marcar_status(tenant_id, documento_id, status='em_processamento')

    # 2. Lê a imagem in-process (FileField local — sem HTTP).
    try:
        with arquivo.open('rb') as fh:
            image_bytes = fh.read()
    except (OSError, ValueError) as exc:
        logger.error("Análise de IA: falha ao ler arquivo do documento %s: %s", documento_id, exc)
        _marcar_status(tenant_id, documento_id, status='erro',
                       resultado={'erro': f'Falha ao ler o arquivo: {exc}'})
        return

    mime_type = mimetypes.guess_type(arquivo.name)[0] or 'image/jpeg'

    # 3. Chama a LLM de visão local.
    try:
        resultado = analisar_imagem(image_bytes, mime_type, tipo_analise)
    except LLMResultadoInvalido as exc:
        # Resposta malformada: permanente, não adianta repetir — fica visível como `erro`.
        logger.warning("Análise de IA do documento %s inválida: %s", documento_id, exc)
        _marcar_status(tenant_id, documento_id, status='erro',
                       resultado={'erro': f'Resultado da IA inválido: {exc}'})
        return
    except LLMIndisponivel as exc:
        # Transitório: repete; ao esgotar, marca `erro` e vai para a DLQ.
        logger.warning("LLM de visão indisponível p/ documento %s (tentativa %s/%s): %s",
                       documento_id, self.request.retries + 1, self.max_retries, exc)
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            _marcar_status(tenant_id, documento_id, status='erro',
                           resultado={'erro': f'LLM de visão indisponível: {exc}'})
            raise

    # 4. Sucesso.
    _marcar_status(tenant_id, documento_id, status='concluido', resultado=resultado)
    logger.info("Análise de IA (%s) concluída para o documento %s.", tipo_analise, documento_id)
