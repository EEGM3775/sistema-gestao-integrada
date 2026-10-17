"""Endpoint da trilha de auditoria — Fase 9.E.

``GET /api/auditoria/`` — leitura da trilha imutável, isolada por tenant, com a
permissão ``plataforma.auditoria.view`` (ou admin de tenant/plataforma). Sem
verbo de escrita: a imutabilidade do `AuditLog` também vale na superfície da API
(``ReadOnlyModelViewSet``). Fail-closed (`RequirePermissionStrict`, sem fallback
de papel), coerente com o restante das operações sensíveis da Fase 9.

**D17 — a leitura unificada.** A tela "Trilha de auditoria" junta esta trilha com
a de identidade da IAM (`GET /iam/eventos-seguranca/`). Para as duas se
intercalarem pelo horário, as duas paginam do mesmo jeito (`PAGINA_*["auditoria"]`
do `payment/planos.py`), aceitam o mesmo período (`?desde=`/`?ate=`, ISO) e o
mesmo recorte por pessoa (`?pessoa=<login>` — quem agiu, aqui; quem agiu ou quem
sofreu, lá). Antes disto a lista vinha inteira, sem página nenhuma.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO

from .lgpd_views import RequirePermissionStrict
from .models import AuditLog
from .tenancy import TenantScopedViewSetMixin


class AuditoriaPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["auditoria"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["auditoria"]


def periodo(queryset, campo, params):
    """`?desde=`/`?ate=` (data ou data-hora ISO) sobre `campo`. Data sem hora no
    `ate` vale até o fim do dia."""
    for nome, comparador in (("desde", "gte"), ("ate", "lte")):
        valor = (params.get(nome) or "").strip()
        if not valor:
            continue
        # Só data vale o dia inteiro. O `parse_datetime` do Django aceitaria
        # "2026-10-10" como meia-noite sem fuso — e o `ate` cortaria o dia.
        if "T" in valor or " " in valor:
            quando, chave = parse_datetime(valor), f"{campo}__{comparador}"
        else:
            quando, chave = parse_date(valor), f"{campo}__date__{comparador}"
        if quando is not None:
            queryset = queryset.filter(**{chave: quando})
    return queryset


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
    pagination_class = AuditoriaPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["modelo", "acao", "usuario", "objeto_id"]
    ordering_fields = ["timestamp"]
    ordering = ["-timestamp", "-id"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        qs = periodo(qs, "timestamp", params)
        pessoa = (params.get("pessoa") or "").strip()
        if pessoa:
            qs = qs.filter(Q(usuario_nome__iexact=pessoa) | Q(usuario__username__iexact=pessoa))
        return qs
