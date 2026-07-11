"""Endpoint da trilha de auditoria — Fase 9.E.

``GET /api/auditoria/`` — leitura da trilha imutável, isolada por tenant, com a
permissão ``plataforma.auditoria.view`` (ou admin de tenant/plataforma). Sem
verbo de escrita: a imutabilidade do `AuditLog` também vale na superfície da API
(``ReadOnlyModelViewSet``). Fail-closed (`RequirePermissionStrict`, sem fallback
de papel), coerente com o restante das operações sensíveis da Fase 9.
"""
from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from .lgpd_views import RequirePermissionStrict
from .models import AuditLog
from .tenancy import TenantScopedViewSetMixin


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id", "tenant", "usuario", "usuario_nome", "acao", "modelo",
            "objeto_id", "detalhes", "timestamp",
        ]
        read_only_fields = fields


class AuditLogViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Trilha de auditoria (somente leitura). Requer ``plataforma.auditoria.view``."""

    queryset = AuditLog.objects.all().order_by("-timestamp")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, RequirePermissionStrict]
    required_permission = "plataforma.auditoria.view"
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["modelo", "acao", "usuario", "objeto_id"]
    ordering_fields = ["timestamp"]
    ordering = ["-timestamp"]
