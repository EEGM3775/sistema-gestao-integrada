# backend/modulodiario/views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
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
            diario = DiarioObra.objects.get(
                usuario_id=usuario_id,
                obra_id=obra_id,
                data=today
            )
            serializer = self.get_serializer(diario)
            return Response(serializer.data)
        except DiarioObra.DoesNotExist:
            return Response(status=404)

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
            tipo_analise='progresso_obra'
        )
