# backend/modulodiario/views.py
from rest_framework import viewsets, mixins, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q

from nucleo.tenancy import TenantScopedViewSetMixin
from .models import DiarioObra, EntradaDiario, DocumentoDiario
from .serializers import (
    DiarioObraSerializer,
    EntradaDiarioSerializer,
    DocumentoDiarioSerializer,
)
from .tasks import disparar_analise_ia
from .services import registrar_contribuicao
from .permissions import (
    PodeModerarDiario,
    get_funcionario,
    pode_contribuir,
)


def _str_to_bool(value):
    return str(value).strip().lower() in ('1', 'true', 'on', 'sim', 'yes')


class DiarioObraViewSet(TenantScopedViewSetMixin,
                        mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    """
    Diário do dia (container por obra/data). A escrita de conteúdo é feita pela
    ação `contribuir` (get-or-create do dia). PUT/PATCH/DELETE do container e
    edição de entradas exigem responsável técnico (PodeModerarDiario).
    """
    queryset = DiarioObra.objects.all().select_related('obra', 'criado_por').prefetch_related(
        'entradas__autor', 'documentos__autor', 'documentos__analise_ia'
    )
    serializer_class = DiarioObraSerializer
    permission_classes = [IsAuthenticated, PodeModerarDiario]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = super().get_queryset()
        obra_id = self.request.query_params.get('obra')
        data = self.request.query_params.get('data')
        if obra_id:
            qs = qs.filter(obra_id=obra_id)
        if data:
            qs = qs.filter(data=data)
        return qs

    @action(detail=False, methods=['get'])
    def today(self, request):
        """Diário de hoje para uma obra (escopo obra+data, compartilhado)."""
        obra_id = request.query_params.get('obra') or request.query_params.get('obra_id')
        if not obra_id:
            return Response({'error': 'obra é obrigatório'}, status=400)
        diario = self.get_queryset().filter(obra_id=obra_id, data=timezone.localdate()).first()
        if diario is None:
            return Response({'exists': False, 'message': 'Nenhum diário para hoje'})
        return Response({'exists': True, 'diario': self.get_serializer(diario).data})

    @action(detail=False, methods=['post'])
    def contribuir(self, request):
        """
        Caminho único de escrita: get-or-create do diário do dia e anexa
        uma entrada de texto e/ou um documento (foto), com autoria.
        Aceita multipart (para o arquivo) ou JSON (só texto).
        """
        funcionario = get_funcionario(request.user)
        if funcionario is None:
            self.permission_denied(
                request,
                message="Seu usuário não possui cadastro de funcionário vinculado; apenas a equipe ou responsáveis técnicos da obra podem registrar no diário.",
            )

        obra_id = request.data.get('obra')
        if not obra_id:
            return Response({'obra': 'Campo obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        from obras.models import Obra
        try:
            obra = Obra.objects.get(pk=obra_id)
        except Obra.DoesNotExist:
            return Response({'obra': 'Obra não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        if not pode_contribuir(funcionario, obra):
            self.permission_denied(
                request,
                message="Você não faz parte da equipe nem é responsável técnico desta obra, portanto não pode registrar no diário dela.",
            )

        texto = (request.data.get('texto') or '').strip()
        arquivo = request.data.get('arquivo')
        if not texto and not arquivo:
            return Response(
                {'detail': 'Envie ao menos um texto ou uma foto.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_id = getattr(request.user, 'tenant_id', None)
        data = request.data.get('data') or timezone.localdate()

        # Caminho único de escrita (web + WhatsApp): modulodiario.services.
        diario = registrar_contribuicao(
            obra=obra,
            funcionario=funcionario,
            texto=texto or None,
            arquivo=arquivo or None,
            descricao=request.data.get('descricao') or '',
            eh_ocorrencia=_str_to_bool(request.data.get('eh_ocorrencia')),
            clima=request.data.get('condicoes_climaticas'),
            origem='web',
            data=data,
            criado_por=request.user,
            tenant_id=tenant_id,
        )

        diario.refresh_from_db()
        serializer = self.get_serializer(diario)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EntradaDiarioViewSet(TenantScopedViewSetMixin,
                           mixins.ListModelMixin,
                           mixins.RetrieveModelMixin,
                           mixins.UpdateModelMixin,
                           mixins.DestroyModelMixin,
                           viewsets.GenericViewSet):
    """
    Entradas de texto. Criação é via DiarioObraViewSet.contribuir. Edição e
    exclusão exigem responsável técnico (PodeModerarDiario, por objeto).
    """
    queryset = EntradaDiario.objects.all().select_related('autor', 'diario_obra__obra')
    serializer_class = EntradaDiarioSerializer
    permission_classes = [IsAuthenticated, PodeModerarDiario]

    def get_queryset(self):
        qs = super().get_queryset()
        diario_id = self.request.query_params.get('diario_obra')
        if diario_id:
            qs = qs.filter(diario_obra_id=diario_id)
        return qs


class DocumentoDiarioViewSet(TenantScopedViewSetMixin,
                             mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.DestroyModelMixin,
                             viewsets.GenericViewSet):
    """
    Documentos (fotos) do diário. Criação é via contribuir (web) ou pelo canal
    WhatsApp (Fase C). Exclusão exige responsável técnico.
    """
    queryset = DocumentoDiario.objects.all().select_related('autor', 'diario_obra__obra', 'analise_ia')
    serializer_class = DocumentoDiarioSerializer
    permission_classes = [IsAuthenticated, PodeModerarDiario]

    def get_queryset(self):
        qs = super().get_queryset()
        diario_id = self.request.query_params.get('diario_obra')
        if diario_id:
            qs = qs.filter(diario_obra_id=diario_id)
        return qs


# ─── Views de análise de IA (consumidas pela galeria do frontend) ──────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def documentos_com_analise(request):
    """Lista documentos de imagem, indicando o status da análise de IA."""
    try:
        AnaliseImagemIA = None
        try:
            from funcoesia.models import AnaliseImagemIA
        except ImportError:
            pass

        obra_id = request.GET.get('obra')
        status_filter = request.GET.get('status')

        query = Q()
        if obra_id:
            query &= Q(diario_obra__obra__obra_id=obra_id)

        documentos = DocumentoDiario.objects.select_related(
            'diario_obra', 'diario_obra__obra', 'autor'
        ).filter(query, arquivo__isnull=False).order_by('-data_criacao')

        extensoes_imagem = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
        status_mapping = {
            'concluido': 'completa', 'em_processamento': 'em_andamento',
            'pendente': 'pendente', 'erro': 'erro',
        }

        documentos_data = []
        for documento in documentos:
            if not (documento.arquivo and documento.arquivo.name.lower().endswith(extensoes_imagem)):
                continue

            analise = None
            if AnaliseImagemIA is not None:
                try:
                    analise = AnaliseImagemIA.objects.filter(
                        documento_id=documento.documento_diario_id
                    ).order_by('-data_criacao').first()
                except Exception:
                    analise = None

            nome_arquivo = documento.arquivo.name.split('/')[-1]
            obra_nome = documento.diario_obra.obra.nome_obra if (documento.diario_obra and documento.diario_obra.obra) else 'Sem obra'

            status_analise = 'sem_analise'
            data_analise = None
            resultado_analise = None
            if analise:
                status_analise = status_mapping.get(analise.status, analise.status)
                data_analise = analise.data_criacao
                resultado_analise = analise.resultado_analise

            if status_filter and status_analise != status_filter:
                continue

            documentos_data.append({
                'id': documento.documento_diario_id,
                'nome': nome_arquivo,
                'nome_original': documento.descricao or nome_arquivo,
                'nome_arquivo': nome_arquivo,
                'obra_nome': obra_nome,
                'autor_nome': documento.autor.nome_completo if documento.autor else None,
                'descricao': documento.descricao or nome_arquivo,
                'data_criacao': documento.data_criacao,
                'status_analise': status_analise,
                'data_analise': data_analise,
                'resultado_analise': resultado_analise,
                'tipo_analise': 'completa',
                'url_imagem': documento.arquivo.url if documento.arquivo else None,
                'tem_analise': analise is not None,
            })

        return Response({'total': len(documentos_data), 'documentos': documentos_data})

    except Exception as e:
        return Response({'error': f'Erro interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalhes_documento_analise(request, documento_id):
    """Detalhe de um documento com sua análise."""
    try:
        AnaliseImagemIA = None
        try:
            from funcoesia.models import AnaliseImagemIA
        except ImportError:
            pass

        documento = DocumentoDiario.objects.select_related(
            'diario_obra', 'diario_obra__obra', 'autor'
        ).get(documento_diario_id=documento_id)

        analise = None
        if AnaliseImagemIA is not None:
            try:
                analise = AnaliseImagemIA.objects.filter(
                    documento_id=documento.documento_diario_id
                ).order_by('-data_criacao').first()
            except Exception:
                analise = None

        if not analise:
            return Response({'error': 'Este documento não possui análise de IA'}, status=status.HTTP_404_NOT_FOUND)

        nome_arquivo = documento.arquivo.name.split('/')[-1] if documento.arquivo else 'Sem arquivo'
        obra_nome = documento.diario_obra.obra.nome_obra if (documento.diario_obra and documento.diario_obra.obra) else 'Sem obra'
        status_mapping = {
            'concluido': 'completa', 'em_processamento': 'em_andamento',
            'pendente': 'pendente', 'erro': 'erro',
        }

        return Response({
            'id': documento.documento_diario_id,
            'nome': nome_arquivo,
            'nome_original': documento.descricao or nome_arquivo,
            'nome_arquivo': nome_arquivo,
            'obra_nome': obra_nome,
            'autor_nome': documento.autor.nome_completo if documento.autor else None,
            'descricao': documento.descricao,
            'data_criacao': documento.data_criacao,
            'status_analise': status_mapping.get(analise.status, analise.status),
            'data_analise': analise.data_criacao,
            'resultado': analise.resultado_analise,
            'resultado_analise': analise.resultado_analise,
            'url_imagem': documento.arquivo.url if documento.arquivo else None,
            'tem_analise': True,
        })

    except DocumentoDiario.DoesNotExist:
        return Response({'error': 'Documento não encontrado'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': f'Erro interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reprocessar_analise(request):
    """Reprocessa a análise de IA de um documento."""
    documento_id = request.data.get('documento_id')
    tipo_analise = request.data.get('tipo_analise', 'completa')
    if not documento_id:
        return JsonResponse({'error': 'documento_id é obrigatório'}, status=400)
    try:
        DocumentoDiario.objects.get(documento_diario_id=documento_id)
    except DocumentoDiario.DoesNotExist:
        return JsonResponse({'error': 'Documento não encontrado'}, status=404)
    disparar_analise_ia.delay(documento_id=documento_id, tipo_analise=tipo_analise)
    return JsonResponse({
        'success': True, 'message': 'Reprocessamento iniciado', 'documento_id': documento_id,
        'tipo_analise': tipo_analise,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def status_analise(request, documento_id):
    """Status atual da análise de IA de um documento."""
    try:
        documento = DocumentoDiario.objects.get(documento_diario_id=documento_id)
    except DocumentoDiario.DoesNotExist:
        return JsonResponse({'error': 'Documento não encontrado'}, status=404)

    analise = getattr(documento, 'analise_ia', None)
    if analise is None:
        return JsonResponse({'documento_id': documento_id, 'tem_analise': False,
                             'message': 'Nenhuma análise encontrada para este documento'})
    return JsonResponse({
        'documento_id': documento_id, 'tem_analise': True,
        'analise': {
            'status': analise.status,
            'data_criacao': analise.data_criacao,
            'data_atualizacao': analise.data_atualizacao,
            'tem_resultado': analise.resultado_analise is not None,
            'resultado': analise.resultado_analise,
        },
    })
