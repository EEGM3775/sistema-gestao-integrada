# backend/obras/views.py
# Define a lógica da API (endpoints) para o app 'obras'.
from rest_framework import viewsets
from .models import Obra, EtapaObra, DocumentoObra
from .serializers import (
    ObraSerializer,
    EtapaObraSerializer,
    DocumentoObraSerializer
)

class ObraViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar obras.
    """
    queryset = Obra.objects.all()
    serializer_class = ObraSerializer
    # permission_classes = [permissions.IsAuthenticated]

class EtapaObraViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar etapas de obras.
    """
    queryset = EtapaObra.objects.all()
    serializer_class = EtapaObraSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DocumentoObraViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar documentos de obras.
    """
    queryset = DocumentoObra.objects.all()
    serializer_class = DocumentoObraSerializer
    # permission_classes = [permissions.IsAuthenticated]
