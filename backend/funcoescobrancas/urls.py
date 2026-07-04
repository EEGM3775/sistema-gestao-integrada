# backend/funcoescobrancas/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EventoWebhookAsaasViewSet, WebhookAsaasView

router = DefaultRouter()
router.register(r'eventos', EventoWebhookAsaasViewSet, basename='evento-webhook-asaas')

urlpatterns = [
    path('webhook/asaas/', WebhookAsaasView.as_view(), name='webhook-asaas'),
    path('', include(router.urls)),
]
