# backend/modulopdca/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AditivoContratoViewSet,
    ApontamentoAvancoViewSet,
    AtividadeViewSet,
    CalendarioTrabalhoViewSet,
    ContratoObraViewSet,
    CronogramaViewSet,
    ExcecaoCalendarioViewSet,
    ItemContratoViewSet,
    LiberacaoRetencaoViewSet,
    LocalObraViewSet,
    MedicaoViewSet,
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
# PDCA.3 — o dinheiro
router.register(r"contratos", ContratoObraViewSet, basename="pdca-contrato")
router.register(r"itens-contrato", ItemContratoViewSet, basename="pdca-item-contrato")
router.register(r"medicoes", MedicaoViewSet, basename="pdca-medicao")
router.register(r"liberacoes", LiberacaoRetencaoViewSet, basename="pdca-liberacao")
# PDCA.4 — o contrato mudando por escrito
router.register(r"aditivos", AditivoContratoViewSet, basename="pdca-aditivo")

urlpatterns = [
    path("status/", PdcaStatusView.as_view(), name="pdca-status"),
    path("", include(router.urls)),
]
