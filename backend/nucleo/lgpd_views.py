"""Endpoints LGPD — Fase 9.D.

- ``GET  /api/lgpd/<tipo>/<id>/exportar/`` — portabilidade (plataforma.lgpd.exportar).
- ``POST /api/lgpd/<tipo>/<id>/esquecer/`` — esquecimento (plataforma.lgpd.excluir).
- ``/api/lgpd/incidentes/`` — CRUD do incidente; **confirmar/descartar/notificar**
  exigem o **dono da plataforma** (superuser da IAM), a trava de falso-positivo.
"""
from __future__ import annotations

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import autorizacao, lgpd
from .auditoria import registrar_auditoria
from .models import IncidenteLGPD
from .tenancy import TenantScopedAPIViewMixin, TenantScopedViewSetMixin


class RequirePermissionStrict(BasePermission):
    """Como o `RequirePermission` do nucleo, mas **sem fallback de papel** — fail-closed.
    Para operações novas e sensíveis (LGPD) sem histórico de transição: quem não
    tem a permissão explícita (ou não é admin) é barrado, mesmo com claim vazia.
    O ViewSet declara ``required_permission``."""

    message = "Você não tem permissão para esta operação."

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not u or not u.is_authenticated:
            return False
        needed = getattr(view, "required_permission", None)
        if not needed:
            return True
        if not (autorizacao.supervisiona(u) or autorizacao.pode(u, needed)):
            return False
        # Exportar e esquecer são da classe C: pedem autenticação recente (fase 6).
        autorizacao.exigir_confirmacao(u, needed)
        return True


class IsPlatformOwner(BasePermission):
    """Dono da plataforma (superuser da IAM) — confirma/descarta incidente."""

    message = "Apenas o dono da plataforma pode confirmar/descartar um incidente."

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and autorizacao.supervisiona(u))


def _get_titular(view, tipo, pk):
    if tipo not in lgpd.TITULARES:
        return None
    cfg = lgpd.TITULARES[tipo]
    qs = view.scope_qs(lgpd.titular_model(tipo).objects.all())
    return qs.filter(**{cfg["pk"]: pk}).first()


class LgpdExportarView(TenantScopedAPIViewMixin, APIView):
    """Portabilidade: exporta todos os dados do titular (JSON integral)."""

    permission_classes = [IsAuthenticated, RequirePermissionStrict]
    required_permission = "plataforma.lgpd.exportar"

    def get(self, request, tipo, pk):
        obj = _get_titular(self, tipo, pk)
        if obj is None:
            return Response({"detail": "Titular não encontrado."}, status=404)
        dados = lgpd.exportar_titular(tipo, obj)
        # Auditoria (Fase 9.E): a portabilidade expõe o PII integral do titular.
        registrar_auditoria(acao="exportar_lgpd", instance=obj,
                            usuario=request.user, detalhes={"tipo": tipo})
        return Response(dados)


class LgpdEsquecerView(TenantScopedAPIViewMixin, APIView):
    """Direito ao esquecimento: anonimiza o titular e apaga filhos de PII."""

    permission_classes = [IsAuthenticated, RequirePermissionStrict]
    required_permission = "plataforma.lgpd.excluir"

    def post(self, request, tipo, pk):
        obj = _get_titular(self, tipo, pk)
        if obj is None:
            return Response({"detail": "Titular não encontrado."}, status=404)
        lgpd.anonimizar_titular(tipo, obj)
        # Auditoria (Fase 9.E): esquecimento é destrutivo/irreversível — registra
        # antes que o próprio titular perca rastreabilidade.
        registrar_auditoria(acao="anonimizar_lgpd", instance=obj,
                            usuario=request.user, detalhes={"tipo": tipo})
        return Response({"detail": "Titular anonimizado.", "tipo": tipo, "id": pk}, status=200)


class IncidenteLGPDSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidenteLGPD
        fields = [
            "id", "descricao", "dados_afetados", "detectado_em", "status",
            "reportado_por", "confirmado_por", "confirmado_em", "prazo_anpd",
            "notificado_em", "criado_em", "tenant",
        ]
        read_only_fields = [
            "id", "status", "reportado_por", "confirmado_por", "confirmado_em",
            "prazo_anpd", "notificado_em", "criado_em", "tenant",
        ]


class IncidenteLGPDViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Incidentes LGPD. Reportar/listar: usuário do tenant com `plataforma.auditoria.view`
    (ou admin). Confirmar/descartar/notificar: **dono da plataforma**."""

    queryset = IncidenteLGPD.objects.all().order_by("-detectado_em")
    serializer_class = IncidenteLGPDSerializer

    def get_permissions(self):
        if self.action in ("confirmar", "descartar", "notificar"):
            return [IsAuthenticated(), IsPlatformOwner()]
        return [IsAuthenticated(), RequirePermissionStrict()]

    # reportar/listar exigem a permissão de auditoria (ou admin de tenant, que passa)
    required_permission = "plataforma.auditoria.view"

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            tenant_id=getattr(user, "tenant_id", None),
            reportado_por=user if user.is_authenticated else None,
        )

    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        inc = self.get_object()
        if inc.status != IncidenteLGPD.Status.PENDENTE:
            return Response({"detail": f"Incidente já está '{inc.status}'."}, status=400)
        inc.confirmar(request.user)
        return Response(self.get_serializer(inc).data)

    @action(detail=True, methods=["post"])
    def descartar(self, request, pk=None):
        inc = self.get_object()
        if inc.status != IncidenteLGPD.Status.PENDENTE:
            return Response({"detail": f"Incidente já está '{inc.status}'."}, status=400)
        inc.descartar(request.user)
        return Response(self.get_serializer(inc).data)

    @action(detail=True, methods=["post"])
    def notificar(self, request, pk=None):
        inc = self.get_object()
        if inc.status != IncidenteLGPD.Status.CONFIRMADO:
            return Response(
                {"detail": "Só um incidente confirmado pode ser notificado à ANPD."},
                status=400,
            )
        inc.marcar_notificado()
        return Response(self.get_serializer(inc).data)
