# backend/financeiro/serializers.py
# Este arquivo define como os modelos do app 'financeiro' são convertidos para o formato JSON.
from rest_framework import serializers
from .models import (
    NotaFiscal,
    ContaPagar,
    ContaReceber,
    CobrancaCliente
)

class NotaFiscalSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo NotaFiscal.
    """
    class Meta:
        model = NotaFiscal
        fields = '__all__'  # Inclui todos os campos do modelo na API.

class ContaPagarSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaPagar.
    """
    class Meta:
        model = ContaPagar
        fields = '__all__'

class ContaReceberSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaReceber.
    """
    class Meta:
        model = ContaReceber
        fields = '__all__'

class CobrancaClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo CobrancaCliente.
    """
    class Meta:
        model = CobrancaCliente
        fields = '__all__'