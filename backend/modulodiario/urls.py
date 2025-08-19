# backend/modulodiario/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DiarioObraViewSet, DocumentoDiarioViewSet

router = DefaultRouter()
router.register(r'diarios', DiarioObraViewSet)
router.register(r'documentos', DocumentoDiarioViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
