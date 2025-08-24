# backend/funcoesia/views.py
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import JsonResponse
from .models import AnaliseImagemIA
from .serializers import AnaliseImagemIASerializer
import requests
from django.conf import settings

class AnaliseImagemIAViewSet(mixins.CreateModelMixin,
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
    
    def get_queryset(self):
        """
        Permite filtrar por documento_id
        """
        queryset = AnaliseImagemIA.objects.all()
        documento_id = self.request.query_params.get('documento', None)
        if documento_id is not None:
            queryset = queryset.filter(documento_id=documento_id)
        return queryset


# Views de proxy para o microserviço de IA

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tipos_analise(request):
    """
    Proxy para obter tipos de análise disponíveis no microserviço de IA
    """
    try:
        # URL do microserviço de IA
        ia_url = getattr(settings, 'IA_SERVICE_URL', 'http://localhost:3002/api/analise')
        token = getattr(settings, 'IA_SERVICE_SECRET_TOKEN', 'um-token-secreto-forte-para-ia')
        
        response = requests.get(
            f"{ia_url}/tipos",
            headers={'X-Internal-Service-Token': token},
            timeout=5
        )
        
        if response.status_code == 200:
            return JsonResponse(response.json(), safe=False)
        else:
            # Fallback se o serviço não responder adequadamente
            raise requests.RequestException("Serviço indisponível")
            
    except requests.RequestException:
        # Fallback com tipos básicos
        tipos_basicos = [
            {
                'id': 'completa',
                'nome': 'Análise Completa da Obra',
                'descricao': 'Análise abrangente incluindo progresso, segurança, qualidade e produtividade'
            },
            {
                'id': 'qualidade_construcao',
                'nome': 'Análise de Qualidade',
                'descricao': 'Verificação da qualidade dos materiais e execução'
            },
            {
                'id': 'seguranca_obra',
                'nome': 'Análise de Segurança',
                'descricao': 'Identificação de riscos e problemas de segurança'
            },
            {
                'id': 'completa',
                'nome': 'Análise Completa',
                'descricao': 'Análise abrangente incluindo progresso, qualidade e segurança'
            }
        ]
        return JsonResponse(tipos_basicos, safe=False)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recomendacoes_analise(request):
    """
    Proxy para obter recomendações de análise
    """
    try:
        # URL do microserviço de IA
        ia_url = getattr(settings, 'IA_SERVICE_URL', 'http://localhost:3002/api/analise')
        token = getattr(settings, 'IA_SERVICE_SECRET_TOKEN', 'um-token-secreto-forte-para-ia')
        
        response = requests.get(
            f"{ia_url.replace('/analise', '')}/api/analise/recomendacoes",
            headers={'X-Internal-Service-Token': token},
            timeout=5
        )
        
        if response.status_code == 200:
            return JsonResponse(response.json(), safe=False)
        else:
            raise requests.RequestException("Serviço indisponível")
            
    except requests.RequestException:
        # Fallback básico
        return JsonResponse({
            'recomendacao': 'completa',
            'motivo': 'Análise padrão recomendada para documentos de obra'
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def iniciar_analise_proxy(request):
    """
    Proxy para iniciar análise no microserviço
    """
    try:
        # URL do microserviço de IA
        ia_url = getattr(settings, 'IA_SERVICE_URL', 'http://localhost:3002/api/analise')
        token = getattr(settings, 'IA_SERVICE_SECRET_TOKEN', 'um-token-secreto-forte-para-ia')
        
        response = requests.post(
            ia_url,
            json=request.data,
            headers={
                'X-Internal-Service-Token': token,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        if response.status_code in [200, 201, 202]:
            return JsonResponse(response.json(), status=response.status_code)
        else:
            return JsonResponse({
                'error': 'Erro no serviço de IA',
                'details': response.text
            }, status=response.status_code)
            
    except requests.RequestException as e:
        return JsonResponse({
            'error': 'Serviço de IA indisponível',
            'message': str(e)
        }, status=503)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reprocessar_analise(request):
    """
    Proxy para reprocessar análise no microserviço
    """
    try:
        documento_id = request.data.get('documento_id')
        if not documento_id:
            return JsonResponse({'error': 'documento_id é obrigatório'}, status=400)
        
        # URL do microserviço de IA
        ia_url = getattr(settings, 'IA_SERVICE_URL', 'http://localhost:3002/api/analise')
        token = getattr(settings, 'IA_SERVICE_SECRET_TOKEN', 'um-token-secreto-forte-para-ia')
        
        response = requests.post(
            f"{ia_url}/reprocessar",
            json={'documento_id': documento_id},
            headers={
                'X-Internal-Service-Token': token,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        if response.status_code in [200, 201, 202]:
            return JsonResponse(response.json(), status=response.status_code)
        else:
            return JsonResponse({
                'error': 'Erro ao reprocessar análise',
                'details': response.text
            }, status=response.status_code)
            
    except requests.RequestException as e:
        return JsonResponse({
            'error': 'Serviço de IA indisponível',
            'message': str(e)
        }, status=503)
