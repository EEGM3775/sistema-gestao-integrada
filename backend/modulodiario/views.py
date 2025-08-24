# backend/modulodiario/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.db.models import Q
from .models import DiarioObra, DocumentoDiario
from .serializers import DiarioObraSerializer, DocumentoDiarioSerializer
from .tasks import disparar_analise_ia
from .permissions import IsResponsavelTecnicoDaObra

class DiarioObraViewSet(viewsets.ModelViewSet):
    queryset = DiarioObra.objects.all()
    serializer_class = DiarioObraSerializer
    permission_classes = [permissions.IsAuthenticated, IsResponsavelTecnicoDaObra]

    def perform_create(self, serializer):
        # Validação de permissão antes de criar
        permission = IsResponsavelTecnicoDaObra()
        if not permission.has_permission_for_create(self.request, serializer):
            self.permission_denied(self.request, message="Você não é um responsável técnico desta obra.")
        
        serializer.save(usuario=self.request.user)

    @action(detail=False, methods=['get'])
    def today(self, request):
        usuario_id = request.query_params.get('usuario_id')
        obra_id = request.query_params.get('obra_id')
        today = timezone.now().date()

        if not usuario_id or not obra_id:
            return Response({'error': 'usuario_id e obra_id são obrigatórios'}, status=400)

        try:
            # Buscar todos os diários para hoje
            diarios = DiarioObra.objects.filter(
                usuario_id=usuario_id,
                obra_id=obra_id,
                data=today
            ).order_by('-data_criacao')  # Ordenar pelo mais recente primeiro

            if diarios.count() == 0:
                return Response({'exists': False, 'message': 'Nenhum diário encontrado para hoje'}, status=404)
            elif diarios.count() == 1:
                # Um diário encontrado - comportamento normal
                serializer = self.get_serializer(diarios.first())
                return Response({
                    'exists': True, 
                    'diario': serializer.data,
                    'multiple': False
                })
            else:
                # Múltiplos diários encontrados - retornar lista para seleção
                serializer = self.get_serializer(diarios, many=True)
                return Response({
                    'exists': True,
                    'multiple': True,
                    'count': diarios.count(),
                    'diarios': serializer.data,
                    'message': f'Encontrados {diarios.count()} diários para hoje. Selecione um para continuar.'
                })

        except Exception as e:
            return Response({'error': str(e)}, status=500)

    @action(detail=True, methods=['get'])
    def documentos_com_analise(self, request, pk=None):
        """
        Retorna todos os documentos de um diário com suas respectivas análises de IA.
        """
        try:
            diario = self.get_object()
            documentos = diario.documentos.all()
            
            documentos_data = []
            for doc in documentos:
                doc_data = DocumentoDiarioSerializer(doc).data
                
                # Adicionar informações da análise de IA se existir
                try:
                    analise = doc.analise_ia
                    doc_data['analise_ia'] = {
                        'analise_id': analise.analise_ia_id,
                        'status': analise.status,
                        'resultado': analise.resultado_analise,
                        'data_criacao': analise.data_criacao,
                        'data_atualizacao': analise.data_atualizacao
                    }
                except:
                    doc_data['analise_ia'] = None
                
                documentos_data.append(doc_data)
            
            return Response({
                'diario_id': diario.diario_obra_id,
                'documentos': documentos_data
            })
            
        except Exception as e:
            return Response({'error': str(e)}, status=500)

class DocumentoDiarioViewSet(viewsets.ModelViewSet):
    queryset = DocumentoDiario.objects.all()
    serializer_class = DocumentoDiarioSerializer

    def perform_create(self, serializer):
        """
        Salva o documento e depois enfileira a tarefa para disparar o gatilho de IA.
        """
        documento = serializer.save()
        disparar_analise_ia.delay(
            documento_id=documento.documento_diario_id,
            tipo_analise='completa'
        )

    @action(detail=True, methods=['post'])
    def reprocessar_analise(self, request, pk=None):
        """
        Reprocessa a análise de IA para um documento específico.
        Permite escolher o tipo de análise.
        """
        try:
            documento = self.get_object()
            tipo_analise = request.data.get('tipo_analise', 'completa')
            
            # Verificar se existe uma análise anterior
            analise_anterior = None
            try:
                analise_anterior = documento.analise_ia
                status_anterior = analise_anterior.status
                resultado_anterior = analise_anterior.resultado_analise
            except:
                status_anterior = 'sem_analise'
                resultado_anterior = None
            
            # Disparar nova análise
            disparar_analise_ia.delay(
                documento_id=documento.documento_diario_id,
                tipo_analise=tipo_analise
            )
            
            return Response({
                'message': 'Reprocessamento da análise iniciado com sucesso',
                'documento_id': documento.documento_diario_id,
                'tipo_analise': tipo_analise,
                'status_anterior': status_anterior,
                'tem_analise_anterior': analise_anterior is not None
            }, status=status.HTTP_202_ACCEPTED)
            
        except DocumentoDiario.DoesNotExist:
            return Response({
                'error': 'Documento não encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': f'Erro ao reprocessar análise: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def status_analise(self, request, pk=None):
        """
        Retorna o status atual da análise de IA para um documento.
        """
        try:
            documento = self.get_object()
            
            try:
                analise = documento.analise_ia
                return Response({
                    'documento_id': documento.documento_diario_id,
                    'tem_analise': True,
                    'analise': {
                        'analise_id': analise.analise_ia_id,
                        'status': analise.status,
                        'data_criacao': analise.data_criacao,
                        'data_atualizacao': analise.data_atualizacao,
                        'tem_resultado': analise.resultado_analise is not None,
                        'resultado': analise.resultado_analise
                    }
                })
            except:
                return Response({
                    'documento_id': documento.documento_diario_id,
                    'tem_analise': False,
                    'message': 'Nenhuma análise encontrada para este documento'
                })
                
        except DocumentoDiario.DoesNotExist:
            return Response({
                'error': 'Documento não encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """
        Lista documentos com informações adicionais para seleção de nova análise
        """
        queryset = self.get_queryset().select_related(
            'diario_obra', 'diario_obra__obra'
        ).order_by('-data_criacao')
        
        # Filtrar apenas documentos com arquivo de imagem
        queryset = queryset.filter(arquivo__isnull=False)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer_data = []
            for doc in page:
                data = self.get_serializer(doc).data
                
                # Adicionar informações da obra
                if doc.diario_obra and doc.diario_obra.obra:
                    data['obra_nome'] = doc.diario_obra.obra.nome_obra
                    data['obra_id'] = doc.diario_obra.obra.obra_id
                else:
                    data['obra_nome'] = None
                    data['obra_id'] = None
                
                # Verificar se tem análise existente
                try:
                    analise = doc.analise_ia
                    data['tem_analise'] = True
                    data['status_analise'] = analise.status
                except:
                    data['tem_analise'] = False
                    data['status_analise'] = None
                
                # Verificar se é imagem
                if doc.arquivo:
                    arquivo_lower = doc.arquivo.name.lower()
                    extensoes_imagem = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
                    data['eh_imagem'] = any(arquivo_lower.endswith(ext) for ext in extensoes_imagem)
                else:
                    data['eh_imagem'] = False
                
                if data['eh_imagem']:
                    serializer_data.append(data)
            
            return self.get_paginated_response(serializer_data)
        
        # Sem paginação
        serializer_data = []
        for doc in queryset:
            data = self.get_serializer(doc).data
            
            # Adicionar informações da obra
            if doc.diario_obra and doc.diario_obra.obra:
                data['obra_nome'] = doc.diario_obra.obra.nome_obra
                data['obra_id'] = doc.diario_obra.obra.obra_id
            else:
                data['obra_nome'] = None
                data['obra_id'] = None
            
            # Verificar se tem análise existente
            try:
                analise = doc.analise_ia
                data['tem_analise'] = True
                data['status_analise'] = analise.status
            except:
                data['tem_analise'] = False
                data['status_analise'] = None
            
            # Verificar se é imagem
            if doc.arquivo:
                arquivo_lower = doc.arquivo.name.lower()
                extensoes_imagem = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
                data['eh_imagem'] = any(arquivo_lower.endswith(ext) for ext in extensoes_imagem)
            else:
                data['eh_imagem'] = False
            
            if data['eh_imagem']:
                serializer_data.append(data)
        
        return Response(serializer_data)


# Function-based views para análises de IA

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def documentos_com_analise(request):
    """Lista todos os documentos de imagem, indicando se possuem análise de IA"""
    try:
        # Tentar importar o modelo de análise IA
        AnaliseImagemIA = None
        try:
            from funcoesia.models import AnaliseImagemIA
        except ImportError as e:
            print(f"Aviso: Modelo AnaliseImagemIA não disponível: {e}")
        
        # Filtrar por obra se especificado
        obra_id = request.GET.get('obra')
        status_filter = request.GET.get('status')
        
        query = Q()
        if obra_id:
            query &= Q(diario_obra__obra__obra_id=obra_id)
        
        # Buscar todos os documentos com arquivo de imagem
        documentos = DocumentoDiario.objects.select_related(
            'diario_obra', 'diario_obra__obra'
        ).filter(
            query, arquivo__isnull=False
        ).order_by('-data_criacao')
        
        # Filtrar apenas imagens
        documentos_filtrados = []
        for doc in documentos:
            if doc.arquivo and doc.arquivo.name:
                arquivo_lower = doc.arquivo.name.lower()
                extensoes_imagem = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
                if any(arquivo_lower.endswith(ext) for ext in extensoes_imagem):
                    documentos_filtrados.append(doc)
        
        documentos_data = []
        
        for documento in documentos_filtrados:
            # Buscar a análise mais recente se o modelo estiver disponível
            analise_recente = None
            if AnaliseImagemIA is not None:
                try:
                    analise_recente = AnaliseImagemIA.objects.filter(
                        documento_id=documento.documento_diario_id
                    ).order_by('-data_criacao').first()
                except Exception as e:
                    print(f"Erro ao buscar análise para documento {documento.documento_diario_id}: {e}")
            
            # Extrair nome do arquivo
            nome_arquivo = documento.arquivo.name.split('/')[-1] if documento.arquivo else 'Sem arquivo'
            
            # Nome da obra
            obra_nome = 'Sem obra'
            if documento.diario_obra and documento.diario_obra.obra:
                obra_nome = documento.diario_obra.obra.nome_obra
            
            # Status da análise
            status_analise = 'sem_analise'
            data_analise = None
            resultado_analise = None
            tipo_analise = None
            
            if analise_recente:
                # Mapear status do modelo para o frontend
                status_mapping = {
                    'concluido': 'completa',
                    'em_processamento': 'em_andamento',
                    'pendente': 'pendente',
                    'erro': 'erro'
                }
                status_analise = status_mapping.get(analise_recente.status, analise_recente.status)
                data_analise = analise_recente.data_criacao
                
                # Converter resultado JSON para string se necessário
                resultado_analise = analise_recente.resultado_analise
                if isinstance(resultado_analise, dict):
                    import json
                    resultado_analise = json.dumps(resultado_analise, indent=2, ensure_ascii=False)
                
                tipo_analise = getattr(analise_recente, 'tipo_analise', 'Análise Padrão')
            
            # Aplicar filtro de status se especificado
            if status_filter and status_analise != status_filter:
                continue
            
            documento_data = {
                'id': documento.documento_diario_id,
                'nome': nome_arquivo,
                'nome_original': documento.descricao or nome_arquivo,  # Nome original/descrição
                'nome_arquivo': nome_arquivo,  # Nome do arquivo
                'obra_nome': obra_nome,
                'descricao': documento.descricao or nome_arquivo,
                'data_criacao': documento.data_criacao,
                'status_analise': status_analise,
                'data_analise': data_analise,
                'resultado_analise': resultado_analise,
                'tipo_analise': tipo_analise,
                'url_imagem': documento.arquivo.url if documento.arquivo else None,
                'tem_analise': analise_recente is not None
            }
            
            documentos_data.append(documento_data)
        
        return Response({
            'total': len(documentos_data),
            'documentos': documentos_data
        })
        
    except Exception as e:
        import traceback
        error_message = f'Erro interno: {str(e)}'
        print(f"Erro em documentos_com_analise: {error_message}")
        print(f"Traceback: {traceback.format_exc()}")
        
        return Response(
            {'error': error_message}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalhes_documento_analise(request, documento_id):
    """Busca detalhes de um documento específico com sua análise"""
    try:
        # Tentar importar o modelo de análise IA
        AnaliseImagemIA = None
        try:
            from funcoesia.models import AnaliseImagemIA
        except ImportError:
            pass
            
        documento = DocumentoDiario.objects.select_related(
            'diario_obra', 'diario_obra__obra'
        ).get(documento_diario_id=documento_id)
        
        # Buscar análise se disponível
        analise_recente = None
        if AnaliseImagemIA is not None:
            try:
                analise_recente = AnaliseImagemIA.objects.filter(
                    documento_id=documento.documento_diario_id
                ).order_by('-data_criacao').first()
            except Exception:
                pass
        
        if not analise_recente:
            return Response(
                {'error': 'Este documento não possui análise de IA'}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Extrair informações do documento
        nome_arquivo = documento.arquivo.name.split('/')[-1] if documento.arquivo else 'Sem arquivo'
        obra_nome = 'Sem obra'
        if documento.diario_obra and documento.diario_obra.obra:
            obra_nome = documento.diario_obra.obra.nome_obra
        
        # Mapear status
        status_mapping = {
            'concluido': 'completa',
            'em_processamento': 'em_andamento',
            'pendente': 'pendente',
            'erro': 'erro'
        }
        status_analise = status_mapping.get(analise_recente.status, analise_recente.status)
        
        # Preparar resultado da análise
        resultado_analise = analise_recente.resultado_analise
        
        documento_data = {
            'id': documento.documento_diario_id,
            'nome': nome_arquivo,
            'nome_original': documento.descricao or nome_arquivo,
            'nome_arquivo': nome_arquivo,
            'obra_nome': obra_nome,
            'descricao': documento.descricao,
            'data_criacao': documento.data_criacao,
            'status_analise': status_analise,
            'data_analise': analise_recente.data_criacao,
            'resultado': resultado_analise,  # Manter como JSON para processamento no frontend
            'resultado_analise': resultado_analise,
            'url_imagem': documento.arquivo.url if documento.arquivo else None,
            'tem_analise': True
        }
        
        return Response(documento_data)
            
    except DocumentoDiario.DoesNotExist:
        return Response(
            {'error': 'Documento não encontrado'}, 
            status=status.HTTP_404_NOT_FOUND
        )
        
    except Exception as e:
        import traceback
        print(f"Erro em detalhes_documento_analise: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return Response(
            {'error': f'Erro interno: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def reprocessar_analise(request):
    """
    Reprocessa a análise de IA para um documento específico.
    """
    try:
        documento_id = request.data.get('documento_id')
        tipo_analise = request.data.get('tipo_analise', 'completa')
        
        if not documento_id:
            return JsonResponse({
                'error': 'documento_id é obrigatório'
            }, status=400)
        
        # Verificar se o documento existe
        try:
            documento = DocumentoDiario.objects.get(
                documento_diario_id=documento_id
            )
        except DocumentoDiario.DoesNotExist:
            return JsonResponse({
                'error': 'Documento não encontrado'
            }, status=404)
        
        # Disparar nova análise
        disparar_analise_ia.delay(
            documento_id=documento_id,
            tipo_analise=tipo_analise
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Reprocessamento iniciado com sucesso',
            'documento_id': documento_id,
            'tipo_analise': tipo_analise
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Erro ao reprocessar análise: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def status_analise(request, documento_id):
    """
    Retorna o status atual da análise de IA para um documento.
    """
    try:
        # Verificar se o documento existe
        try:
            documento = DocumentoDiario.objects.get(
                documento_diario_id=documento_id
            )
        except DocumentoDiario.DoesNotExist:
            return JsonResponse({
                'error': 'Documento não encontrado'
            }, status=404)
        
        # Buscar análise do documento
        try:
            analise = documento.analise_ia
            
            return JsonResponse({
                'documento_id': documento_id,
                'tem_analise': True,
                'analise': {
                    'status': analise.status,
                    'tipo_analise': getattr(analise, 'tipo_analise', None),
                    'data_criacao': analise.data_criacao,
                    'data_atualizacao': analise.data_atualizacao,
                    'tem_resultado': analise.resultado_analise is not None,
                    'resultado': analise.resultado_analise
                }
            })
            
        except AttributeError:
            return JsonResponse({
                'documento_id': documento_id,
                'tem_analise': False,
                'message': 'Nenhuma análise encontrada para este documento'
            })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Erro ao verificar status: {str(e)}'
        }, status=500)
