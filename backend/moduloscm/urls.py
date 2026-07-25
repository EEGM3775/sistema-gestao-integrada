from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AvaliacaoFornecedorViewSet,
    CentroCustoViewSet,
    CotacaoViewSet,
    DemandaViewSet,
    FaixaPrecoOfertaViewSet,
    ItemDemandaViewSet,
    ItemPedidoViewSet,
    ItemPropostaViewSet,
    ItemRecebimentoViewSet,
    OfertaFornecedorViewSet,
    PedidoCompraViewSet,
    PropostaViewSet,
    RecebimentoViewSet,
    ScmDashboardView,
    ScmStatusView,
)

router = DefaultRouter()
router.register(r"centros-custo", CentroCustoViewSet, basename="scm-centrocusto")
router.register(r"ofertas", OfertaFornecedorViewSet, basename="scm-oferta")
router.register(r"faixas-preco", FaixaPrecoOfertaViewSet, basename="scm-faixapreco")
router.register(r"demandas", DemandaViewSet, basename="scm-demanda")
router.register(r"itens-demanda", ItemDemandaViewSet, basename="scm-itemdemanda")
router.register(r"cotacoes", CotacaoViewSet, basename="scm-cotacao")
router.register(r"propostas", PropostaViewSet, basename="scm-proposta")
router.register(r"itens-proposta", ItemPropostaViewSet, basename="scm-itemproposta")
router.register(r"pedidos", PedidoCompraViewSet, basename="scm-pedido")
router.register(r"itens-pedido", ItemPedidoViewSet, basename="scm-itempedido")
router.register(r"recebimentos", RecebimentoViewSet, basename="scm-recebimento")
router.register(r"itens-recebimento", ItemRecebimentoViewSet, basename="scm-itemrecebimento")
router.register(r"avaliacoes", AvaliacaoFornecedorViewSet, basename="scm-avaliacao")

urlpatterns = [
    path("status/", ScmStatusView.as_view(), name="scm-status"),
    path("dashboard/", ScmDashboardView.as_view(), name="scm-dashboard"),
    path("", include(router.urls)),
]
