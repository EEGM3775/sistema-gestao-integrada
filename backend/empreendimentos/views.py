# backend/empreendimentos/views.py
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from nucleo.quotas import QuotaEnforcedMixin
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Empreendimento, ContaBancariaEmpreendimento, CustoEmpreendimento, Unidade
from .serializers import (
    EmpreendimentoSerializer, ContaBancariaEmpreendimentoSerializer,
    CustoEmpreendimentoSerializer, UnidadeSerializer,
)
from obras.models import Obra
from django.db.models import Count, F, Q

class EmpreendimentoViewSet(QuotaEnforcedMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Empreendimento.objects.all()
    serializer_class = EmpreendimentoSerializer
    permission_classes = [IsAuthenticated, RequirePermission]
    required_resource = "obra.empreendimento"
    quota_recurso = "empreendimentos"  # D24
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['empreendimento', 'razao_social', 'cnpj']

    def get_queryset(self):
        # Contagem de unidades no próprio SELECT: a Visão Geral mostra "38
        # unidades · 12 vendidas" sem uma segunda chamada por empreendimento (que
        # na listagem seriam N+1 requisições).
        return super().get_queryset().annotate(
            unidades_total=Count('unidades', distinct=True),
            unidades_disponiveis=Count(
                'unidades', filter=Q(unidades__situacao='disponivel'), distinct=True,
            ),
            unidades_vendidas=Count(
                'unidades', filter=Q(unidades__situacao='vendida'), distinct=True,
            ),
        )

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
    permission_classes = [IsAuthenticated, RequirePermission]
    required_resource = "obra.empreend_conta"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['empreendimento']

class UnidadePagination(PageNumberPagination):
    """Um loteamento tem milhares de lotes; a aba Unidades rola infinito e pede
    de página em página, como a carteira de clientes."""
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 300


class UnidadeViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As unidades à venda — cadastro do empreendimento, não da venda.

    Mesma permissão do empreendimento (`obra.empreendimento`): a unidade é parte
    do cadastro dele, e criar uma permissão nova exigiria rebuild e re-seed da
    IAM sem ganho de separação real — quem cadastra o empreendimento cadastra o
    que ele vende.

    A ordenação padrão é a do endereço (quadra › lote › bloco › andar › apto),
    a mesma da carteira: é como quem trabalha com o mapa do loteamento lê.
    """
    queryset = Unidade.objects.select_related('empreendimento').prefetch_related('aquisicoes__cliente')
    serializer_class = UnidadeSerializer
    permission_classes = [IsAuthenticated, RequirePermission]
    required_resource = "obra.empreendimento"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['empreendimento', 'situacao', 'tipo', 'quadra', 'bloco_torre']
    search_fields = ['quadra', 'lote', 'bloco_torre', 'andar', 'apto', 'endereco']
    ordering_fields = ['valor_base', 'situacao', 'tipo', 'area_privativa', 'data_criacao']
    pagination_class = UnidadePagination

    def get_queryset(self):
        qs = super().get_queryset()
        # Ordem natural do endereço: os campos são texto ("Quadra A", "Lote 12-B"),
        # então "10" viria antes de "2" na ordem alfabética. Mesma chave da
        # carteira (clientes/carteira.py) para as duas telas não discordarem.
        if not self.request.query_params.get('ordering'):
            qs = ordenar_por_endereco(qs)
        return qs

    def destroy(self, request, *args, **kwargs):
        unidade = self.get_object()
        if unidade.aquisicoes.exists():
            return Response(
                {'detail': 'Unidade vendida não pode ser excluída. Cancele a aquisição primeiro.'},
                status=409,
            )
        return super().destroy(request, *args, **kwargs)


def ordenar_por_endereco(qs):
    """Quadra › lote › bloco › andar › apto, numérica e com vazio por último."""
    from clientes.carteira import chave_natural  # mesma régua, um lugar só

    return qs.annotate(
        _q=chave_natural('quadra'), _l=chave_natural('lote'), _b=chave_natural('bloco_torre'),
        _a=chave_natural('andar'), _u=chave_natural('apto'),
    ).order_by(
        F('_q').asc(nulls_last=True), F('_l').asc(nulls_last=True), F('_b').asc(nulls_last=True),
        F('_a').asc(nulls_last=True), F('_u').asc(nulls_last=True), 'pk',
    )


class CustoEmpreendimentoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CustoEmpreendimento.objects.all()
    serializer_class = CustoEmpreendimentoSerializer
    permission_classes = [IsAuthenticated, RequirePermission]
    required_resource = "obra.empreend_custo"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['empreendimento']
    search_fields = ['descricao', 'nota_fiscal']

