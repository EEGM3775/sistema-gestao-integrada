# backend/clientes/serializers.py
from rest_framework import serializers
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente
)


class ClienteSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = '__all__'
        read_only_fields = ['cliente_id', 'data_cadastro', 'tenant']


class ClienteEmpreendimentoSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)
    empreendimento_nome = serializers.CharField(source='empreendimento.empreendimento', read_only=True)

    class Meta:
        model = ClienteEmpreendimento
        fields = '__all__'
        read_only_fields = ['cliente_empreendimento_id', 'tenant']


class ContratoClienteSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)
    empreendimento_nome = serializers.CharField(source='empreendimento.empreendimento', read_only=True)
    responsavel_nome = serializers.CharField(source='responsavel.nome_completo', read_only=True, default=None)
    vendedor_nome = serializers.CharField(source='vendedor.razao_social', read_only=True, default=None)

    class Meta:
        model = ContratoCliente
        fields = '__all__'
        read_only_fields = ['contrato_cliente_id', 'tenant']


class DocumentoClienteSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)
    tipo_documento_display = serializers.CharField(source='get_tipo_documento_display', read_only=True)

    class Meta:
        model = DocumentoCliente
        fields = '__all__'
        read_only_fields = ['documento_cliente_id', 'data_upload', 'tenant']


class DadoBancarioClienteSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)

    class Meta:
        model = DadoBancarioCliente
        fields = '__all__'
        read_only_fields = ['data_atualizacao', 'tenant']
