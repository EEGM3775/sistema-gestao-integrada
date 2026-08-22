# backend/moduloprancheta/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcervoView,
    DerivadaProjetoViewSet,
    DesenhoProjetoViewSet,
    DisciplinaProjetoViewSet,
    DocumentoProjetoViewSet,
    MarcacaoViewSet,
    MedicaoViewSet,
    PontoDeVistaViewSet,
    PranchetaStatusView,
    RevisaoDocumentoViewSet,
)

router = DefaultRouter()
router.register(r"disciplinas", DisciplinaProjetoViewSet, basename="prancheta-disciplina")
router.register(r"documentos", DocumentoProjetoViewSet, basename="prancheta-documento")
router.register(r"revisoes", RevisaoDocumentoViewSet, basename="prancheta-revisao")
router.register(r"desenhos", DesenhoProjetoViewSet, basename="prancheta-desenho")
router.register(r"derivadas", DerivadaProjetoViewSet, basename="prancheta-derivada")
router.register(r"marcacoes", MarcacaoViewSet, basename="prancheta-marcacao")
router.register(r"medicoes", MedicaoViewSet, basename="prancheta-medicao")
router.register(r"pontos-de-vista", PontoDeVistaViewSet, basename="prancheta-ponto-de-vista")

urlpatterns = [
    path("status/", PranchetaStatusView.as_view(), name="prancheta-status"),
    path("acervo/", AcervoView.as_view(), name="prancheta-acervo"),
    path("", include(router.urls)),
]
