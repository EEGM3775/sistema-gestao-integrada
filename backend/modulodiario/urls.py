# backend/modulodiario/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DiarioObraViewSet,
    EntradaDiarioViewSet,
    DocumentoDiarioViewSet,
    documentos_com_analise,
    detalhes_documento_analise,
    reprocessar_analise,
    status_analise,
)

router = DefaultRouter()
router.register(r'diarios', DiarioObraViewSet, basename='diarioobra')
router.register(r'entradas', EntradaDiarioViewSet, basename='entradadiario')
router.register(r'documentos', DocumentoDiarioViewSet, basename='documentodiario')

urlpatterns = [
    path('', include(router.urls)),
    path('documentos-com-analise/', documentos_com_analise, name='documentos-com-analise'),
    path('documento-analise/<int:documento_id>/', detalhes_documento_analise, name='detalhes-documento-analise'),
    path('reprocessar-analise/', reprocessar_analise, name='reprocessar-analise'),
    path('status-analise/<int:documento_id>/', status_analise, name='status-analise'),
]
