# backend/funcoesia/serializers.py
from rest_framework import serializers
from .models import AnaliseImagemIA

class AnaliseImagemIASerializer(serializers.ModelSerializer):
    class Meta:
        model = AnaliseImagemIA
        fields = '__all__'
        read_only_fields = ['tenant']  # tenant injetado pelo perform_create (D3); documento segue gravável
