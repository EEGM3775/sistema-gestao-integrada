# backend/catalogo/views.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets

from nucleo.permissions import RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from .models import ComponenteComposicao, Item
from .pagination import CatalogoPageNumberPagination
from .serializers import ComponenteComposicaoSerializer, ItemSerializer


class BaseCatalogoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Catálogo é **fundação** (sem entitlement): isolamento por tenant + checagem
    por permissão `cadastro.item.*` (camada 2). Sem `RequireModule` — disponível a
    todo tenant autenticado, como fornecedores/clientes."""

    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    pagination_class = CatalogoPageNumberPagination


class ItemViewSet(BaseCatalogoViewSet):
    queryset = Item.objects.all().order_by("descricao")
    serializer_class = ItemSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        "tipo", "categoria", "ativo",
        "compravel", "estocavel", "vendavel", "consumivel", "rastreavel",
    ]
    search_fields = ["codigo_interno", "descricao", "categoria", "gtin"]
    ordering_fields = ["descricao", "codigo_interno"]
    required_resource = "cadastro.item"


class ComponenteComposicaoViewSet(BaseCatalogoViewSet):
    queryset = ComponenteComposicao.objects.all().order_by("item_pai", "componente_id")
    serializer_class = ComponenteComposicaoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["item_pai", "item_filho"]
    required_resource = "cadastro.item"
    pagination_class = None  # lida por item_pai (composição pequena)
