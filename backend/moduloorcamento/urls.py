# backend/moduloorcamento/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BaseReferencialResumoView,
    BaseReferencialViewSet,
    ComposicaoBDIViewSet,
    ControleDeCustoView,
    InsumoReferenciaViewSet,
    ItemOrcadoViewSet,
    MemorialNBRViewSet,
    OrcamentoStatusView,
    OrcamentoViewSet,
    ParametroObraViewSet,
    ParcelaEtapaViewSet,
    PavimentoObraViewSet,
    QuadrosNBRView,
    RevisaoOrcamentoViewSet,
    UnidadeAutonomaViewSet,
)

router = DefaultRouter()
router.register(r"bases", BaseReferencialViewSet, basename="orcamento-base")
router.register(r"referencias", InsumoReferenciaViewSet, basename="orcamento-referencia")
router.register(r"orcamentos", OrcamentoViewSet, basename="orcamento-orcamento")
router.register(r"itens", ItemOrcadoViewSet, basename="orcamento-item")
router.register(r"revisoes", RevisaoOrcamentoViewSet, basename="orcamento-revisao")
router.register(r"bdi", ComposicaoBDIViewSet, basename="orcamento-bdi")
router.register(r"parcelas", ParcelaEtapaViewSet, basename="orcamento-parcela")
router.register(r"parametricos", ParametroObraViewSet, basename="orcamento-parametrico")
router.register(r"pavimentos", PavimentoObraViewSet, basename="orcamento-pavimento")
router.register(r"unidades", UnidadeAutonomaViewSet, basename="orcamento-unidade")
router.register(r"memoriais", MemorialNBRViewSet, basename="orcamento-memorial")

urlpatterns = [
    path("status/", OrcamentoStatusView.as_view(), name="orcamento-status"),
    path("bases-resumo/", BaseReferencialResumoView.as_view(), name="orcamento-bases-resumo"),
    path("controle/", ControleDeCustoView.as_view(), name="orcamento-controle"),
    path("nbr12721/", QuadrosNBRView.as_view(), name="orcamento-nbr12721"),
    *router.urls,
]
