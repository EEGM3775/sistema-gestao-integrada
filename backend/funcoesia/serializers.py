# backend/funcoesia/serializers.py
from rest_framework import serializers
from .models import AnaliseImagemIA

class AnaliseImagemIASerializer(serializers.ModelSerializer):
    class Meta:
        model = AnaliseImagemIA
        fields = '__all__'
        read_only_fields = ('documento',) # O documento será associado na view
