from rest_framework import views, permissions
from rest_framework.response import Response
from nucleo.permissions import RequireModule


class ApsStatusView(views.APIView):
    """Endpoint de status do módulo APS. Confirma entitlement antes de qualquer dado."""
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "aps"

    def get(self, request):
        return Response({"modulo": "aps", "status": "ativo"})
