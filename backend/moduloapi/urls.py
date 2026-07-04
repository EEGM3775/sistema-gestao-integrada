# backend/moduloapi/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GoogleAccountViewSet

router = DefaultRouter()
router.register(r'google-accounts', GoogleAccountViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
