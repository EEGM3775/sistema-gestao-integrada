# backend/rh/serializers.py
# Este arquivo define como os modelos do app 'rh' são convertidos para o formato JSON para a API.
from rest_framework import serializers
from .models import (
    Cargo,
    Funcionario,
    DadoMedicoFuncionario,
    DocumentoFuncionario,
    DadoBancarioFuncionario,
    PagamentoFuncionario,
    FolhaPagamento
)

class CargoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Cargo.
    Define os campos que serão incluídos na representação da API.
    """
    class Meta:
        model = Cargo
        fields = '__all__' # Inclui todos os campos do modelo.

class FuncionarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Funcionário.
    """
    class Meta:
        model = Funcionario
        fields = '__all__'

class DadoMedicoFuncionarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DadoMedicoFuncionario.
    """
    class Meta:
        model = DadoMedicoFuncionario
        fields = '__all__'

class DocumentoFuncionarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DocumentoFuncionario.
    """
    class Meta:
        model = DocumentoFuncionario
        fields = '__all__'

class DadoBancarioFuncionarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo DadoBancarioFuncionario.
    """
    class Meta:
        model = DadoBancarioFuncionario
        fields = '__all__'

class PagamentoFuncionarioSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo PagamentoFuncionario.
    """
    class Meta:
        model = PagamentoFuncionario
        fields = '__all__'

class FolhaPagamentoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo FolhaPagamento.
    """
    class Meta:
        model = FolhaPagamento
        fields = '__all__'