# backend/moduloapi/serializers.py
from rest_framework import serializers
from .models import GoogleAccount

class GoogleAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleAccount
        fields = '__all__'
