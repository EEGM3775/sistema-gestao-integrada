# backend/nucleo/notificacoes_views.py
"""API do centro de notificações in-app (Calendário, Fatia C).

`GET /api/notificacoes/` — as notificações do **próprio usuário** (as mais
recentes; `?unread=1` filtra as não-lidas). Ações de marcação:
`unread-count` (badge do sino), `marcar-lida` (uma) e `marcar-todas-lidas`.

Módulo **base** (sem entitlement): notificação é do usuário, não de um módulo
pago. Isolamento por tenant pela RLS armada na autenticação + o filtro por
`user`. Sem verbo de escrita direto (as notificações nascem de tasks/eventos);
o cliente só lê e marca como lida.
"""
from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payment.planos import NOTIFICACOES_LIMITE_LISTA

from .models import Notificacao
from .tenancy import TenantScopedViewSetMixin

# Teto de itens devolvidos na listagem — o sino mostra as recentes, não um
# histórico infinito (sem paginação global configurada no projeto).
LIMITE_LISTA = NOTIFICACOES_LIMITE_LISTA


class NotificacaoSerializer(serializers.ModelSerializer):
    lida = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notificacao
        fields = ["id", "titulo", "mensagem", "tipo", "nivel", "url", "lida", "lida_em", "criado_em"]
        # `lida` é declarado explicitamente acima (property do modelo) — não pode
        # entrar em read_only_fields (o DRF proíbe duplicar). Os demais campos,
        # sim; de resto o ViewSet é ReadOnly.
        read_only_fields = ["id", "titulo", "mensagem", "tipo", "nivel", "url", "lida_em", "criado_em"]


class NotificacaoViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Notificações do usuário autenticado (somente leitura + marcação)."""

    serializer_class = NotificacaoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notificacao.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") in ("1", "true", "True"):
            qs = qs.filter(lida_em__isnull=True)
        return qs

    def list(self, request, *args, **kwargs):
        eventos = self.get_queryset()[:LIMITE_LISTA]
        return Response(self.get_serializer(eventos, many=True).data)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Contador para o badge do sino (chamado em polling pelo frontend)."""
        total = Notificacao.objects.filter(user=request.user, lida_em__isnull=True).count()
        return Response({"count": total})

    @action(detail=True, methods=["post"], url_path="marcar-lida")
    def marcar_lida(self, request, pk=None):
        notificacao = self.get_object()
        notificacao.marcar_lida()
        return Response(self.get_serializer(notificacao).data)

    @action(detail=False, methods=["post"], url_path="marcar-todas-lidas")
    def marcar_todas_lidas(self, request):
        from django.utils import timezone
        atualizadas = Notificacao.objects.filter(
            user=request.user, lida_em__isnull=True,
        ).update(lida_em=timezone.now())
        return Response({"marcadas": atualizadas})
