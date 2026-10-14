# backend/moduloerp/tasks.py
"""
Tarefas Celery de Nota Fiscal — emissão/consulta de NFS-e (Fase 11.1).

Absorvem o microsserviço Node `funcoesnf` (+ bridge PHP): seguem o AD-8 (nova
integração externa → Celery task Python) e o padrão de RLS fora de request de
`nucleo.tenancy` (`rls_bypass` p/ achar o tenant → `tenant_context` p/ gravar),
o mesmo do `funcoesia.tasks` (11.3) e do `funcoescobrancas.tasks`.

São wrappers finos sobre `nfe_client` (HTTP puro): a decisão retry/DLQ mora
aqui. Falha transitória (`NFeIndisponivel`) → retry; esgotado → status `ERRO`
+ DLQ. Erro permanente (`NFeErro`: dados/negócio) → `ERRO` direto, sem retry.
"""
import logging

from celery import shared_task

from nucleo.tasks import DLQTask
from nucleo.tenancy import rls_bypass, tenant_context

from . import nfe_client
from .nfe_client import NFeIndisponivel, NFeErro

logger = logging.getLogger(__name__)


def _mapear_status(nfe_status):
    """Traduz o status cru da NFE.io para o `StatusNFE` local."""
    from .models import StatusNFE

    return {
        'Issued': StatusNFE.EMITIDA,
        'Cancelled': StatusNFE.CANCELADA,
        'Error': StatusNFE.ERRO,
    }.get(nfe_status, StatusNFE.PROCESSANDO)


def _aplicar_retorno(nf, dados):
    """Grava o retorno normalizado da NFE.io na NF (dentro do tenant_context)."""
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone
    from .models import StatusNFE

    status_anterior = nf.status
    nf.status = _mapear_status(dados.get('status'))
    if dados.get('nfe_io_id'):
        nf.nfe_io_id = dados['nfe_io_id']
    if dados.get('numero'):
        nf.numero = dados['numero']
    if dados.get('chave_acesso'):
        nf.chave_acesso = dados['chave_acesso']
    if dados.get('data_emissao'):
        nf.data_emissao = parse_datetime(dados['data_emissao']) or nf.data_emissao
    if nf.status == StatusNFE.CANCELADA:
        # Carimba a data de cancelamento (da NFE.io, ou "agora" na transição).
        cancelamento = dados.get('data_cancelamento')
        nf.data_cancelamento = (parse_datetime(cancelamento) if cancelamento else None) or nf.data_cancelamento or timezone.now()
    nf.dados_retorno_api = dados.get('full_response')
    nf.save()

    # Baixa PDF/XML quando a NF está emitida. A NFE.io não devolve o link no
    # corpo do invoice — resolve-se pelos endpoints /pdf|/xml (302 → blob
    # assinado público). Sem os arquivos, o download da UI ficaria vazio.
    # Idempotente: só baixa o que ainda falta (uma reconsulta não recria órfãos);
    # a 1ª emissão às vezes ainda não tem o arquivo pronto e uma consulta posterior
    # completa.
    if nf.status == StatusNFE.EMITIDA and nf.nfe_io_id and not (nf.arquivo_pdf and nf.arquivo_xml):
        client = nfe_client.cliente_do_tenant(nf.tenant_id, nf.entidade_id)
        url_pdf = None if nf.arquivo_pdf else (dados.get('url_pdf') or client.resolver_url_arquivo(nf.nfe_io_id, 'pdf'))
        url_xml = None if nf.arquivo_xml else (dados.get('url_xml') or client.resolver_url_arquivo(nf.nfe_io_id, 'xml'))
        if url_pdf or url_xml:
            from .views import _registrar_arquivos_nf  # lazy: evita ciclo de import
            _registrar_arquivos_nf(nf, url_pdf, url_xml)

    # Ao CANCELAR, a NFE.io gera uma NOVA versão do PDF/XML (com a marca
    # "CANCELADA" e a data de cancelamento). Rebaixa forçado — sobrescrevendo o
    # arquivo emitido — para que o documento guardado como fallback já seja o
    # cancelado (o caminho ao vivo `documento` refaz isso na hora da abertura).
    if nf.status == StatusNFE.CANCELADA and nf.nfe_io_id and status_anterior != StatusNFE.CANCELADA:
        client = nfe_client.cliente_do_tenant(nf.tenant_id, nf.entidade_id)
        url_pdf = dados.get('url_pdf') or client.resolver_url_arquivo(nf.nfe_io_id, 'pdf')
        url_xml = dados.get('url_xml') or client.resolver_url_arquivo(nf.nfe_io_id, 'xml')
        if url_pdf or url_xml:
            from .views import _registrar_arquivos_nf
            _registrar_arquivos_nf(nf, url_pdf, url_xml)


def _marcar_erro(nf, mensagem, payload=None):
    """Marca a NF como `ERRO` preservando a causa em `dados_retorno_api`.

    `payload` é o corpo cru da NFE.io (códigos/mensagens) quando o erro veio da
    API — é o que a UI abre no popup de detalhes. Sem ele (erro de validação
    local), guarda só a frase.
    """
    from .models import StatusNFE

    nf.status = StatusNFE.ERRO
    nf.dados_retorno_api = {'erro': str(mensagem), 'detalhes': payload}
    nf.save(update_fields=['status', 'dados_retorno_api', 'atualizado_em'])


def _acompanhar_ate_sair_de_processando(nf_id, tentativa):
    """Agenda a próxima consulta enquanto a NFE.io não decide a nota.

    **O defeito (item 58, revisão de 01/10/2026).** A NFE.io responde "Created"
    e emite depois — a prefeitura é que decide, em segundos ou minutos. O SGI
    gravava "Processando" e não perguntava de novo: a nota 12 do dev estava
    emitida lá (nº 6) e "Processando" aqui, e a pessoa via nota parada. Agora a
    consulta volta a cada `ERP_NFSE_CONSULTA_INTERVALO_S` até a nota sair de
    "Processando" ou as tentativas acabarem (aí fica o botão de consultar).
    """
    from payment.planos import ERP_NFSE_CONSULTA_INTERVALO_S, ERP_NFSE_CONSULTA_TENTATIVAS

    if tentativa > ERP_NFSE_CONSULTA_TENTATIVAS:
        logger.warning("NFS-e %s segue em processamento na NFE.io depois de %s consultas.",
                       nf_id, ERP_NFSE_CONSULTA_TENTATIVAS)
        return
    consultar_nota_fiscal_servico.apply_async(
        args=[nf_id], kwargs={'tentativa': tentativa}, countdown=ERP_NFSE_CONSULTA_INTERVALO_S,
    )


def _carregar_nfse(nf_id):
    """Retorna (tenant_id, dados imutáveis) da NFS-e sob bypass de RLS.

    A task roda fora de request (sem JWT/tenant): a própria NF carrega o tenant.
    Retorna `None` se a NF não existir mais.
    """
    from .models import NotaFiscalServico

    with rls_bypass():
        try:
            nf = NotaFiscalServico.objects.get(pk=nf_id)
        except NotaFiscalServico.DoesNotExist:
            return None
        return {
            'tenant_id': nf.tenant_id,
            'city_service_code': nf.city_service_code,
            'description': nf.description,
            'services_amount': nf.services_amount,
            'borrower_data': nf.borrower_data,
            'nfe_io_id': nf.nfe_io_id,
            'entidade_id': nf.entidade_id,
        }


@shared_task(bind=True, base=DLQTask, max_retries=3)
def emitir_nota_fiscal_servico(self, nf_id):
    """Emite a NFS-e de id `nf_id` na NFE.io e grava o retorno na NF."""
    from .models import NotaFiscalServico, StatusNFE

    dados_nf = _carregar_nfse(nf_id)
    if dados_nf is None:
        logger.warning("Emissão de NFS-e ignorada: NF %s não existe.", nf_id)
        return
    tenant_id = dados_nf['tenant_id']

    # Monta o payload (valida dados do tomador). Falta de dado é permanente → ERRO.
    try:
        payload = nfe_client.montar_payload_nfse(
            city_service_code=dados_nf['city_service_code'],
            description=dados_nf['description'],
            services_amount=dados_nf['services_amount'],
            borrower_data=dados_nf['borrower_data'],
        )
    except NFeErro as exc:
        logger.warning("Emissão de NFS-e %s inválida: %s", nf_id, exc)
        with tenant_context(tenant_id):
            _marcar_erro(NotaFiscalServico.objects.get(pk=nf_id), exc)
        return

    with tenant_context(tenant_id):
        NotaFiscalServico.objects.filter(pk=nf_id).update(status=StatusNFE.PROCESSANDO)

    try:
        dados = nfe_client.cliente_do_tenant(tenant_id, dados_nf.get('entidade_id')).emitir_nfse(payload)
    except NFeErro as exc:
        logger.warning("NFE.io recusou a emissão da NFS-e %s: %s", nf_id, exc)
        with tenant_context(tenant_id):
            _marcar_erro(NotaFiscalServico.objects.get(pk=nf_id), exc, getattr(exc, 'payload', None))
        return
    except NFeIndisponivel as exc:
        logger.warning("NFE.io indisponível p/ emissão da NFS-e %s (tentativa %s/%s): %s",
                       nf_id, self.request.retries + 1, self.max_retries, exc)
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            with tenant_context(tenant_id):
                _marcar_erro(NotaFiscalServico.objects.get(pk=nf_id),
                             f"NFE.io indisponível: {exc}")
            raise

    with tenant_context(tenant_id):
        nf = NotaFiscalServico.objects.get(pk=nf_id)
        _aplicar_retorno(nf, dados)
        ainda_processando = nf.status == StatusNFE.PROCESSANDO
    logger.info("NFS-e %s emitida na NFE.io (invoice=%s, status=%s).",
                nf_id, dados.get('nfe_io_id'), dados.get('status'))
    if ainda_processando:
        _acompanhar_ate_sair_de_processando(nf_id, 1)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def consultar_nota_fiscal_servico(self, nf_id, tentativa=0):
    """Consulta na NFE.io o status atual da NFS-e e atualiza a NF.

    `tentativa` > 0 é o acompanhamento automático depois da emissão: ainda em
    processamento, agenda a próxima. A consulta pedida pela tela vem com 0 e
    não encadeia.
    """
    from .models import NotaFiscalServico, StatusNFE

    dados_nf = _carregar_nfse(nf_id)
    if dados_nf is None:
        logger.warning("Consulta de NFS-e ignorada: NF %s não existe.", nf_id)
        return
    if not dados_nf['nfe_io_id']:
        logger.info("Consulta de NFS-e %s ignorada: sem nfe_io_id.", nf_id)
        return
    tenant_id = dados_nf['tenant_id']

    try:
        dados = nfe_client.cliente_do_tenant(tenant_id, dados_nf.get('entidade_id')).consultar_nfse(dados_nf['nfe_io_id'])
    except NFeErro as exc:
        logger.warning("NFE.io recusou a consulta da NFS-e %s: %s", nf_id, exc)
        with tenant_context(tenant_id):
            _marcar_erro(NotaFiscalServico.objects.get(pk=nf_id), exc, getattr(exc, 'payload', None))
        return
    except NFeIndisponivel as exc:
        logger.warning("NFE.io indisponível p/ consulta da NFS-e %s (tentativa %s/%s): %s",
                       nf_id, self.request.retries + 1, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=60)

    with tenant_context(tenant_id):
        nf = NotaFiscalServico.objects.get(pk=nf_id)
        _aplicar_retorno(nf, dados)
        ainda_processando = nf.status == StatusNFE.PROCESSANDO
    logger.info("NFS-e %s consultada na NFE.io (status=%s).", nf_id, dados.get('status'))
    if tentativa and ainda_processando:
        _acompanhar_ate_sair_de_processando(nf_id, tentativa + 1)


@shared_task(bind=True, base=DLQTask, max_retries=3)
def cancelar_nota_fiscal_servico(self, nf_id):
    """Cancela na NFE.io a NFS-e de id `nf_id` e grava o retorno na NF (D.1.3)."""
    from .models import NotaFiscalServico

    dados_nf = _carregar_nfse(nf_id)
    if dados_nf is None:
        logger.warning("Cancelamento de NFS-e ignorado: NF %s não existe.", nf_id)
        return
    if not dados_nf['nfe_io_id']:
        logger.info("Cancelamento de NFS-e %s ignorado: sem nfe_io_id.", nf_id)
        return
    tenant_id = dados_nf['tenant_id']

    try:
        dados = nfe_client.cliente_do_tenant(tenant_id, dados_nf.get('entidade_id')).cancelar_nfse(dados_nf['nfe_io_id'])
    except NFeErro as exc:
        logger.warning("NFE.io recusou o cancelamento da NFS-e %s: %s", nf_id, exc)
        with tenant_context(tenant_id):
            _marcar_erro(NotaFiscalServico.objects.get(pk=nf_id), exc, getattr(exc, 'payload', None))
        return
    except NFeIndisponivel as exc:
        logger.warning("NFE.io indisponível p/ cancelamento da NFS-e %s (tentativa %s/%s): %s",
                       nf_id, self.request.retries + 1, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=60)

    with tenant_context(tenant_id):
        _aplicar_retorno(NotaFiscalServico.objects.get(pk=nf_id), dados)
    logger.info("NFS-e %s cancelada na NFE.io (status=%s).", nf_id, dados.get('status'))
