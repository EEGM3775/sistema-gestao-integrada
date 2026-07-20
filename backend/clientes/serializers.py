# backend/clientes/serializers.py
from rest_framework import serializers
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.field_masking import FieldMaskingSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente
)


class ClienteSerializer(FieldMaskingSerializerMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Cliente — CPF/CNPJ mascarado por permissão (Fase 9.C / LGPD)."""
    class Meta:
        model = Cliente
        fields = '__all__'
        read_only_fields = ['cliente_id', 'data_cadastro', 'tenant']

    # CPF/CNPJ do cliente é PII de leitura (permissão dedicada, concedível a quem
    # trata documentos do cliente). A escrita é do cadastro (`cadastro.cliente.edit`,
    # gate do endpoint) — não travada aqui, senão o comercial não criaria cliente.
    sensitive_fields = {
        "cpf_cnpj": "cadastro.cliente_doc.view",
    }


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


class DocumentoClienteSerializer(UploadValidationMixin, serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)
    tipo_documento_display = serializers.CharField(source='get_tipo_documento_display', read_only=True)

    class Meta:
        model = DocumentoCliente
        fields = '__all__'
        read_only_fields = ['documento_cliente_id', 'data_upload', 'tenant']


class DadoBancarioClienteSerializer(FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Dados bancários do cliente — PII sensível (LGPD). Mascarada por permissão."""
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)

    class Meta:
        model = DadoBancarioCliente
        fields = '__all__'
        read_only_fields = ['data_atualizacao', 'tenant']

    sensitive_fields = {
        "agencia": "cadastro.cliente_banco.view",
        "conta": "cadastro.cliente_banco.view",
        "titular_cpf_cnpj": "cadastro.cliente_banco.view",
        "chave_pix": "cadastro.cliente_banco.view",
    }
    write_protected_fields = {
        "agencia": "cadastro.cliente_banco.edit",
        "conta": "cadastro.cliente_banco.edit",
        "titular_cpf_cnpj": "cadastro.cliente_banco.edit",
        "chave_pix": "cadastro.cliente_banco.edit",
    }