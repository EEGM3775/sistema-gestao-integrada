# backend/modulomaps/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CamadaViewSet,
    DetectarEnderecoView,
    FeicaoViewSet,
    GeofenceViewSet,
    LocalViewSet,
    MapaDaEmpresaView,
    MapsStatusView,
    OrtofotoViewSet,
    ParadaRotaViewSet,
    PlanoVooViewSet,
    RotaViewSet,
)

router = DefaultRouter()
# Fundação (sem entitlement)
router.register(r"locais", LocalViewSet, basename="maps-local")
# Camadas (entitlement `maps`)
router.register(r"camadas", CamadaViewSet, basename="maps-camada")
router.register(r"feicoes", FeicaoViewSet, basename="maps-feicao")
router.register(r"ortofotos", OrtofotoViewSet, basename="maps-ortofoto")
router.register(r"planos-voo", PlanoVooViewSet, basename="maps-planovoo")
router.register(r"rotas", RotaViewSet, basename="maps-rota")
router.register(r"paradas", ParadaRotaViewSet, basename="maps-parada")
router.register(r"geofences", GeofenceViewSet, basename="maps-geofence")

urlpatterns = [
    path("status/", MapsStatusView.as_view(), name="maps-status"),
    path("mapa/", MapaDaEmpresaView.as_view(), name="maps-mapa"),
    path("detectar-endereco/", DetectarEnderecoView.as_view(), name="maps-detectar-endereco"),
    path("", include(router.urls)),
]
