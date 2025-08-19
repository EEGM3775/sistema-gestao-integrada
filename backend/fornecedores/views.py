# backend/fornecedores/views.py
# Define a lógica da API (endpoints) para o app 'fornecedores'.
from rest_framework import viewsets
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

class FornecedorViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar fornecedores.
    """
    queryset = Fornecedor.objects.all()
    serializer_class = FornecedorSerializer
    # permission_classes = [permissions.IsAuthenticated]


class DadoBancarioFornecedorViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar dados bancários de fornecedores.
    """
    queryset = DadoBancarioFornecedor.objects.all()
    serializer_class = DadoBancarioFornecedorSerializer
    # permission_classes = [permissions.IsAuthenticated]

class ProdutoServicoFornecedorViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar produtos e serviços de fornecedores.
    """
    queryset = ProdutoServicoFornecedor.objects.all()
    serializer_class = ProdutoServicoFornecedorSerializer
    # permission_classes = [permissions.IsAuthenticated]
