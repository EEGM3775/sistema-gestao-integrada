from django.urls import path
from .views import ApsStatusView

urlpatterns = [
    path("status/", ApsStatusView.as_view(), name="aps-status"),
]
