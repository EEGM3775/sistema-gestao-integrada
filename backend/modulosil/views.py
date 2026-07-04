from rest_framework import views, permissions
from rest_framework.response import Response
from nucleo.permissions import RequireModule


class SilStatusView(views.APIView):
    """Endpoint de status do módulo SIL. Confirma entitlement antes de qualquer dado."""
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "sil"

    def get(self, request):
        return Response({"modulo": "sil", "status": "ativo"})
