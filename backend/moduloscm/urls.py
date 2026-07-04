from django.urls import path
from .views import ScmStatusView

urlpatterns = [
    path("status/", ScmStatusView.as_view(), name="scm-status"),
]
