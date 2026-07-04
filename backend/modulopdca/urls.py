from django.urls import path
from .views import PdcaStatusView

urlpatterns = [
    path("status/", PdcaStatusView.as_view(), name="pdca-status"),
]
