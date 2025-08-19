# backend/modulodiario/views.py
from rest_framework import viewsets
from .models import DiarioObra, DocumentoDiario
from .serializers import DiarioObraSerializer, DocumentoDiarioSerializer
from .tasks import disparar_analise_ia

class DiarioObraViewSet(viewsets.ModelViewSet):
    queryset = DiarioObra.objects.all()
    serializer_class = DiarioObraSerializer

class DocumentoDiarioViewSet(viewsets.ModelViewSet):
    queryset = DocumentoDiario.objects.all()
    serializer_class = DocumentoDiarioSerializer

    def perform_create(self, serializer):
        """
        Salva o documento e depois enfileira a tarefa para disparar o gatilho de IA.
        """
        documento = serializer.save()
        # Dispara a tarefa em background, especificando o tipo de análise.
        disparar_analise_ia.delay(
            documento_id=documento.documento_diario_id,
            tipo_analise='progresso_obra'
        )
