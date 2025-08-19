# backend/modulodiario/serializers.py
from rest_framework import serializers
from .models import DiarioObra, DocumentoDiario

class DocumentoDiarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoDiario
        fields = '__all__'

class DiarioObraSerializer(serializers.ModelSerializer):
    documentos = DocumentoDiarioSerializer(many=True, read_only=True)

    class Meta:
        model = DiarioObra
        fields = '__all__'
