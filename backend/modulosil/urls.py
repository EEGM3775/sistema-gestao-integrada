from django.urls import path
from .views import SilStatusView

urlpatterns = [
    path("status/", SilStatusView.as_view(), name="sil-status"),
]
