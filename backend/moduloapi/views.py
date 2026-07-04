# backend/moduloapi/views.py
from rest_framework import viewsets, permissions
from nucleo.tenancy import TenantScopedViewSetMixin
from .models import GoogleAccount
from .serializers import GoogleAccountSerializer

class GoogleAccountViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = GoogleAccount.objects.all()
    serializer_class = GoogleAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """ 
        This view should return a list of all the google accounts
        for the currently authenticated user.
        """
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, tenant_id=getattr(self.request.user, "tenant_id", None))
