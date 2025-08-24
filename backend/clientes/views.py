# backend/clientes/views.py
from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
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

class ClienteViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que clientes sejam visualizados ou editados.
    """
    queryset = Cliente.objects.all().order_by('nome_completo')
    serializer_class = ClienteSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['estado_civil', 'profissao', 'cidade', 'estado']
    search_fields = ['nome_completo', 'cpf_cnpj', 'email', 'telefone', 'endereco', 'bairro', 'cidade', 'cep']
    ordering_fields = ['nome_completo', 'data_cadastro', 'cidade', 'estado']
    ordering = ['nome_completo']
    # permission_classes = [permissions.IsAuthenticated] # Exemplo de permissão

class ClienteEmpreendimentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que os vínculos entre clientes e empreendimentos sejam visualizados ou editados.
    """
    queryset = ClienteEmpreendimento.objects.all()
    serializer_class = ClienteEmpreendimentoSerializer
    # permission_classes = [permissions.IsAuthenticated]

class ContratoClienteViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que contratos de clientes sejam visualizados ou editados.
    """
    queryset = ContratoCliente.objects.all()
    serializer_class = ContratoClienteSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DocumentoClienteViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que documentos de clientes sejam visualizados ou editados.
    """
    queryset = DocumentoCliente.objects.all()
    serializer_class = DocumentoClienteSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DadoBancarioClienteViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que dados bancários de clientes sejam visualizados ou editados.
    """
    queryset = DadoBancarioCliente.objects.all()
    serializer_class = DadoBancarioClienteSerializer
    # permission_classes = [permissions.IsAuthenticated]
