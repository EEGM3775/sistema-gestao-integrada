# backend/empreendimentos/serializers.py
# Este arquivo contém os serializadores para o aplicativo 'empreendimentos'.
# Serializadores convertem objetos complexos, como instâncias de modelos Django,
# em tipos de dados nativos do Python que podem ser facilmente renderizados em JSON para a API.

from rest_framework import serializers
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from .models import (
    Empreendimento,
    ContaBancariaEmpreendimento,
    CustoEmpreendimento
)

class EmpreendimentoSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo Empreendimento.
    A classe Meta especifica o modelo a ser serializado e os campos a serem incluídos.
    """
    class Meta:
        model = Empreendimento
        fields = '__all__'  # '__all__' é um atalho para incluir todos os campos do modelo.

class ContaBancariaEmpreendimentoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaBancariaEmpreendimento.
    Converte os dados das contas bancárias dos empreendimentos para JSON.
    """
    class Meta:
        model = ContaBancariaEmpreendimento
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

class CustoEmpreendimentoSerializer(UploadValidationMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo CustoEmpreendimento.
    Converte os dados de custos dos empreendimentos para JSON.
    """
    class Meta:
        model = CustoEmpreendimento
        fields = '__all__'
