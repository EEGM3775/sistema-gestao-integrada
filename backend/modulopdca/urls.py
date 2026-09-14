# backend/modulopdca/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ApontamentoAvancoViewSet,
    AtividadeViewSet,
    CalendarioTrabalhoViewSet,
    CronogramaViewSet,
    ExcecaoCalendarioViewSet,
    LocalObraViewSet,
    PdcaStatusView,
    PrecedenciaViewSet,
)

router = DefaultRouter()
router.register(r"locais", LocalObraViewSet, basename="pdca-local")
router.register(r"calendarios", CalendarioTrabalhoViewSet, basename="pdca-calendario")
router.register(r"excecoes-calendario", ExcecaoCalendarioViewSet, basename="pdca-excecao")
router.register(r"cronogramas", CronogramaViewSet, basename="pdca-cronograma")
router.register(r"atividades", AtividadeViewSet, basename="pdca-atividade")
router.register(r"precedencias", PrecedenciaViewSet, basename="pdca-precedencia")
router.register(r"apontamentos", ApontamentoAvancoViewSet, basename="pdca-apontamento")

urlpatterns = [
    path("status/", PdcaStatusView.as_view(), name="pdca-status"),
    path("", include(router.urls)),
]
