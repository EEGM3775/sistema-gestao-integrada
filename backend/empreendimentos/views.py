# backend/empreendimentos/views.py
from rest_framework import viewsets, permissions
from .models import (
    Empreendimento,
    ContaBancariaEmpreendimento,
    CustoEmpreendimento
)
from .serializers import (
    EmpreendimentoSerializer,
    ContaBancariaEmpreendimentoSerializer,
    CustoEmpreendimentoSerializer
)

class EmpreendimentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que empreendimentos sejam visualizados ou editados.
    """
    queryset = Empreendimento.objects.all().order_by('empreendimento')
    serializer_class = EmpreendimentoSerializer
    # permission_classes = [permissions.IsAuthenticated]

class ContaBancariaEmpreendimentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que contas bancárias de empreendimentos sejam visualizadas ou editadas.
    """
    queryset = ContaBancariaEmpreendimento.objects.all()
    serializer_class = ContaBancariaEmpreendimentoSerializer
    # permission_classes = [permissions.IsAuthenticated]

class CustoEmpreendimentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite que custos de empreendimentos sejam visualizados ou editados.
    """
    queryset = CustoEmpreendimento.objects.all()
    serializer_class = CustoEmpreendimentoSerializer
    # permission_classes = [permissions.IsAuthenticated]
