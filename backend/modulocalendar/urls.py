from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CalendarEventViewSet, CalendarViewSet, FeriadosStatusView, LocalidadesObrasView, PessoasView,
)

app_name = 'modulocalendar'

router = DefaultRouter()
router.register(r'events', CalendarEventViewSet, basename='calendarevent')
# Fatia D: as agendas (pessoal, equipe, empresa).
router.register(r'calendars', CalendarViewSet, basename='calendar')

urlpatterns = [
    # Fatia F: localidades das obras (p/ o seletor) e status da sincronização.
    path('localidades/', LocalidadesObrasView.as_view(), name='localidades'),
    path('feriados/status/', FeriadosStatusView.as_view(), name='feriados-status'),
    # Fatia D: quem pode ser convidado (seletor com busca no servidor).
    path('pessoas/', PessoasView.as_view(), name='pessoas'),
    path('', include(router.urls)),
]
