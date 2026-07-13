# backend/clientes/views.py
from rest_framework import viewsets, permissions, filters, status as drf_status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from nucleo.field_masking import mask_document_unless
from funcoescobrancas.services import analisar_divergencias_asaas
from funcoescobrancas.client import AsaasAPIError
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente
)
from .serializers import (
    ClienteSerializer,
    ClienteEmpreendimentoSerializer,
    ContratoClienteSerializer,
    DocumentoClienteSerializer,
    DadoBancarioClienteSerializer
)
from .filters import (
    ClienteFilter,
    ClienteEmpreendimentoFilter,
    ContratoClienteFilter,
    DocumentoClienteFilter,
)


class ClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Cliente.objects.all().order_by('nome_completo')
    serializer_class = ClienteSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ClienteFilter
    search_fields = ['nome_completo', 'cpf_cnpj', 'email', 'telefone', 'bairro', 'cidade', 'cep']
    ordering_fields = ['nome_completo', 'data_cadastro', 'cidade', 'estado']
    ordering = ['nome_completo']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"  # GET→.view · escrita→.edit

    @action(detail=False, methods=['get'], url_path='divergencias-asaas')
    def divergencias_asaas(self, request):
        """
        Relatório (só leitura) das divergências de identidade entre os clientes
        deste tenant e os customers do Asaas — o mesmo critério que barra a
        emissão de cobrança. Consumido ao abrir "Novo Cliente" e ao gerar
        cobrança (D3), para ver o que impediria/desviaria um boleto.

        **LGPD:** o relatório expõe CPF/CNPJ (PII documental) num dict cru, fora
        do `FieldMaskingSerializerMixin`. Quem não tem `cadastro.cliente_doc.view`
        recebe o documento **mascarado** (mesma regra da 9.C) — o nome basta para
        localizar o cadastro a corrigir, sem vazar o documento inteiro.
        """
        try:
            relatorio = analisar_divergencias_asaas(self.get_queryset())
        except AsaasAPIError as exc:
            return Response(
                {'detail': f'Não foi possível consultar o gateway de cobrança (Asaas) agora: {exc}'},
                status=drf_status.HTTP_502_BAD_GATEWAY,
            )
        for d in relatorio.get('divergencias', []):
            d['documento'] = mask_document_unless(request.user, d.get('documento'))
        return Response(relatorio)


class ClienteEmpreendimentoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ClienteEmpreendimento.objects.all().order_by('-data_compra')
    serializer_class = ClienteEmpreendimentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ClienteEmpreendimentoFilter
    ordering_fields = ['data_compra', 'valor_compra']
    ordering = ['-data_compra']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"  # aquisição/venda do cliente


class ContratoClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContratoCliente.objects.all().order_by('-data_assinatura')
    serializer_class = ContratoClienteSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ContratoClienteFilter
    search_fields = ['numero_contrato', 'objeto_contrato']
    ordering_fields = ['data_assinatura', 'numero_contrato', 'status_contrato']
    ordering = ['-data_assinatura']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"


class DocumentoClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DocumentoCliente.objects.all().order_by('-data_upload')
    serializer_class = DocumentoClienteSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = DocumentoClienteFilter
    ordering_fields = ['data_upload', 'tipo_documento']
    ordering = ['-data_upload']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"


class DadoBancarioClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DadoBancarioCliente.objects.all().order_by('cliente')
    serializer_class = DadoBancarioClienteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['cliente']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente_banco"
