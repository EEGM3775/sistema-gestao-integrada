# backend/moduloerp/views.py
import logging
import requests
from rest_framework import viewsets, permissions, views, status as status_module
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Case, When, Value, CharField, DecimalField
from django.db.models.functions import TruncMonth
from django.core.files.base import ContentFile
from os.path import basename

from .models import (
    Fatura, Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto
)
from .serializers import (
    FaturaSerializer,
    TransacaoSerializer,
    NotaFiscalServicoSerializer,
    NotaFiscalProdutoSerializer,
    NotaFiscalSerializer,
    ContaPagarSerializer,
    ContaReceberSerializer,
    CobrancaClienteSerializer,
    BoletoSerializer
)

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

# --- ViewSets ---

class FaturaViewSet(viewsets.ModelViewSet):
    queryset = Fatura.objects.all()
    serializer_class = FaturaSerializer
    permission_classes = [permissions.AllowAny]  # Permite acesso sem autenticação para demonstração

    def get_queryset(self):
        """
        Otimiza a consulta de faturas e prepara para segurança a nível de objeto.

        - select_related: Otimiza buscas em relacionamentos ForeignKey (um-para-um).
        - prefetch_related: Otimiza buscas em relacionamentos ManyToMany e reversos.
        """
        # TODO: Implementar filtragem por empreendimento do usuário quando o modelo de dados permitir.
        # Ex: return Fatura.objects.filter(empreendimento__in=self.request.user.empreendimentos.all())
        
        queryset = Fatura.objects.select_related(
            'empreendimento', 
            'cliente', 
            'fornecedor', 
            'nota_fiscal_servico', 
            'nota_fiscal_produto',
            'nota_fiscal_recebida'
        ).prefetch_related('transacoes').order_by('-data_vencimento')
        
        return queryset

    def _emitir_nf(self, request, fatura, tipo_nf):
        try:
            if fatura.tipo != Fatura.TipoFatura.A_RECEBER:
                return Response({'error': 'Notas Fiscais só podem ser emitidas para faturas a receber.'}, status=status_module.HTTP_400_BAD_REQUEST)

            if tipo_nf == 'servico' and fatura.nota_fiscal_servico:
                return Response({'message': 'Nota Fiscal de Serviço já existente para esta fatura.'}, status=status_module.HTTP_400_BAD_REQUEST)
            elif tipo_nf == 'produto' and fatura.nota_fiscal_produto:
                return Response({'message': 'Nota Fiscal de Produto já existente para esta fatura.'}, status=status_module.HTTP_400_BAD_REQUEST)

            # Determine which model and microservice endpoint to use
            if tipo_nf == 'servico':
                nf_model = NotaFiscalServico
                microservice_endpoint = '/api/emitir-nfse'
            else: # produto
                nf_model = NotaFiscalProduto
                microservice_endpoint = '/api/emitir-nfe'

            # Create the NotaFiscal instance with required data
            if tipo_nf == 'servico':
                # Preparar dados do cliente/tomador
                borrower_data = {}
                if fatura.cliente:
                    borrower_data = {
                        'nome': getattr(fatura.cliente, 'nome_completo', '') or getattr(fatura.cliente, 'nome', ''),
                        'cpf_cnpj': getattr(fatura.cliente, 'cpf', '') or getattr(fatura.cliente, 'cnpj', ''),
                        'email': getattr(fatura.cliente, 'email', ''),
                        'endereco': getattr(fatura.cliente, 'endereco', ''),
                    }
                
                # Garantir que sempre há uma descrição válida
                descricao_servico = request.data.get('descricao') or fatura.descricao or 'Prestação de Serviços'
                
                nf = nf_model.objects.create(
                    city_service_code='010701',  # Código padrão - pode ser configurável
                    description=descricao_servico,
                    services_amount=fatura.valor,
                    borrower_data=borrower_data
                )
            else:
                # Para produto - dados básicos
                buyer_data = {}
                if fatura.cliente:
                    buyer_data = {
                        'nome': getattr(fatura.cliente, 'nome_completo', '') or getattr(fatura.cliente, 'nome', ''),
                        'cpf_cnpj': getattr(fatura.cliente, 'cpf', '') or getattr(fatura.cliente, 'cnpj', ''),
                        'email': getattr(fatura.cliente, 'email', ''),
                        'endereco': getattr(fatura.cliente, 'endereco', ''),
                    }
                
                # Garantir que sempre há uma descrição válida
                descricao_produto = request.data.get('descricao') or fatura.descricao or 'Venda de Produtos'
                
                items_data = [{
                    'descricao': descricao_produto,
                    'quantidade': 1,
                    'valor_unitario': float(fatura.valor),
                    'valor_total': float(fatura.valor)
                }]
                
                nf = nf_model.objects.create(
                    buyer_data=buyer_data,
                    items_data=items_data
                )
            
            # Link it to the Fatura
            if tipo_nf == 'servico':
                fatura.nota_fiscal_servico = nf
            else:
                fatura.nota_fiscal_produto = nf
            fatura.save()

            # Trigger the microservice (optional in development)
            microservice_url = f'http://localhost:3002{microservice_endpoint}'
            try:
                response = requests.post(microservice_url, json={'fatura_id': fatura.fatura_id, 'nf_id': nf.id}, timeout=5)
                response.raise_for_status()
                logger.info(f"Microserviço de NF acionado para Fatura ID: {fatura.fatura_id} e NF ID: {nf.id}")
                
                # Se chegou até aqui, o microserviço respondeu com sucesso
                nf.status = 'PROCESSANDO'
                nf.save()
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Microserviço de NF não disponível: {e}. Modo desenvolvimento ativado.")
                
                # Em desenvolvimento, simular o comportamento sem falhar
                nf.status = 'AGUARDANDO'  # Manter status padrão
                nf.save()
                
                # Retornar sucesso mesmo sem o microserviço
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

    @action(detail=True, methods=['post'], url_path='emitir-nfse')
    def emitir_nota_fiscal_servico(self, request, pk=None):
        """ Triggers the issuance of a Service Invoice (NFS-e). """
        fatura = self.get_object()
        return self._emitir_nf(request, fatura, 'servico')

    @action(detail=True, methods=['post'], url_path='emitir-nfe')
    def emitir_nota_fiscal_produto(self, request, pk=None):
        """ Triggers the issuance of a Product Invoice (NF-e). """
        fatura = self.get_object()
        return self._emitir_nf(request, fatura, 'produto')

class TransacaoViewSet(viewsets.ModelViewSet):
    queryset = Transacao.objects.all()
    serializer_class = TransacaoSerializer
    permission_classes = [permissions.IsAuthenticated]

class NotaFiscalServicoViewSet(viewsets.ModelViewSet):
    queryset = NotaFiscalServico.objects.all()
    serializer_class = NotaFiscalServicoSerializer
    permission_classes = [permissions.IsAuthenticated]

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


class NotaFiscalProdutoViewSet(viewsets.ModelViewSet):
    queryset = NotaFiscalProduto.objects.all()
    serializer_class = NotaFiscalProdutoSerializer
    permission_classes = [permissions.IsAuthenticated]

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


class ERPDashboardView(views.APIView):
    """
    Provides aggregated and complex data for the Financial dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        today = timezone.now().date()
        one_year_ago = today - timedelta(days=365)

        # Allow filtering by empreendimento
        empreendimento_id = request.query_params.get('empreendimento_id')
        filtro_empreendimento = {}
        if empreendimento_id:
            filtro_empreendimento['empreendimento_id'] = empreendimento_id

        # 1. Aging Report - Contas a Receber
        contas_a_receber_aging = Fatura.objects.filter(
            tipo=Fatura.TipoFatura.A_RECEBER,
            status__in=[Fatura.StatusFatura.PENDENTE, Fatura.StatusFatura.ATRASADA],
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
            )
        ).values('categoria').annotate(total=Sum('valor')).order_by('categoria')

        # 2. Aging Report - Contas a Pagar
        contas_a_pagar_aging = Fatura.objects.filter(
            tipo=Fatura.TipoFatura.A_PAGAR,
            status__in=[Fatura.StatusFatura.PENDENTE, Fatura.StatusFatura.ATRASADA],
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
            )
        ).values('categoria').annotate(total=Sum('valor')).order_by('categoria')

        # 3. Annual Cash Flow (last 12 months, grouped by month, from transactions)
        fluxo_mensal = (
            Transacao.objects
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

class NotaFiscalViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar notas fiscais.
    """
    queryset = NotaFiscal.objects.all()
    serializer_class = NotaFiscalSerializer
    # permission_classes = [permissions.IsAuthenticated]

class ContaPagarViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar contas a pagar.
    """
    queryset = ContaPagar.objects.all()
    serializer_class = ContaPagarSerializer
    # permission_classes = [permissions.IsAuthenticated]

class ContaReceberViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar contas a receber.
    """
    queryset = ContaReceber.objects.all()
    serializer_class = ContaReceberSerializer
    # permission_classes = [permissions.IsAuthenticated]

class CobrancaClienteViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar cobranças de clientes.
    """
    queryset = CobrancaCliente.objects.all()
    serializer_class = CobrancaClienteSerializer
    # permission_classes = [permissions.IsAuthenticated]

class BoletoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar boletos.
    """
    queryset = Boleto.objects.all()
    serializer_class = BoletoSerializer
    # permission_classes = [permissions.IsAuthenticated]


class AtualizarStatusNFView(views.APIView):
    """
    Endpoint para o microserviço atualizar o status das Notas Fiscais.
    """
    permission_classes = [permissions.AllowAny]  # Permitir acesso do microserviço
    
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
            
            # Buscar e atualizar a NF
            nf = nf_model.objects.get(id=nf_id)
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
