# backend/fornecedores/views.py
from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from nucleo.quotas import QuotaEnforcedMixin
from .models import (
    Fornecedor,
    DadoBancarioFornecedor,
    ProdutoServicoFornecedor
)
from .serializers import (
    FornecedorSerializer,
    DadoBancarioFornecedorSerializer,
    ProdutoServicoFornecedorSerializer
)


class FornecedorViewSet(QuotaEnforcedMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    quota_recurso = "fornecedores"  # D24
    queryset = Fornecedor.objects.all().order_by('razao_social')
    serializer_class = FornecedorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['cnpj']
    search_fields = ['razao_social', 'cnpj', 'email', 'contato', 'telefone']
    ordering_fields = ['razao_social']
    ordering = ['razao_social']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.fornecedor"


class DadoBancarioFornecedorViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DadoBancarioFornecedor.objects.all().order_by('fornecedor')
    serializer_class = DadoBancarioFornecedorSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['fornecedor']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.fornecedor_banco"


class ProdutoServicoFornecedorViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ProdutoServicoFornecedor.objects.all().order_by('nome_produto_servico')
    serializer_class = ProdutoServicoFornecedorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['fornecedor', 'tipo_produto_servico']
    search_fields = ['nome_produto_servico', 'descricao']
    ordering_fields = ['nome_produto_servico', 'preco_unitario', 'data_cotacao']
    ordering = ['nome_produto_servico']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.fornecedor"
