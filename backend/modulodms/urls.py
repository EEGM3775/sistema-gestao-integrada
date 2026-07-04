from django.urls import path
from .views import DmsStatusView

urlpatterns = [
    path("status/", DmsStatusView.as_view(), name="dms-status"),
]
