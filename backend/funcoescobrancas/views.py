# backend/funcoescobrancas/views.py
import logging

from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from nucleo.permissions import RequireModule, RequirePermission

from . import services
from .models import EventoWebhookAsaas
from .serializers import EventoWebhookAsaasSerializer

logger = logging.getLogger(__name__)


class WebhookAsaasView(APIView):
    """
    Endpoint público que recebe os eventos do Asaas (`PAYMENT_RECEIVED`,
    `PAYMENT_CONFIRMED`, etc.) e dá a baixa automática — "como o ERP sabe quem
    já pagou" (moduloerp.md §6/funcoescobrancas.md).

    Sem autenticação de usuário (o Asaas não tem sessão/JWT do SGI): a defesa
    é o `ASAAS_WEBHOOK_TOKEN`, conferido no header `asaas-access-token`, e a
    idempotência por `event.id` em `EventoWebhookAsaas`/`processar_evento_webhook`
    (o Asaas reenvia eventos não confirmados — boa prática obrigatória da
    integração).
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        token_recebido = request.headers.get('asaas-access-token', '')
        if not settings.ASAAS_WEBHOOK_TOKEN or token_recebido != settings.ASAAS_WEBHOOK_TOKEN:
            logger.warning("Webhook Asaas rejeitado: token de validação ausente ou incorreto.")
            return Response({'detail': 'token de validação inválido'}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data
        evento_id = payload.get('id')
        tipo = payload.get('event')
        if not evento_id or not tipo:
            return Response({'detail': 'payload incompleto — esperado "id" e "event"'}, status=status.HTTP_400_BAD_REQUEST)

        evento = services.processar_evento_webhook(evento_id=evento_id, tipo=tipo, payload=payload)
        return Response({'detail': 'evento recebido', 'resultado': evento.resultado}, status=status.HTTP_200_OK)


class EventoWebhookAsaasViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Somente leitura — alimenta a timeline de eventos do webhook na
    `BoletoDetailPage` (UI, D.1.2): `GET /api/erp/cobrancas/eventos/?boleto=<id>`.

    Não herda `TenantScopedViewSetMixin` porque `EventoWebhookAsaas` não é
    `TenantScopedModel` (ver docstring do model) — o isolamento é feito aqui
    via `boleto__tenant_id`, o único caminho até o tenant.
    """
    serializer_class = EventoWebhookAsaasSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    required_resource = "erp.cobranca"   # ReadOnly: GET→erp.cobranca.view
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['boleto']

    def get_queryset(self):
        queryset = EventoWebhookAsaas.objects.select_related('boleto').all()
        user = self.request.user
        if not user.is_superuser:
            queryset = queryset.filter(boleto__tenant_id=getattr(user, 'tenant_id', None))
        return queryset
