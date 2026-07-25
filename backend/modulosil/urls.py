# backend/modulosil/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AplicadoView,
    CurvaABCView,
    DevolucaoViewSet,
    EmprestimoFerramentaViewSet,
    EntregaEPIViewSet,
    FerramentaViewSet,
    InventarioViewSet,
    ItemDevolucaoViewSet,
    ItemInventarioViewSet,
    ItemRequisicaoViewSet,
    ItemTransferenciaViewSet,
    LocalEstoqueViewSet,
    LoteViewSet,
    MovimentacaoEstoqueViewSet,
    RequisicaoViewSet,
    SaldoEstoqueViewSet,
    SilDashboardView,
    SilStatusView,
    TransferenciaViewSet,
)

router = DefaultRouter()
router.register(r"locais", LocalEstoqueViewSet, basename="sil-local")
router.register(r"saldos", SaldoEstoqueViewSet, basename="sil-saldo")
router.register(r"movimentacoes", MovimentacaoEstoqueViewSet, basename="sil-movimentacao")
router.register(r"lotes", LoteViewSet, basename="sil-lote")
router.register(r"requisicoes", RequisicaoViewSet, basename="sil-requisicao")
router.register(r"itens-requisicao", ItemRequisicaoViewSet, basename="sil-itemrequisicao")
router.register(r"transferencias", TransferenciaViewSet, basename="sil-transferencia")
router.register(r"itens-transferencia", ItemTransferenciaViewSet, basename="sil-itemtransferencia")
router.register(r"devolucoes", DevolucaoViewSet, basename="sil-devolucao")
router.register(r"itens-devolucao", ItemDevolucaoViewSet, basename="sil-itemdevolucao")
router.register(r"inventarios", InventarioViewSet, basename="sil-inventario")
router.register(r"itens-inventario", ItemInventarioViewSet, basename="sil-iteminventario")
router.register(r"entregas-epi", EntregaEPIViewSet, basename="sil-entregaepi")
router.register(r"ferramentas", FerramentaViewSet, basename="sil-ferramenta")
router.register(r"emprestimos", EmprestimoFerramentaViewSet, basename="sil-emprestimo")

urlpatterns = [
    path("status/", SilStatusView.as_view(), name="sil-status"),
    path("dashboard/", SilDashboardView.as_view(), name="sil-dashboard"),
    path("curva-abc/", CurvaABCView.as_view(), name="sil-curva-abc"),
    path("aplicado/", AplicadoView.as_view(), name="sil-aplicado"),
    path("", include(router.urls)),
]
