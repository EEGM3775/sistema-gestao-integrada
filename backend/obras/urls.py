# backend/obras/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ObraViewSet

router = DefaultRouter()
router.register(r'', ObraViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
