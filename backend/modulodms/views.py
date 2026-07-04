from rest_framework import views, permissions
from rest_framework.response import Response
from nucleo.permissions import RequireModule


class DmsStatusView(views.APIView):
    """Endpoint de status do módulo DMS. Confirma entitlement antes de qualquer dado."""
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "dms"

    def get(self, request):
        return Response({"modulo": "dms", "status": "ativo"})
