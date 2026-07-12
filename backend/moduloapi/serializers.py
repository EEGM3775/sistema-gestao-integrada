# backend/moduloapi/serializers.py
from rest_framework import serializers
from .models import GoogleAccount

class GoogleAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleAccount
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)
