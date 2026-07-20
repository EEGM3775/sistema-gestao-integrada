
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarEventViewSet, LocalidadesObrasView, FeriadosStatusView

app_name = 'modulocalendar'

router = DefaultRouter()
router.register(r'events', CalendarEventViewSet, basename='calendarevent')

urlpatterns = [
    # Fatia F: localidades das obras (p/ o seletor) e status da sincronização.
    path('localidades/', LocalidadesObrasView.as_view(), name='localidades'),
    path('feriados/status/', FeriadosStatusView.as_view(), name='feriados-status'),
    path('', include(router.urls)),
]
