from rest_framework import views, permissions
from rest_framework.response import Response
from nucleo.permissions import RequireModule


class MapsStatusView(views.APIView):
    """Endpoint de status do módulo Maps. Confirma entitlement antes de qualquer dado."""
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "maps"

    def get(self, request):
        return Response({"modulo": "maps", "status": "ativo"})
