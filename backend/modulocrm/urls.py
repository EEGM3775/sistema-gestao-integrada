# backend/modulocrm/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeadViewSet,
    AccountViewSet,
    ContactViewSet,
    OpportunityViewSet,
    InteractionViewSet
)

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'accounts', AccountViewSet, basename='account')
router.register(r'contacts', ContactViewSet, basename='contact')
router.register(r'opportunities', OpportunityViewSet, basename='opportunity')
router.register(r'interactions', InteractionViewSet, basename='interaction')

urlpatterns = [
    path('', include(router.urls)),
]
