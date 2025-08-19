# backend/financeiro/views.py
# Este arquivo define a lógica da API para o app 'financeiro'.
# Cada ViewSet agrupa as operações CRUD (Create, Retrieve, Update, Delete) para um modelo.
from rest_framework import viewsets
from .models import (
    NotaFiscal,
    ContaPagar,
    ContaReceber,
    CobrancaCliente
)
from .serializers import (
    NotaFiscalSerializer,
    ContaPagarSerializer,
    ContaReceberSerializer,
    CobrancaClienteSerializer
)

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
