# backend/funcoesia/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnaliseImagemIAViewSet,
    tipos_analise,
    recomendacoes_analise,
    iniciar_analise_proxy,
    reprocessar_analise
)

router = DefaultRouter()
router.register(r'analises', AnaliseImagemIAViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('analise/tipos/', tipos_analise, name='tipos_analise'),
    path('analise/recomendacoes/', recomendacoes_analise, name='recomendacoes_analise'),
    path('analise/', iniciar_analise_proxy, name='iniciar_analise'),
    path('reprocessar/', reprocessar_analise, name='reprocessar_analise'),
]
