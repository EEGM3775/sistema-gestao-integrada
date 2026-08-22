# backend/moduloerp/views.py
import logging
from urllib.parse import urlparse
import requests
from nucleo.busca import BuscaSemAcento
from rest_framework import viewsets, permissions, views, filters, status as status_module
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin, TenantScopedAPIViewMixin
from nucleo.permissions import RequireModule, RequirePermission
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Case, When, Value, CharField, DecimalField, F
from django.db.models.functions import TruncMonth
from django.core.files.base import ContentFile
from decimal import Decimal
from os.path import basename

from funcoesimpexp.entrega import url_do_arquivo

from .impexp import RECURSO_NOTA_FISCAL
from .models import (
    Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto,
    CentroCusto, LoteRemessa, StatusConta, StatusNFE, RevisaoBaixa, StatusRevisaoBaixa, BaixaRequerRevisao
)
from .serializers import (
    TransacaoSerializer,
    NotaFiscalServicoSerializer,
    NotaFiscalProdutoSerializer,
    NotaFiscalSerializer,
    ContaPagarSerializer,
    ContaReceberSerializer,
    CobrancaClienteSerializer,
    BoletoSerializer,
    CentroCustoSerializer,
    LoteRemessaSerializer,
    BaixaSerializer,
    RevisaoBaixaSerializer,
)
from .filters import (
    TransacaoFilter, ContaPagarFilter, ContaReceberFilter,
    CobrancaClienteFilter, BoletoFilter, NotaFiscalServicoFilter,
)
from .pagination import ErpPageNumberPagination
from funcoescobrancas.tasks import criar_cobranca
from funcoescobrancas.client import AsaasAPIError
from funcoescobrancas.services import (
    validar_cliente_para_cobranca, CobrancaBloqueada,
    cancelar_cobranca_asaas, verificar_cobranca_asaas,
)
from .tasks import (
    emitir_nota_fiscal_servico, consultar_nota_fiscal_servico,
    cancelar_nota_fiscal_servico,
)

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _registrar_arquivos_nf(nf_instance, url_pdf, url_xml):
    """
    Downloads PDF and XML from URLs and saves them to the NotaFiscal instance.
    """
    try:
        # Download and save PDF (L8: timeout + nome derivado do path, sem query string).
        # O nome pode não vir com extensão (ex.: blob assinado da NFE.io, path
        # `/blob/download`) → garante a extensão certa para o download da UI.
        if url_pdf:
            response_pdf = requests.get(url_pdf, stream=True, timeout=(5, 30))
            response_pdf.raise_for_status()
            pdf_name = basename(urlparse(url_pdf).path)
            if not pdf_name.lower().endswith('.pdf'):
                pdf_name = f"nf_{nf_instance.id}.pdf"
            nf_instance.arquivo_pdf.save(pdf_name, ContentFile(response_pdf.content))
            logger.info(f"Arquivo PDF da NF ID {nf_instance.id} salvo: {pdf_name}")

        # Download and save XML
        if url_xml:
            response_xml = requests.get(url_xml, stream=True, timeout=(5, 30))
            response_xml.raise_for_status()
            xml_name = basename(urlparse(url_xml).path)
            if not xml_name.lower().endswith('.xml'):
                xml_name = f"nf_{nf_instance.id}.xml"
            nf_instance.arquivo_xml.save(xml_name, ContentFile(response_xml.content))
            logger.info(f"Arquivo XML da NF ID {nf_instance.id} salvo: {xml_name}")
        
        nf_instance.save()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao baixar arquivos da NF ID {nf_instance.id}: {e}")
        return False


def _verificar_documento_nf(nf):
    """
    Verifica AO VIVO a NFS-e na NFE.io (espelha `verificar_cobranca_asaas`): é o
    que a UI chama ao abrir o documento. **NFE.io no ar** → devolve a verdade do
    provedor (status atual + link assinado do PDF/XML, já a versão CANCELADA se
    foi cancelada) e atualiza a nota local; **fora do ar** → devolve a última
    versão guardada e sinaliza `gateway_online=False`. Nunca levanta exceção.
    """
    from .nfe_client import NFeClient, NFeIndisponivel, NFeErro
    from .tasks import _aplicar_retorno

    # D70 — a cópia LOCAL da nota sai pela porta única. Este payload é montado à
    # mão e não passa pelo serializer, então o mixin não o alcançava: era o
    # segundo caminho pelo qual `/media/` chegava ao browser, e o mais fácil de
    # esquecer justamente por não parecer um serializer.
    #
    # A URL da NFE.io (`dados['url_pdf']`, abaixo) continua sendo dela — é link
    # assinado do provedor, não arquivo nosso, e nada aqui deve reescrevê-lo.
    def _url_local(campo, especie):
        return url_do_arquivo(RECURSO_NOTA_FISCAL, especie, nf.pk) if campo else ''

    def _local(mensagem, online=False):
        return {
            'gateway_online': online,
            'status': nf.status,
            'url_pdf': _url_local(nf.arquivo_pdf, 'nfse_pdf'),
            'url_xml': _url_local(nf.arquivo_xml, 'nfse_xml'),
            'mensagem': mensagem,
        }

    if not nf.nfe_io_id:
        return _local('Nota sem ID na NFE.io — exibindo a versão local, se houver.')

    client = NFeClient()
    try:
        dados = client.consultar_nfse(nf.nfe_io_id)
    except NFeIndisponivel:
        return _local('NFE.io fora do ar — exibindo a última versão conhecida da nota.')
    except NFeErro as exc:
        return _local(f'NFE.io recusou a consulta: {exc}')

    _aplicar_retorno(nf, dados)   # atualiza status/arquivos locais (fallback)
    nf.refresh_from_db()
    url_pdf = dados.get('url_pdf') or client.resolver_url_arquivo(nf.nfe_io_id, 'pdf') or _url_local(nf.arquivo_pdf, 'nfse_pdf')
    url_xml = dados.get('url_xml') or client.resolver_url_arquivo(nf.nfe_io_id, 'xml') or _url_local(nf.arquivo_xml, 'nfse_xml')
    return {
        'gateway_online': True,
        'status': nf.status,
        'url_pdf': url_pdf,
        'url_xml': url_xml,
        'mensagem': '',
    }


def _dados_cliente_para_nf(cliente):
    """
    Snapshot do tomador/comprador gravado na NF, com os nomes de campo do
    model `Cliente` — contrato consumido por `nfe_client.montar_payload_nfse`
    (exige `cpf_cnpj`, `cep` e `cidade_ibge` para emitir a NFS-e).
    """
    if not cliente:
        return {}
    return {
        'cliente_id': cliente.cliente_id,
        'nome_completo': cliente.nome_completo,
        'cpf_cnpj': cliente.cpf_cnpj,
        'email': cliente.email,
        'endereco': cliente.endereco,
        'numero_endereco': cliente.numero_endereco,
        'complemento_endereco': cliente.complemento_endereco,
        'bairro': cliente.bairro,
        'cidade': cliente.cidade,
        'estado': cliente.estado,
        'cep': cliente.cep,
        'cidade_ibge': cliente.cidade_ibge,
    }


def _emitir_nf_para_conta_receber(request, conta, tipo_nf):
    """
    Emite NFS-e ou NF-e para uma ContaReceber e a vincula via
    `nota_fiscal_servico`/`nota_fiscal_produto`. A NF herda o `tenant` da
    conta (é criada fora de `perform_create`, então o mixin não a escopa).

    Migrado de FaturaViewSet._emitir_nf (consolidação Fatura → ContaPagar/
    ContaReceber, D.1.1): emissão de NF sempre foi exclusiva de títulos a
    receber, então a ação nasce direto no ContaReceberViewSet.

    Fase 11.1: a emissão de NFS-e deixou de chamar o microsserviço Node
    `funcoesnf` (`http://localhost:3003`) — agora enfileira a Celery task
    Python `emitir_nota_fiscal_servico`, que fala REST direto com a NFE.io.
    """
    try:
        if tipo_nf == 'servico' and conta.nota_fiscal_servico:
            return Response({'message': 'Nota Fiscal de Serviço já existente para esta conta.'}, status=status_module.HTTP_400_BAD_REQUEST)
        elif tipo_nf == 'produto' and conta.nota_fiscal_produto:
            return Response({'message': 'Nota Fiscal de Produto já existente para esta conta.'}, status=status_module.HTTP_400_BAD_REQUEST)

        # Create the NotaFiscal instance with required data
        if tipo_nf == 'servico':
            descricao_servico = request.data.get('descricao') or conta.descricao or 'Prestação de Serviços'

            nf = NotaFiscalServico.objects.create(
                tenant=conta.tenant,
                city_service_code=request.data.get('city_service_code', '010701'),
                description=descricao_servico,
                services_amount=conta.valor,
                borrower_data=_dados_cliente_para_nf(conta.cliente)
            )
            conta.nota_fiscal_servico = nf
        else:
            descricao_produto = request.data.get('descricao') or conta.descricao or 'Venda de Produtos'

            items_data = [{
                'descricao': descricao_produto,
                'quantidade': 1,
                'valor_unitario': float(conta.valor),
                'valor_total': float(conta.valor)
            }]

            nf = NotaFiscalProduto.objects.create(
                tenant=conta.tenant,
                buyer_data=_dados_cliente_para_nf(conta.cliente),
                items_data=items_data
            )
            conta.nota_fiscal_produto = nf
        conta.save()

        # Auditoria (Fase 9.E): emissão de NF é evento fiscal sensível.
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="emitir_nf", instance=conta, usuario=getattr(request, "user", None),
            detalhes={"tipo_nf": tipo_nf, "nf_id": nf.id, "valor": str(conta.valor)},
        )

        serializer_class = NotaFiscalServicoSerializer if tipo_nf == 'servico' else NotaFiscalProdutoSerializer

        if tipo_nf == 'servico':
            # Enfileira a emissão na NFE.io (Celery task Python — Fase 11.1). O
            # status vira EMITIDA/ERRO quando a task grava o retorno da NFE.io.
            nf.status = StatusNFE.PROCESSANDO
            nf.save(update_fields=['status', 'atualizado_em'])
            emitir_nota_fiscal_servico.delay(nf.id)
            return Response(
                {'message': 'Emissão de NFS-e iniciada — o status é atualizado quando a NFE.io responder.',
                 'data': serializer_class(nf).data},
                status=status_module.HTTP_202_ACCEPTED,
            )

        # NF-e (produto): a emissão via NFE.io nunca foi implementada (o
        # `funcoesnf` também recusava produto) — a NF fica registrada aguardando
        # a integração de produto. Ver docs/modulos/moduloerp.md.
        return Response(
            {'message': 'Nota Fiscal de Produto registrada. Emissão de NF-e ainda não integrada.',
             'data': serializer_class(nf).data},
            status=status_module.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"Erro interno ao emitir nota fiscal: {e}")
        return Response({'error': f'Erro interno do servidor: {str(e)}'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)

# --- ViewSets ---

class TransacaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Transacao.objects.all()
    serializer_class = TransacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.transacao"   # ledger: só .view no catálogo (escrita bloqueada)
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_class = TransacaoFilter
    search_fields = ['descricao']
    ordering_fields = ['data_transacao', 'valor']
    ordering = ['-data_transacao']

class NotaFiscalServicoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = NotaFiscalServico.objects.all()
    serializer_class = NotaFiscalServicoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.nf"
    action_permission_map = {"cancelar": "erp.nf.cancelar"}   # cancelamento = verbo próprio
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = NotaFiscalServicoFilter
    ordering_fields = ['data_emissao', 'criado_em', 'services_amount']
    ordering = ['-criado_em']

    @action(detail=True, methods=['post'], url_path='registrar-arquivos')
    def registrar_arquivos(self, request, pk=None):
        """
        Receives PDF and XML URLs from the microservice, downloads and saves them.
        """
        nf = self.get_object()
        url_pdf = request.data.get('url_pdf')
        url_xml = request.data.get('url_xml')

        if not url_pdf and not url_xml:
            return Response({'error': 'Pelo menos uma URL (url_pdf ou url_xml) é necessária.'}, status=status_module.HTTP_400_BAD_REQUEST)

        success = _registrar_arquivos_nf(nf, url_pdf, url_xml)

        if success:
            return Response({'message': 'Arquivos da nota fiscal registrados com sucesso.'}, status=status_module.HTTP_200_OK)
        else:
            return Response({'error': 'Falha ao baixar ou salvar os arquivos da nota fiscal.'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='documento')
    def documento(self, request, pk=None):
        """
        Verifica a nota AO VIVO na NFE.io e devolve os links atuais do PDF/XML
        (a versão CANCELADA quando cancelada). Se a NFE.io estiver fora do ar,
        devolve a última versão local e avisa. GET → exige apenas `erp.nf.view`.
        """
        nf = self.get_object()
        return Response(_verificar_documento_nf(nf))

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        """
        Enfileira o cancelamento da NFS-e na NFE.io (D.1.3). Só uma NF **emitida**
        e com `nfe_io_id` é cancelável; o status vira `CANCELADA` (ou `ERRO`)
        quando a Celery task grava o retorno da NFE.io.
        """
        nf = self.get_object()
        if not nf.nfe_io_id:
            return Response(
                {'error': 'NF sem ID externo (nfe_io_id) — nada a cancelar na NFE.io.'},
                status=status_module.HTTP_400_BAD_REQUEST,
            )
        if nf.status != StatusNFE.EMITIDA:
            return Response(
                {'error': 'Só é possível cancelar uma NF emitida.'},
                status=status_module.HTTP_400_BAD_REQUEST,
            )
        cancelar_nota_fiscal_servico.delay(nf.id)
        # Auditoria (Fase 9.E): cancelamento de NF é evento fiscal sensível.
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="cancelar_nf", instance=nf, usuario=getattr(request, "user", None),
            detalhes={"nf_id": nf.id, "nfe_io_id": nf.nfe_io_id},
        )
        return Response(
            {'message': 'Cancelamento enviado à NFE.io — o status é atualizado quando responder.'},
            status=status_module.HTTP_202_ACCEPTED,
        )


class NotaFiscalProdutoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = NotaFiscalProduto.objects.all()
    serializer_class = NotaFiscalProdutoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.nf"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['data_emissao', 'criado_em']
    ordering = ['-criado_em']

    @action(detail=True, methods=['post'], url_path='registrar-arquivos')
    def registrar_arquivos(self, request, pk=None):
        """
        Receives PDF and XML URLs from the microservice, downloads and saves them.
        """
        nf = self.get_object()
        url_pdf = request.data.get('url_pdf')
        url_xml = request.data.get('url_xml')

        if not url_pdf and not url_xml:
            return Response({'error': 'Pelo menos uma URL (url_pdf ou url_xml) é necessária.'}, status=status_module.HTTP_400_BAD_REQUEST)

        success = _registrar_arquivos_nf(nf, url_pdf, url_xml)

        if success:
            return Response({'message': 'Arquivos da nota fiscal registrados com sucesso.'}, status=status_module.HTTP_200_OK)
        else:
            return Response({'error': 'Falha ao baixar ou salvar os arquivos da nota fiscal.'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)


class ERPDashboardView(TenantScopedAPIViewMixin, views.APIView):
    """
    Provides aggregated and complex data for the Financial dashboard.
    """
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.relatorio"   # dashboard = relatório financeiro (GET→.view)
    # Teto próprio (S8): o hub agrega vários somatórios sobre todo o financeiro do
    # tenant — é a chamada mais cara da API e a que mais dói se alguém a repetir em
    # laço. Muito mais apertado que o teto geral de usuário.
    throttle_scope = "relatorio"
    def get(self, request, *args, **kwargs):
        today = timezone.localdate()
        one_year_ago = today - timedelta(days=365)

        # Allow filtering by empreendimento
        empreendimento_id = request.query_params.get('empreendimento_id')
        filtro_empreendimento = {}
        if empreendimento_id:
            filtro_empreendimento['empreendimento_id'] = empreendimento_id

        # Status em aberto — "Atrasado" não é persistido (StatusConta), é
        # derivado aqui mesmo via data_vencimento, junto com as faixas de aging.
        status_em_aberto = [StatusConta.ABERTO, StatusConta.PARCIAL]

        # 1. Aging Report - Contas a Receber (saldo em aberto, não o valor cheio)
        contas_a_receber_aging = self.scope_qs(ContaReceber.objects.all()).filter(
            status__in=status_em_aberto,
            **filtro_empreendimento
        ).annotate(
            categoria=Case(
                When(data_vencimento__lt=today - timedelta(days=90), then=Value('> 90 dias')),
                When(data_vencimento__lt=today - timedelta(days=60), then=Value('61-90 dias')),
                When(data_vencimento__lt=today - timedelta(days=30), then=Value('31-60 dias')),
                When(data_vencimento__lt=today, then=Value('1-30 dias Vencido')),
                When(data_vencimento=today, then=Value('Vence Hoje')),
                default=Value('A Vencer'),
                output_field=CharField(),
            ),
            saldo=F('valor') + F('juros') + F('multa') - F('desconto') - F('valor_pago'),
        ).values('categoria').annotate(total=Sum('saldo')).order_by('categoria')

        # 2. Aging Report - Contas a Pagar (saldo em aberto, não o valor cheio)
        contas_a_pagar_aging = self.scope_qs(ContaPagar.objects.all()).filter(
            status__in=status_em_aberto,
            **filtro_empreendimento
        ).annotate(
            categoria=Case(
                When(data_vencimento__lt=today - timedelta(days=90), then=Value('> 90 dias')),
                When(data_vencimento__lt=today - timedelta(days=60), then=Value('61-90 dias')),
                When(data_vencimento__lt=today - timedelta(days=30), then=Value('31-60 dias')),
                When(data_vencimento__lt=today, then=Value('1-30 dias Atrasado')),
                When(data_vencimento=today, then=Value('Vence Hoje')),
                default=Value('A Vencer'),
                output_field=CharField(),
            ),
            saldo=F('valor') + F('juros') + F('multa') - F('desconto') - F('valor_pago'),
        ).values('categoria').annotate(total=Sum('saldo')).order_by('categoria')

        # 3. Annual Cash Flow (last 12 months, grouped by month, from transactions)
        fluxo_mensal = (
            self.scope_qs(Transacao.objects.all())
            .filter(
                data_transacao__date__gte=one_year_ago,
                data_transacao__date__lte=today,
                **filtro_empreendimento
            )
            .annotate(mes=TruncMonth('data_transacao'))
            .values('mes')
            .annotate(
                receitas=Sum(Case(When(tipo='ENTRADA', then='valor'), default=0, output_field=DecimalField())),
                despesas=Sum(Case(When(tipo='SAIDA', then='valor'), default=0, output_field=DecimalField()))
            )
            .order_by('mes')
        )

        # Prepare data for the serializer
        dashboard_data = {
            'agingContasAReceber': list(contas_a_receber_aging),
            'agingContasAPagar': list(contas_a_pagar_aging),
            'fluxoDeCaixaMensal': list(fluxo_mensal),
        }

        return Response(dashboard_data)

class NotaFiscalViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar notas fiscais.
    """
    queryset = NotaFiscal.objects.all()
    serializer_class = NotaFiscalSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.nf"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ['empreendimento', 'fornecedor']
    search_fields = ['numero_nota', 'chave_acesso']
    ordering_fields = ['data_emissao', 'valor_total']
    ordering = ['-data_emissao']

class ContaPagarViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar contas a pagar.
    """
    queryset = ContaPagar.objects.all()
    serializer_class = ContaPagarSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.conta_pagar"   # CRUD: GET→.view · escrita→.edit
    action_permission_map = {               # verbos de domínio (@action)
        "dar_baixa": "erp.conta_pagar.baixar",
        "gerar_lote_remessa": "erp.lote_remessa.create",
    }
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_class = ContaPagarFilter
    search_fields = ['descricao']
    ordering_fields = ['data_vencimento', 'valor', 'status']
    ordering = ['-data_vencimento']

    def get_queryset(self):
        return super().get_queryset().select_related(
            'fornecedor', 'empreendimento', 'nota_fiscal'
        ).prefetch_related('rateios__centro_custo', 'boletos')

    @action(detail=True, methods=['post'], url_path='dar-baixa')
    def dar_baixa(self, request, pk=None):
        """
        Baixa manual (total ou parcial) de uma conta a pagar.

        Único caminho de baixa — delega a `ContaPagar.dar_baixa`, o mesmo
        método que a futura baixa automática via webhook do Asaas (D.1.2)
        usará com `origem='asaas'`, garantindo consistência entre os dois.
        """
        conta = self.get_object()
        serializer = BaixaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        try:
            conta.dar_baixa(
                valor=dados['valor'],
                data=dados['data'],
                juros=dados['juros'],
                multa=dados['multa'],
                desconto=dados['desconto'],
                meio_pagamento=dados['meio_pagamento'],
                usuario=request.user,
                origem='manual',
            )
        except BaixaRequerRevisao as exc:
            return Response(
                {
                    'detail': 'Título já estava quitado/cancelado — baixa encaminhada para revisão do financeiro.',
                    'revisao': RevisaoBaixaSerializer(exc.revisao).data,
                },
                status=status_module.HTTP_202_ACCEPTED,
            )
        return Response(ContaPagarSerializer(conta).data)

    @action(detail=False, methods=['post'], url_path='gerar-lote-remessa')
    def gerar_lote_remessa(self, request):
        """
        Registra um lote de remessa bancária agrupando títulos selecionados.

        Só entram títulos **elegíveis** (L9): em aberto/parcial (nunca quitados
        ou cancelados) e ainda não vinculados a um lote ativo; o `valor_total`
        soma o **saldo em aberto**, não o valor cheio (um título parcialmente
        pago remete só o que falta). Títulos descartados voltam em `ignorados`
        para o financeiro conferir, em vez de inflarem o lote silenciosamente.

        Apenas o registro do lote (status/valor_total/vínculo M2M) — a geração
        do arquivo CNAB em si fica para uma sub-fase futura (ver docstring de
        models.LoteRemessa e docs/modulos/moduloerp.md §13/§15).
        """
        conta_ids = request.data.get('conta_pagar_ids', [])
        if not conta_ids:
            return Response({'error': 'Lista de conta_pagar_ids é obrigatória.'}, status=status_module.HTTP_400_BAD_REQUEST)

        # Elegíveis: em aberto/parcial e fora de qualquer lote ainda ativo
        # (GERADO/ENVIADO/PROCESSADO — um lote CANCELADO libera seus títulos).
        contas = self.get_queryset().filter(
            conta_pagar_id__in=conta_ids,
            status__in=[StatusConta.ABERTO, StatusConta.PARCIAL],
        ).exclude(
            lotes_remessa__status__in=[
                LoteRemessa.StatusLote.GERADO,
                LoteRemessa.StatusLote.ENVIADO,
                LoteRemessa.StatusLote.PROCESSADO,
            ],
        ).distinct()
        if not contas.exists():
            return Response(
                {'error': 'Nenhum título elegível: quitados/cancelados ou já em um lote ativo são ignorados.'},
                status=status_module.HTTP_400_BAD_REQUEST,
            )

        # Saldo em aberto (não o valor cheio): título parcial remete só o que falta.
        saldo_aberto = F('valor') + F('juros') + F('multa') - F('desconto') - F('valor_pago')
        valor_total = contas.aggregate(
            total=Sum(saldo_aberto, output_field=DecimalField(max_digits=15, decimal_places=2)),
        )['total'] or Decimal('0')

        # Materializa os elegíveis ANTES do `set()`: vincular ao lote (GERADO) faz o
        # próprio queryset `contas` (que exclui títulos em lote ativo) voltar vazio.
        elegiveis_ids = list(contas.values_list('conta_pagar_id', flat=True))

        lote = LoteRemessa.objects.create(
            tenant_id=getattr(request.user, 'tenant_id', None),
            banco=request.data.get('banco', ''),
            observacoes=request.data.get('observacoes', ''),
            valor_total=valor_total,
        )
        lote.contas_pagar.set(elegiveis_ids)

        elegiveis = {str(cid) for cid in elegiveis_ids}
        data = LoteRemessaSerializer(lote).data
        data['ignorados'] = [cid for cid in conta_ids if str(cid) not in elegiveis]
        return Response(data, status=status_module.HTTP_201_CREATED)


class ContaReceberViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar contas a receber.
    """
    queryset = ContaReceber.objects.all()
    serializer_class = ContaReceberSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.conta_receber"   # CRUD: GET→.view · escrita→.edit
    action_permission_map = {                 # verbos de domínio: baixa, cobrança, NF
        "dar_baixa": "erp.conta_receber.baixar",
        "gerar_cobranca": "erp.cobranca.emitir",
        "emitir_nota_fiscal_servico": "erp.nf.emitir",
        "emitir_nota_fiscal_produto": "erp.nf.emitir",
        "emitir_lote_nfse": "erp.nf.emitir",
    }
    # Ações que consomem cota de TERCEIRO (Asaas, NFE.io) e produzem efeito com
    # custo real — boleto emitido, nota fiscal emitida. Ganham um teto próprio,
    # bem menor que o do usuário: repetição em laço aqui não é só carga na nossa
    # API, é fatura de terceiro e documento fiscal indevido.
    ACOES_INTEGRACAO_EXTERNA = {
        "gerar_cobranca",
        "emitir_nota_fiscal_servico",
        "emitir_nota_fiscal_produto",
        "emitir_lote_nfse",
    }

    def get_throttles(self):
        # `throttle_scope` é lido do VIEW pelo ScopedRateThrottle, e um ViewSet tem
        # uma ação por requisição — então o escopo é definido aqui, por ação, em vez
        # de um atributo fixo que valeria para o CRUD inteiro.
        if getattr(self, "action", None) in self.ACOES_INTEGRACAO_EXTERNA:
            self.throttle_scope = "integracao_externa"
        return super().get_throttles()
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_class = ContaReceberFilter
    search_fields = ['descricao']
    ordering_fields = ['data_vencimento', 'valor', 'status']
    ordering = ['-data_vencimento']

    def get_queryset(self):
        return super().get_queryset().select_related(
            'cliente', 'empreendimento',
            'nota_fiscal_recebida', 'nota_fiscal_servico', 'nota_fiscal_produto',
        ).prefetch_related('rateios__centro_custo', 'boletos')

    @action(detail=True, methods=['post'], url_path='dar-baixa')
    def dar_baixa(self, request, pk=None):
        """
        Baixa manual (total ou parcial) de uma conta a receber.

        Espelha `ContaPagarViewSet.dar_baixa` — delega a `ContaReceber.dar_baixa`,
        o mesmo caminho que a baixa automática via webhook do Asaas (D.1.2)
        usará com `origem='asaas'`.
        """
        conta = self.get_object()
        serializer = BaixaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        try:
            conta.dar_baixa(
                valor=dados['valor'],
                data=dados['data'],
                juros=dados['juros'],
                multa=dados['multa'],
                desconto=dados['desconto'],
                meio_pagamento=dados['meio_pagamento'],
                usuario=request.user,
                origem='manual',
            )
        except BaixaRequerRevisao as exc:
            return Response(
                {
                    'detail': 'Título já estava quitado/cancelado — baixa encaminhada para revisão do financeiro.',
                    'revisao': RevisaoBaixaSerializer(exc.revisao).data,
                },
                status=status_module.HTTP_202_ACCEPTED,
            )
        return Response(ContaReceberSerializer(conta).data)

    @action(detail=True, methods=['post'], url_path='gerar-cobranca')
    def gerar_cobranca(self, request, pk=None):
        """
        Aciona a geração da cobrança no Asaas (boleto/PIX/cartão) para esta
        conta a receber: garante o `customer`, cria o `payment` e grava o
        `Boleto` (status `EMITIDO`, `gateway_id`/`url_pdf`/`linha_digitavel`).

        Processado pela Celery task `funcoescobrancas.tasks.criar_cobranca`
        (D.1.2 — em dev roda in-process via `CELERY_TASK_ALWAYS_EAGER`). A
        baixa, quando o cliente pagar, chega pelo webhook (`origem='asaas'`),
        passando pelo mesmo `dar_baixa`/guard `RevisaoBaixa` da baixa manual.
        """
        conta = self.get_object()
        if conta.status in (StatusConta.QUITADO, StatusConta.CANCELADO):
            return Response(
                {'detail': 'Conta já quitada/cancelada — não é possível gerar cobrança.'},
                status=status_module.HTTP_400_BAD_REQUEST,
            )

        # Trava de identidade ANTES de enfileirar: nome + CPF/CNPJ do cliente
        # têm de bater com o cadastro no gateway. Devolve mensagem clara ao
        # usuário e impede boleto no cliente errado (ver funcoescobrancas).
        try:
            validar_cliente_para_cobranca(conta.cliente)
        except CobrancaBloqueada as exc:
            return Response(
                {'detail': exc.mensagem, 'code': exc.code, **exc.contexto},
                status=status_module.HTTP_409_CONFLICT,
            )
        except AsaasAPIError as exc:
            logger.warning("Não foi possível validar cliente no Asaas p/ ContaReceber #%s: %s",
                           conta.conta_receber_id, exc)
            return Response(
                {'detail': 'Não foi possível validar o cliente no gateway de cobrança agora. '
                           'Nenhum boleto foi emitido — tente novamente em instantes.'},
                status=status_module.HTTP_502_BAD_GATEWAY,
            )

        try:
            criar_cobranca.delay(conta.conta_receber_id)
        except Exception as e:
            logger.error(f"Erro ao acionar geração de cobrança Asaas para a conta #{conta.conta_receber_id}: {e}")
            return Response(
                {'detail': f'Erro ao gerar cobrança no Asaas: {e}'},
                status=status_module.HTTP_502_BAD_GATEWAY,
            )
        # Auditoria (Fase 9.E): cobrança enfileirada com sucesso.
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="gerar_cobranca", instance=conta, usuario=getattr(request, "user", None),
            detalhes={"conta_receber_id": conta.conta_receber_id},
        )
        return Response(
            {'detail': 'Geração de cobrança Asaas iniciada — o boleto/PIX aparece em "Boletos" assim que o gateway confirmar.'},
            status=status_module.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['post'], url_path='emitir-nfse')
    def emitir_nota_fiscal_servico(self, request, pk=None):
        """ Aciona a emissão de uma NFS-e para esta conta a receber. """
        conta = self.get_object()
        return _emitir_nf_para_conta_receber(request, conta, 'servico')

    @action(detail=True, methods=['post'], url_path='emitir-nfe')
    def emitir_nota_fiscal_produto(self, request, pk=None):
        """ Aciona a emissão de uma NF-e (produto) para esta conta a receber. """
        conta = self.get_object()
        return _emitir_nf_para_conta_receber(request, conta, 'produto')

    @action(detail=False, methods=['post'], url_path='emitir-lote-nfse')
    def emitir_lote_nfse(self, request):
        """ Emite NFS-e em lote para múltiplas contas a receber. """
        try:
            conta_ids = request.data.get('conta_receber_ids', [])
            city_service_code = request.data.get('city_service_code', '010701')
            descricao = request.data.get('descricao', None)

            if not conta_ids:
                return Response({'error': 'Lista de conta_receber_ids é obrigatória'}, status=status_module.HTTP_400_BAD_REQUEST)

            resultados = []
            sucessos = 0
            erros = 0

            for conta_id in conta_ids:
                try:
                    conta = self.get_queryset().get(conta_receber_id=conta_id)

                    individual_request = type('Request', (), {
                        'data': {
                            'city_service_code': city_service_code,
                            'descricao': descricao
                        }
                    })()

                    response = _emitir_nf_para_conta_receber(individual_request, conta, 'servico')

                    if response.status_code in [201, 202]:
                        sucessos += 1
                        resultados.append({
                            'conta_receber_id': conta_id,
                            'status': 'sucesso',
                            'message': f'NFS-e iniciada para conta a receber #{conta_id}'
                        })
                    else:
                        erros += 1
                        resultados.append({
                            'conta_receber_id': conta_id,
                            'status': 'erro',
                            'message': response.data.get('error', 'Erro desconhecido')
                        })

                except ContaReceber.DoesNotExist:
                    erros += 1
                    resultados.append({
                        'conta_receber_id': conta_id,
                        'status': 'erro',
                        'message': 'Conta a receber não encontrada'
                    })
                except Exception as e:
                    erros += 1
                    resultados.append({
                        'conta_receber_id': conta_id,
                        'status': 'erro',
                        'message': str(e)
                    })

            return Response({
                'message': f'Lote processado: {sucessos} sucessos, {erros} erros',
                'sucessos': sucessos,
                'erros': erros,
                'resultados': resultados
            }, status=status_module.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Erro ao processar lote de NFS-e: {e}")
            return Response({'error': f'Erro interno: {str(e)}'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)


class CentroCustoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar centros de custo (rateio).
    """
    queryset = CentroCusto.objects.all()
    serializer_class = CentroCustoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.centro_custo"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ['empreendimento', 'ativo']
    search_fields = ['nome', 'codigo']
    ordering_fields = ['nome', 'codigo']
    ordering = ['nome']


class RevisaoBaixaViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Fila de revisão do financeiro: baixas tentadas em títulos já QUITADOS/
    CANCELADOS (ver `BaixaRequerRevisao`). Somente leitura + ações `aprovar`/
    `rejeitar` — a decisão nunca acontece por escrita direta nos campos.
    """
    queryset = RevisaoBaixa.objects.all()
    serializer_class = RevisaoBaixaSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.revisao_baixa"   # ReadOnly: GET→.view
    action_permission_map = {                 # aprovar/rejeitar = resolver
        "aprovar": "erp.revisao_baixa.resolver",
        "rejeitar": "erp.revisao_baixa.resolver",
    }
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'origem']
    ordering_fields = ['solicitado_em']
    ordering = ['-solicitado_em']

    def get_queryset(self):
        return super().get_queryset().select_related(
            'conta_pagar', 'conta_receber', 'solicitado_por', 'revisado_por'
        )

    def _avaliar(self, request, metodo):
        revisao = self.get_object()
        if revisao.status != StatusRevisaoBaixa.PENDENTE:
            return Response(
                {'error': 'Esta revisão já foi avaliada e não pode ser reavaliada.'},
                status=status_module.HTTP_400_BAD_REQUEST,
            )
        getattr(revisao, metodo)(usuario=request.user, observacao=request.data.get('observacao', ''))
        return Response(RevisaoBaixaSerializer(revisao).data)

    @action(detail=True, methods=['post'])
    def aprovar(self, request, pk=None):
        """ Aplica a baixa represada ao título (bypassa o guard) e marca a revisão como aprovada. """
        return self._avaliar(request, 'aprovar')

    @action(detail=True, methods=['post'])
    def rejeitar(self, request, pk=None):
        """ Marca a revisão como rejeitada — a baixa tentada não é aplicada ao título. """
        return self._avaliar(request, 'rejeitar')


class LoteRemessaViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar lotes de remessa bancária.

    A criação "rica" (selecionar títulos + calcular valor_total) acontece via
    `ContaPagarViewSet.gerar_lote_remessa` — este ViewSet cobre list/detail/
    atualização de status/cancelamento.
    """
    queryset = LoteRemessa.objects.all()
    serializer_class = LoteRemessaSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    # Catálogo tem só view+create (sem edit) → mapa explícito; a gestão de status
    # do lote reusa `.create` como verbo de "gerir" (mesmo padrão do CRM interação).
    permission_map = {"view": "erp.lote_remessa.view", "write": "erp.lote_remessa.create"}
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'banco']
    ordering_fields = ['data_geracao', 'valor_total']
    ordering = ['-data_geracao']

class CobrancaClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar cobranças de clientes.
    """
    queryset = CobrancaCliente.objects.all()
    serializer_class = CobrancaClienteSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.cobranca"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = CobrancaClienteFilter
    ordering_fields = ['data_vencimento', 'valor_nominal', 'status']
    ordering = ['-data_vencimento']

class BoletoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar boletos.
    """
    queryset = Boleto.objects.all()
    serializer_class = BoletoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.cobranca"   # boleto é o instrumento da cobrança
    action_permission_map = {"cancelar": "erp.cobranca.emitir"}   # cancelar = gerir a cobrança
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BoletoFilter
    ordering_fields = ['data_vencimento', 'valor', 'status']
    ordering = ['-data_vencimento']

    @action(detail=True, methods=['get'], url_path='documento')
    def documento(self, request, pk=None):
        """
        Verifica o boleto AO VIVO no Asaas e devolve o status + URL atuais. Se o
        Asaas estiver fora do ar, devolve a última versão local e avisa. GET →
        exige apenas `erp.cobranca.view`.
        """
        boleto = self.get_object()
        return Response(verificar_cobranca_asaas(boleto))

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        """
        Cancela o boleto no Asaas (`cancelar_payment`) e marca-o como CANCELADO
        com a data/retorno do gateway. Boleto já pago não é cancelável aqui.
        """
        boleto = self.get_object()
        if boleto.status == Boleto.StatusBoleto.CANCELADO:
            return Response({'detail': 'Boleto já está cancelado.', 'boleto': BoletoSerializer(boleto).data})
        if boleto.status == Boleto.StatusBoleto.PAGO:
            return Response(
                {'detail': 'Não é possível cancelar um boleto já pago — use estorno.'},
                status=status_module.HTTP_400_BAD_REQUEST,
            )
        try:
            cancelar_cobranca_asaas(boleto)
        except AsaasAPIError as exc:
            logger.warning("Asaas recusou o cancelamento do boleto #%s: %s", boleto.boleto_id, exc)
            return Response(
                {'detail': f'O Asaas não conseguiu cancelar o boleto agora: {exc}'},
                status=status_module.HTTP_502_BAD_GATEWAY,
            )
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="cancelar_boleto", instance=boleto, usuario=getattr(request, "user", None),
            detalhes={"boleto_id": boleto.boleto_id, "gateway_id": boleto.gateway_id},
        )
        return Response({'detail': 'Boleto cancelado no Asaas.', 'boleto': BoletoSerializer(boleto).data})


class AtualizarStatusNFView(TenantScopedAPIViewMixin, views.APIView):
    """
    Atualização manual do status de uma NF (escopada ao tenant do usuário).

    Antes era o callback do microsserviço Node `funcoesnf`; com a absorção
    (Fase 11.1) a Celery task grava o status direto, e este endpoint fica como
    correção manual pelo financeiro (exige `erp.nf.edit`).
    """
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.nf"   # grava status da NF → POST exige erp.nf.edit

    def post(self, request, *args, **kwargs):
        nf_id = request.data.get('nf_id')
        nf_tipo = request.data.get('nf_tipo')  # 'servico' ou 'produto'
        status = request.data.get('status')
        dados_retorno = request.data.get('dados_retorno', {})

        if not all([nf_id, nf_tipo, status]):
            return Response(
                {'error': 'Campos obrigatórios: nf_id, nf_tipo, status'},
                status=status_module.HTTP_400_BAD_REQUEST
            )

        # L8: só aceita status do vocabulário (não gravar valor arbitrário).
        if status not in StatusNFE.values:
            return Response(
                {'error': f'status inválido: {status}. Válidos: {", ".join(StatusNFE.values)}'},
                status=status_module.HTTP_400_BAD_REQUEST
            )

        try:
            # Determinar qual modelo usar
            if nf_tipo == 'servico':
                nf_model = NotaFiscalServico
            elif nf_tipo == 'produto':
                nf_model = NotaFiscalProduto
            else:
                return Response(
                    {'error': 'nf_tipo deve ser "servico" ou "produto"'},
                    status=status_module.HTTP_400_BAD_REQUEST
                )
            
            # Buscar e atualizar a NF (escopada ao tenant do usuário — S1)
            nf = self.scope_qs(nf_model.objects.all()).get(id=nf_id)
            nf.status = status
            
            # Atualizar campos específicos se disponíveis nos dados de retorno
            if dados_retorno:
                if 'id' in dados_retorno:
                    nf.nfe_io_id = dados_retorno['id']
                if 'numero' in dados_retorno:
                    nf.numero = dados_retorno['numero']
                if 'chaveAcesso' in dados_retorno:
                    nf.chave_acesso = dados_retorno['chaveAcesso']
                if 'fullResponse' in dados_retorno:
                    nf.dados_retorno_api = dados_retorno['fullResponse']
            
            nf.save()
            
            logger.info(f"Status da {nf_tipo.upper()} ID {nf_id} atualizado para {status}")
            
            return Response({'message': 'Status atualizado com sucesso'})
            
        except nf_model.DoesNotExist:
            return Response(
                {'error': f'Nota Fiscal de {nf_tipo} com ID {nf_id} não encontrada'},
                status=status_module.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Erro ao atualizar status da NF {nf_id}: {e}")
            return Response(
                {'error': f'Erro interno: {str(e)}'},
                status=status_module.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ConsultarStatusNFView(TenantScopedAPIViewMixin, views.APIView):
    """
    Dispara a consulta assíncrona do status de uma NFS-e na NFE.io.

    Fase 11.1: em vez de chamar o microsserviço Node (`localhost:3003`),
    enfileira a Celery task `consultar_nota_fiscal_servico`, que atualiza a NF
    quando a NFE.io responder.
    """
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    # Consulta = leitura (não grava NF localmente, só agenda o refresh via task);
    # apesar do POST, exige apenas erp.nf.view — não .edit.
    required_permission = "erp.nf.view"

    def post(self, request, nf_id):
        try:
            # Escopada ao tenant do usuário (S1) antes de agendar a consulta.
            nf = self.scope_qs(NotaFiscalServico.objects.all()).get(pk=nf_id)

            if not nf.nfe_io_id:
                return Response({'error': 'Esta NF não possui um ID externo (nfe_io_id) para consulta.'}, status=status_module.HTTP_400_BAD_REQUEST)

            consultar_nota_fiscal_servico.delay(nf.id)
            return Response({'message': 'Consulta de status agendada — a NF é atualizada quando a NFE.io responder.'},
                            status=status_module.HTTP_202_ACCEPTED)

        except NotaFiscalServico.DoesNotExist:
            return Response({'error': 'Nota Fiscal de Serviço não encontrada.'}, status=status_module.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erro inesperado ao consultar status da NF {nf_id}: {e}")
            return Response({'error': 'Erro interno do servidor.'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)