from rest_framework import views, permissions
from rest_framework.response import Response
from nucleo.permissions import RequireModule


class PdcaStatusView(views.APIView):
    """Endpoint de status do módulo PDCA. Confirma entitlement antes de qualquer dado."""
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "pdca"

    def get(self, request):
        return Response({"modulo": "pdca", "status": "ativo"})
