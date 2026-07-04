from rest_framework import views, permissions
from rest_framework.response import Response
from nucleo.permissions import RequireModule


class ScmStatusView(views.APIView):
    """Endpoint de status do módulo SCM. Confirma entitlement antes de qualquer dado."""
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "scm"

    def get(self, request):
        return Response({"modulo": "scm", "status": "ativo"})
