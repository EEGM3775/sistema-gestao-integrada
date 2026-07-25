# backend/moduloorcamento/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BaseReferencialResumoView,
    BaseReferencialViewSet,
    InsumoReferenciaViewSet,
    ItemOrcadoViewSet,
    OrcamentoStatusView,
    OrcamentoViewSet,
    RevisaoOrcamentoViewSet,
)

router = DefaultRouter()
router.register(r"bases", BaseReferencialViewSet, basename="orcamento-base")
router.register(r"referencias", InsumoReferenciaViewSet, basename="orcamento-referencia")
router.register(r"orcamentos", OrcamentoViewSet, basename="orcamento-orcamento")
router.register(r"itens", ItemOrcadoViewSet, basename="orcamento-item")
router.register(r"revisoes", RevisaoOrcamentoViewSet, basename="orcamento-revisao")

urlpatterns = [
    path("status/", OrcamentoStatusView.as_view(), name="orcamento-status"),
    path("bases-resumo/", BaseReferencialResumoView.as_view(), name="orcamento-bases-resumo"),
    *router.urls,
]
