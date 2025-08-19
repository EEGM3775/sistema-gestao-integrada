# backend/clientes/serializers.py
from rest_framework import serializers
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente
)

class ClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Cliente.
    """
    class Meta:
        model = Cliente
        fields = '__all__'

class ClienteEmpreendimentoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ClienteEmpreendimento.
    """
    class Meta:
        model = ClienteEmpreendimento
        fields = '__all__'

class ContratoClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContratoCliente.
    """
    class Meta:
        model = ContratoCliente
        fields = '__all__'

class DocumentoClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DocumentoCliente.
    """
    class Meta:
        model = DocumentoCliente
        fields = '__all__'

class DadoBancarioClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DadoBancarioCliente.
    """
    class Meta:
        model = DadoBancarioCliente
        fields = '__all__'
