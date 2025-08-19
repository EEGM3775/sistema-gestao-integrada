# backend/funcoesia/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnaliseImagemIAViewSet

router = DefaultRouter()
router.register(r'analises', AnaliseImagemIAViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
