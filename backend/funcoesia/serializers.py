# backend/funcoesia/serializers.py
from rest_framework import serializers
from .models import AnaliseImagemIA

class AnaliseImagemIASerializer(serializers.ModelSerializer):
    class Meta:
        model = AnaliseImagemIA
        fields = '__all__'
        # Removido read_only_fields para permitir criação com documento
