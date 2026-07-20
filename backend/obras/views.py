# backend/obras/views.py
# Define a lógica da API (endpoints) para o app 'obras'.
from rest_framework import viewsets
from rest_framework import permissions
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from nucleo.quotas import QuotaEnforcedMixin
from .models import Obra, EtapaObra, DocumentoObra
from .serializers import (
    ObraSerializer,
    EtapaObraSerializer,
    DocumentoObraSerializer
)
from .filters import ObraFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from decimal import Decimal
from datetime import date

class ObraViewSet(QuotaEnforcedMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar obras.
    """
    queryset = Obra.objects.all()
    serializer_class = ObraSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ObraFilter
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "obra.obra"
    quota_recurso = "obras"  # D24

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def progresso(self, request, pk=None):
        """Retorna o progresso ponderado da obra (valor + duração).

        GET /obras/{pk}/progresso/
        """
        obra = self.get_object()
        etapas = list(obra.etapas.all())
        total_etapas = len(etapas)
        if total_etapas == 0:
            return Response({'progresso': 0})

        valores = []
        duracoes = []
        pct_list = []
        for e in etapas:
            valor = e.orcamento_previsto if e.orcamento_previsto is not None else Decimal('0')
            valores.append(Decimal(valor))
            inicio = e.data_inicio_prevista
            fim = e.data_fim_prevista
            dur = 0
            if inicio and fim and isinstance(inicio, date) and isinstance(fim, date):
                try:
                    dur = max(0, (fim - inicio).days)
                except Exception:
                    dur = 0
            duracoes.append(dur)
            pct_list.append(float(e.percentual_conclusao or 0))

        total_valor = sum(valores) if valores else Decimal('0')
        total_dur = sum(duracoes) if duracoes else 0

        if (total_valor == 0 or total_valor == Decimal('0')) and total_dur == 0:
            avg = sum(pct_list) / total_etapas
            return Response({'progresso': int(round(avg))})

        COST_TIME_BLEND = 0.6
        weighted_sum = 0.0
        for idx, pct in enumerate(pct_list):
            weight = 0.0
            if total_valor > 0 and total_dur > 0:
                w_val = float(valores[idx] / total_valor) if total_valor > 0 else 0.0
                w_dur = (duracoes[idx] / total_dur) if total_dur > 0 else 0.0
                weight = COST_TIME_BLEND * w_val + (1.0 - COST_TIME_BLEND) * w_dur
            elif total_valor > 0:
                weight = float(valores[idx] / total_valor) if total_valor > 0 else 0.0
            else:
                weight = (duracoes[idx] / total_dur) if total_dur > 0 else 0.0

            weighted_sum += weight * pct

        return Response({'progresso': int(round(weighted_sum))})

class EtapaObraViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar etapas de obras.
    """
    queryset = EtapaObra.objects.all().order_by('ordem', 'etapa_id')
    serializer_class = EtapaObraSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "obra.obra"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['obra']

class DocumentoObraViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar documentos de obras.
    """
    queryset = DocumentoObra.objects.all()
    serializer_class = DocumentoObraSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "obra.obra"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['obra']
