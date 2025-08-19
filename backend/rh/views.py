# backend/rh/views.py
# Este arquivo define a lógica da API (endpoints) para o app 'rh'.
# Cada ViewSet agrupa as operações CRUD (Create, Retrieve, Update, Delete) para um modelo.
from rest_framework import viewsets
from .models import (
    Cargo,
    Funcionario,
    DadoMedicoFuncionario,
    DocumentoFuncionario,
    DadoBancarioFuncionario,
    PagamentoFuncionario,
    FolhaPagamento
)
from .serializers import (
    CargoSerializer,
    FuncionarioSerializer,
    DadoMedicoFuncionarioSerializer,
    DocumentoFuncionarioSerializer,
    DadoBancarioFuncionarioSerializer,
    PagamentoFuncionarioSerializer,
    FolhaPagamentoSerializer
)

class CargoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar cargos.
    """
    queryset = Cargo.objects.all()
    serializer_class = CargoSerializer
    # permission_classes = [permissions.IsAuthenticated]

class FuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar funcionários.
    """
    queryset = Funcionario.objects.all()
    serializer_class = FuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DadoMedicoFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar dados médicos de funcionários.
    """
    queryset = DadoMedicoFuncionario.objects.all()
    serializer_class = DadoMedicoFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DocumentoFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar documentos de funcionários.
    """
    queryset = DocumentoFuncionario.objects.all()
    serializer_class = DocumentoFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DadoBancarioFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar dados bancários de funcionários.
    """
    queryset = DadoBancarioFuncionario.objects.all()
    serializer_class = DadoBancarioFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class PagamentoFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar pagamentos de funcionários.
    """
    queryset = PagamentoFuncionario.objects.all()
    serializer_class = PagamentoFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class FolhaPagamentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar folhas de pagamento.
    """
    queryset = FolhaPagamento.objects.all()
    serializer_class = FolhaPagamentoSerializer
    # permission_classes = [permissions.IsAuthenticated]
