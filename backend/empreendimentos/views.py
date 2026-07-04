# backend/empreendimentos/views.py
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin
from rest_framework.response import Response
from .models import Empreendimento, ContaBancariaEmpreendimento, CustoEmpreendimento
from .serializers import EmpreendimentoSerializer, ContaBancariaEmpreendimentoSerializer, CustoEmpreendimentoSerializer
from obras.models import Obra
from django.db.models import Q

class EmpreendimentoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Empreendimento.objects.all()
    serializer_class = EmpreendimentoSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['empreendimento', 'razao_social', 'cnpj']

    @action(detail=False, methods=['get'], url_path='por-funcionario')
    def por_funcionario(self, request):
        funcionario_id = request.query_params.get('funcionario_id')
        if not funcionario_id or funcionario_id == 'undefined':
            return Response({'error': 'O parâmetro funcionario_id é obrigatório e deve ser um ID válido'}, status=400)

        obras_do_funcionario = Obra.objects.filter(responsaveis_tecnicos=funcionario_id)
        empreendimento_ids = obras_do_funcionario.values_list('empreendimento_id', flat=True).distinct()
        empreendimentos = self.get_queryset().filter(pk__in=empreendimento_ids)

        serializer = self.get_serializer(empreendimentos, many=True)
        return Response(serializer.data)

class ContaBancariaEmpreendimentoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContaBancariaEmpreendimento.objects.all()
    serializer_class = ContaBancariaEmpreendimentoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['empreendimento']

class CustoEmpreendimentoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CustoEmpreendimento.objects.all()
    serializer_class = CustoEmpreendimentoSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['empreendimento']
    search_fields = ['descricao', 'nota_fiscal']

