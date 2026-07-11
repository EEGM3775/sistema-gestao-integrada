# backend/moduloerp/views.py
import logging
import requests
from rest_framework import viewsets, permissions, views, filters, status as status_module
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin, TenantScopedAPIViewMixin
from nucleo.permissions import RequireModule, RequireRole
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Case, When, Value, CharField, DecimalField, F
from django.db.models.functions import TruncMonth
from django.core.files.base import ContentFile
from decimal import Decimal
from os.path import basename

from .models import (
    Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto,
    CentroCusto, LoteRemessa, StatusConta, RevisaoBaixa, StatusRevisaoBaixa, BaixaRequerRevisao
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
    CobrancaClienteFilter, BoletoFilter,
)
from .pagination import ErpPageNumberPagination
from funcoescobrancas.tasks import criar_cobranca
from funcoescobrancas.client import AsaasAPIError
from funcoescobrancas.services import validar_cliente_para_cobranca, CobrancaBloqueada

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _registrar_arquivos_nf(nf_instance, url_pdf, url_xml):
    """
    Downloads PDF and XML from URLs and saves them to the NotaFiscal instance.
    """
    try:
        # Download and save PDF
        if url_pdf:
            response_pdf = requests.get(url_pdf, stream=True)
            response_pdf.raise_for_status()
            pdf_name = basename(url_pdf)
            nf_instance.arquivo_pdf.save(pdf_name, ContentFile(response_pdf.content))
            logger.info(f"Arquivo PDF da NF ID {nf_instance.id} salvo: {pdf_name}")

        # Download and save XML
        if url_xml:
            response_xml = requests.get(url_xml, stream=True)
            response_xml.raise_for_status()
            xml_name = basename(url_xml)
            nf_instance.arquivo_xml.save(xml_name, ContentFile(response_xml.content))
            logger.info(f"Arquivo XML da NF ID {nf_instance.id} salvo: {xml_name}")
        
        nf_instance.save()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao baixar arquivos da NF ID {nf_instance.id}: {e}")
        return False


def _dados_cliente_para_nf(cliente):
    """
    Snapshot do tomador/comprador gravado na NF, com os nomes de campo do
    model `Cliente` — contrato consumido pelo funcoesnf (`emitirNF.js` exige
    `cpf_cnpj`, `cep` e `cidade_ibge` para emitir).
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
    """
    try:
        if tipo_nf == 'servico' and conta.nota_fiscal_servico:
            return Response({'message': 'Nota Fiscal de Serviço já existente para esta conta.'}, status=status_module.HTTP_400_BAD_REQUEST)
        elif tipo_nf == 'produto' and conta.nota_fiscal_produto:
            return Response({'message': 'Nota Fiscal de Produto já existente para esta conta.'}, status=status_module.HTTP_400_BAD_REQUEST)

        # Determine which model and microservice endpoint to use
        if tipo_nf == 'servico':
            nf_model = NotaFiscalServico
            microservice_endpoint = '/api/emitir-nfse'
        else:  # produto
            nf_model = NotaFiscalProduto
            microservice_endpoint = '/api/emitir-nfe'

        # Create the NotaFiscal instance with required data
        if tipo_nf == 'servico':
            descricao_servico = request.data.get('descricao') or conta.descricao or 'Prestação de Serviços'

            nf = nf_model.objects.create(
                tenant=conta.tenant,
                city_service_code=request.data.get('city_service_code', '010701'),
                description=descricao_servico,
                services_amount=conta.valor,
                borrower_data=_dados_cliente_para_nf(conta.cliente)
            )
        else:
            descricao_produto = request.data.get('descricao') or conta.descricao or 'Venda de Produtos'

            items_data = [{
                'descricao': descricao_produto,
                'quantidade': 1,
                'valor_unitario': float(conta.valor),
                'valor_total': float(conta.valor)
            }]

            nf = nf_model.objects.create(
                tenant=conta.tenant,
                buyer_data=_dados_cliente_para_nf(conta.cliente),
                items_data=items_data
            )

        # Link it to the ContaReceber
        if tipo_nf == 'servico':
            conta.nota_fiscal_servico = nf
        else:
            conta.nota_fiscal_produto = nf
        conta.save()

        # Auditoria (Fase 9.E): emissão de NF é evento fiscal sensível.
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="emitir_nf", instance=conta, usuario=getattr(request, "user", None),
            detalhes={"tipo_nf": tipo_nf, "nf_id": nf.id, "valor": str(conta.valor)},
        )

        # Trigger the microservice (optional in development)
        microservice_url = f'http://localhost:3003{microservice_endpoint}'
        try:
            microservice_payload = {
                'conta_receber_id': conta.conta_receber_id,
                'nf_id': nf.id
            }

            if tipo_nf == 'servico':
                microservice_payload['city_service_code'] = request.data.get('city_service_code', '010701')

            response = requests.post(microservice_url, json=microservice_payload, timeout=5)
            response.raise_for_status()
            logger.info(f"Microserviço de NF acionado para Conta a Receber ID: {conta.conta_receber_id} e NF ID: {nf.id}")

            nf.status = 'PROCESSANDO'
            nf.save()

        except requests.exceptions.RequestException as e:
            logger.warning(f"Microserviço de NF não disponível: {e}. Modo desenvolvimento ativado.")

            nf.status = 'AGUARDANDO'
            nf.save()

            serializer_class = NotaFiscalServicoSerializer if tipo_nf == 'servico' else NotaFiscalProdutoSerializer
            return Response({
                'message': 'Nota fiscal criada com sucesso. Microserviço de emissão não disponível (modo desenvolvimento).',
                'data': serializer_class(nf).data,
                'warning': 'Microserviço de emissão não está rodando'
            }, status=status_module.HTTP_201_CREATED)

        serializer_class = NotaFiscalServicoSerializer if tipo_nf == 'servico' else NotaFiscalProdutoSerializer
        return Response({'message': 'Processo de emissão iniciado.', 'data': serializer_class(nf).data}, status=status_module.HTTP_202_ACCEPTED)

    except Exception as e:
        logger.error(f"Erro interno ao emitir nota fiscal: {e}")
        return Response({'error': f'Erro interno do servidor: {str(e)}'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)

# --- ViewSets ---

class TransacaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Transacao.objects.all()
    serializer_class = TransacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TransacaoFilter
    search_fields = ['descricao']
    ordering_fields = ['data_transacao', 'valor']
    ordering = ['-data_transacao']

class NotaFiscalServicoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = NotaFiscalServico.objects.all()
    serializer_class = NotaFiscalServicoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
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


class NotaFiscalProdutoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = NotaFiscalProduto.objects.all()
    serializer_class = NotaFiscalProdutoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"

    def get(self, request, *args, **kwargs):
        today = timezone.now().date()
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
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

        Apenas o registro do lote (status/valor_total/vínculo M2M) — a geração
        do arquivo CNAB em si fica para uma sub-fase futura (ver docstring de
        models.LoteRemessa e docs/modulos/moduloerp.md §13/§15).
        """
        conta_ids = request.data.get('conta_pagar_ids', [])
        if not conta_ids:
            return Response({'error': 'Lista de conta_pagar_ids é obrigatória.'}, status=status_module.HTTP_400_BAD_REQUEST)

        contas = self.get_queryset().filter(conta_pagar_id__in=conta_ids)
        if not contas.exists():
            return Response({'error': 'Nenhuma conta válida encontrada para o lote.'}, status=status_module.HTTP_400_BAD_REQUEST)

        valor_total = contas.aggregate(total=Sum('valor'))['total'] or Decimal('0')
        lote = LoteRemessa.objects.create(
            tenant_id=getattr(request.user, 'tenant_id', None),
            banco=request.data.get('banco', ''),
            observacoes=request.data.get('observacoes', ''),
            valor_total=valor_total,
        )
        lote.contas_pagar.set(contas)
        return Response(LoteRemessaSerializer(lote).data, status=status_module.HTTP_201_CREATED)


class ContaReceberViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar contas a receber.
    """
    queryset = ContaReceber.objects.all()
    serializer_class = ContaReceberSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
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
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    pagination_class = ErpPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BoletoFilter
    ordering_fields = ['data_vencimento', 'valor', 'status']
    ordering = ['-data_vencimento']


class AtualizarStatusNFView(TenantScopedAPIViewMixin, views.APIView):
    """
    Endpoint para o microserviço atualizar o status das Notas Fiscais.
    """
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"
    
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
    View para o frontend solicitar a consulta de status de uma NF ao microserviço.
    """
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequireRole]
    required_module = "erp_financeiro"
    required_role = "financeiro"

    def post(self, request, nf_id):
        try:
            # Usamos NotaFiscalServico diretamente, mas poderia ser genérico
            # (escopada ao tenant do usuário — S1)
            nf = self.scope_qs(NotaFiscalServico.objects.all()).get(pk=nf_id)
            
            if not nf.nfe_io_id:
                return Response({'error': 'Esta NF não possui um ID externo (nfe_io_id) para consulta.'}, status=status_module.HTTP_400_BAD_REQUEST)

            # Payload para o microserviço
            payload = {
                'nf_id': nf.id,
                'invoice_id': nf.nfe_io_id
            }
            
            # Chama o microserviço Node.js
            microservice_url = 'http://localhost:3003/api/consultar-nf'
            response = requests.post(microservice_url, json=payload, timeout=10)
            
            if response.status_code == 202:
                return Response({'message': 'Pedido de consulta de status enviado ao microserviço.'}, status=status_module.HTTP_202_ACCEPTED)
            else:
                logger.error(f"Erro ao chamar microserviço para consultar NF {nf_id}. Status: {response.status_code}, Resposta: {response.text}")
                return Response({'error': 'Falha na comunicação com o serviço de notas fiscais.'}, status=status_module.HTTP_502_BAD_GATEWAY)

        except NotaFiscalServico.DoesNotExist:
            return Response({'error': 'Nota Fiscal de Serviço não encontrada.'}, status=status_module.HTTP_404_NOT_FOUND)
        except requests.exceptions.RequestException as e:
            logger.error(f"Não foi possível conectar ao microserviço de NF para consulta da NF {nf_id}: {e}")
            return Response({'error': 'Serviço de notas fiscais indisponível.'}, status=status_module.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error(f"Erro inesperado ao consultar status da NF {nf_id}: {e}")
            return Response({'error': 'Erro interno do servidor.'}, status=status_module.HTTP_500_INTERNAL_SERVER_ERROR)