# backend/obras/serializers.py
# Converte os modelos do app 'obras' para o formato JSON para a API.
from rest_framework import serializers
from .models import Obra, EtapaObra, DocumentoObra

class ObraSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Obra.
    """
    class Meta:
        model = Obra
        fields = '__all__'

class EtapaObraSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo EtapaObra.
    """
    class Meta:
        model = EtapaObra
        fields = '__all__'

class DocumentoObraSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DocumentoObra.
    """
    class Meta:
        model = DocumentoObra
        fields = '__all__'
