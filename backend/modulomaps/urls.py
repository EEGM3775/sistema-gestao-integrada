from django.urls import path
from .views import MapsStatusView

urlpatterns = [
    path("status/", MapsStatusView.as_view(), name="maps-status"),
]
