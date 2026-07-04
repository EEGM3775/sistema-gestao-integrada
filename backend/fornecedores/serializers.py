# backend/fornecedores/serializers.py
# Converte os modelos do app 'fornecedores' para o formato JSON para a API.
from rest_framework import serializers
from .models import (
    Fornecedor,
    DadoBancarioFornecedor,
    ProdutoServicoFornecedor
)

class FornecedorSerializer(serializers.ModelSerializer):
    cnpj = serializers.CharField(
        max_length=18, allow_null=True, allow_blank=True, required=False
    )

    class Meta:
        model = Fornecedor
        fields = '__all__'

class DadoBancarioFornecedorSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DadoBancarioFornecedor.
    """
    class Meta:
        model = DadoBancarioFornecedor
        fields = '__all__'

class ProdutoServicoFornecedorSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ProdutoServicoFornecedor.
    """
    class Meta:
        model = ProdutoServicoFornecedor
        fields = '__all__'
