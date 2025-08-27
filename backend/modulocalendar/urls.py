
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarEventViewSet, calendar_view

app_name = 'modulocalendar'

router = DefaultRouter()
router.register(r'events', CalendarEventViewSet, basename='calendarevent')

urlpatterns = [
    path('api/', include(router.urls)),
    path('', calendar_view, name='calendar'),
]
