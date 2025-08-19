# backend/funcoesia/views.py
from rest_framework import viewsets, mixins
from .models import AnaliseImagemIA
from .serializers import AnaliseImagemIASerializer

class AnaliseImagemIAViewSet(mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               viewsets.GenericViewSet):
    """
    ViewSet para criar e atualizar análises de IA.
    - `POST`: Cria uma nova análise (usado pelo trigger).
    - `PATCH`: Atualiza uma análise (usado pelo microserviço de IA).
    - `GET`: Visualiza uma análise.
    Não permite listagem ou deleção via API.
    """
    queryset = AnaliseImagemIA.objects.all()
    serializer_class = AnaliseImagemIASerializer
