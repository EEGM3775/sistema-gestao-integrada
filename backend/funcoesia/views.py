# backend/funcoesia/views.py
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import SAFE_METHODS
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequirePermission
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import JsonResponse
from .models import AnaliseImagemIA
from .serializers import AnaliseImagemIASerializer
from .tasks import analisar_documento_ia


class _RequireIaAnalise(RequirePermission):
    """Camada 2 (D5) para os proxies FBV do serviço de IA — sem `view.action`,
    então a permissão é fixada por método: leitura→`ia.analise.view`,
    disparo (POST, custo de processamento)→`ia.analise.executar`."""

    def _needed(self, request, view):
        return "ia.analise.view" if request.method in SAFE_METHODS else "ia.analise.executar"


class AnaliseImagemIAViewSet(TenantScopedViewSetMixin,
                               mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               viewsets.GenericViewSet):
    """
    ViewSet para criar, atualizar e listar análises de IA.
    - `POST`: Cria uma nova análise (usado pelo trigger).
    - `PATCH`: Atualiza uma análise (usado pelo microserviço de IA).
    - `GET`: Visualiza uma análise.
    - `GET /analises/`: Lista análises com filtros.
    """
    queryset = AnaliseImagemIA.objects.all()
    serializer_class = AnaliseImagemIASerializer
    # Camada 2 (Fase 9.B/D5): leitura→ia.analise.view · escrita→ia.analise.executar
    # (catálogo não tem `.edit`). Escrita vem do trigger/microserviço (D1/Fase 11).
    permission_classes = [IsAuthenticated, RequirePermission]
    permission_map = {"view": "ia.analise.view", "write": "ia.analise.executar"}

    def get_queryset(self):
        """
        Permite filtrar por documento_id
        """
        queryset = AnaliseImagemIA.objects.all()
        documento_id = self.request.query_params.get('documento', None)
        if documento_id is not None:
            queryset = queryset.filter(documento_id=documento_id)
        return queryset


# ─── Disparo/consulta da análise de IA ────────────────────────────────────────
# Fase 11.3: estes endpoints deixaram de fazer proxy HTTP para o microsserviço
# Node `funcoesia` (que respondia 401 ao `Token` legado — D1). Agora enfileiram
# a Celery task Python `analisar_documento_ia`, que roda a análise in-process.

# Tipos de análise suportados (o prompt de cada tipo vive no serviço de LLM de
# visão local; aqui só expomos o catálogo para a UI).
TIPOS_ANALISE = [
    {
        'id': 'completa',
        'nome': 'Análise Completa da Obra',
        'descricao': 'Análise abrangente incluindo progresso, segurança, qualidade e produtividade',
    },
    {
        'id': 'progresso_obra',
        'nome': 'Análise de Progresso',
        'descricao': 'Estimativa de avanço físico e observações do estágio da obra',
    },
    {
        'id': 'qualidade_construcao',
        'nome': 'Análise de Qualidade',
        'descricao': 'Verificação da qualidade dos materiais e execução',
    },
    {
        'id': 'seguranca_obra',
        'nome': 'Análise de Segurança',
        'descricao': 'Identificação de riscos e problemas de segurança (EPI, condições)',
    },
]


@api_view(['GET'])
@permission_classes([IsAuthenticated, _RequireIaAnalise])
def tipos_analise(request):
    """Catálogo de tipos de análise disponíveis (servido localmente)."""
    return JsonResponse(TIPOS_ANALISE, safe=False)


@api_view(['GET'])
@permission_classes([IsAuthenticated, _RequireIaAnalise])
def recomendacoes_analise(request):
    """Recomendação padrão de tipo de análise para documentos de obra."""
    return JsonResponse({
        'recomendacao': 'completa',
        'motivo': 'Análise padrão recomendada para documentos de obra',
    })


def _enfileirar_analise(request):
    """Valida o `documento_id` e enfileira a task Python de análise."""
    documento_id = request.data.get('documento_id')
    if not documento_id:
        return JsonResponse({'error': 'documento_id é obrigatório'}, status=400)
    tipo_analise = request.data.get('tipo_analise', 'completa')
    analisar_documento_ia.delay(documento_id=documento_id, tipo_analise=tipo_analise)
    return JsonResponse({
        'success': True,
        'message': 'Análise enfileirada.',
        'documento_id': documento_id,
        'tipo_analise': tipo_analise,
        'status': 'processando',
    }, status=202)


@api_view(['POST'])
@permission_classes([IsAuthenticated, _RequireIaAnalise])
def iniciar_analise_proxy(request):
    """Enfileira a análise de IA de um documento (task Python in-process)."""
    return _enfileirar_analise(request)


@api_view(['POST'])
@permission_classes([IsAuthenticated, _RequireIaAnalise])
def reprocessar_analise(request):
    """Reenfileira a análise de IA de um documento (reprocessamento)."""
    return _enfileirar_analise(request)
