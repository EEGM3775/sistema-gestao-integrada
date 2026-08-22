# backend/catalogo/views.py
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.busca import BuscaSemAcento
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nucleo.permissions import RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from .models import ComponenteComposicao, Item, TipoItemProprio
from .pagination import CatalogoPageNumberPagination
from .serializers import (
    ComponenteComposicaoSerializer,
    ItemSerializer,
    TipoItemProprioSerializer,
)


class BaseCatalogoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Catálogo é **fundação** (sem entitlement): isolamento por tenant + checagem
    por permissão `cadastro.item.*` (camada 2). Sem `RequireModule` — disponível a
    todo tenant autenticado, como fornecedores/clientes."""

    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    pagination_class = CatalogoPageNumberPagination


class ItemViewSet(BaseCatalogoViewSet):
    queryset = Item.objects.all().order_by("descricao")
    serializer_class = ItemSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = [
        "tipo", "tipo_proprio", "categoria", "ativo",
        "compravel", "estocavel", "vendavel", "consumivel", "rastreavel",
    ]
    search_fields = ["codigo_interno", "descricao", "categoria", "gtin"]
    ordering_fields = ["descricao", "codigo_interno"]
    required_resource = "cadastro.item"


class TipoItemProprioViewSet(BaseCatalogoViewSet):
    """Os tipos de item **da empresa**.

    Recurso próprio (`cadastro.tipo_item`) e não um pedaço de `cadastro.item`:
    cadastrar um item é trabalho diário de quem compra e de quem orça; **definir
    um tipo** muda como o sistema calcula todos os itens que o usam — encargo
    social, entrada na relação de compra, saldo em estoque. É a mesma classe de
    ato que criar e excluir cliente, e por isso mora numa permissão que o admin
    do tenant entrega a quem responde pelo cadastro-mestre.
    """

    queryset = TipoItemProprio.objects.all().order_by("nome")
    serializer_class = TipoItemProprioSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["natureza", "ativo"]
    search_fields = ["codigo", "nome", "descricao"]
    ordering_fields = ["nome", "natureza"]
    required_resource = "cadastro.tipo_item"
    pagination_class = None  # dezenas, não milhares: a tela mostra a lista toda

    @action(detail=False, methods=["get"], url_path="naturezas")
    def naturezas(self, request):
        """As naturezas possíveis **com os padrões de flag de cada uma**.

        A tela pergunta a natureza primeiro e já preenche o resto — é o que evita
        que alguém marque cinco caixas sem saber o que cada uma faz. O de-para
        vive no model (`padroes_da_natureza`), não no frontend, senão a tela e o
        banco discordariam na primeira mudança de regra.
        """
        return Response([
            {
                "valor": valor,
                "rotulo": rotulo,
                "padroes": TipoItemProprio.padroes_da_natureza(valor),
            }
            for valor, rotulo in Item.Tipo.choices
        ])


class ComponenteComposicaoViewSet(BaseCatalogoViewSet):
    queryset = ComponenteComposicao.objects.all().order_by("item_pai", "componente_id")
    serializer_class = ComponenteComposicaoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["item_pai", "item_filho"]
    required_resource = "cadastro.item"
    pagination_class = None  # lida por item_pai (composição pequena)
