# backend/fornecedores/serializers.py
# Converte os modelos do app 'fornecedores' para o formato JSON para a API.
from rest_framework import serializers
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.field_masking import FieldMaskingSerializerMixin
from .models import (
    Fornecedor,
    DadoBancarioFornecedor,
    ProdutoServicoFornecedor
)

class FornecedorSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Fornecedor. O **CNPJ não é mascarado** — dado público de pessoa jurídica
    (não PII de pessoa natural); mascará-lo travava o cadastro sem ganho LGPD."""
    cnpj = serializers.CharField(
        max_length=18, allow_null=True, allow_blank=True, required=False
    )

    class Meta:
        model = Fornecedor
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2)

class DadoBancarioFornecedorSerializer(FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Dados bancários do fornecedor — sensível. Mascarada + escrita protegida."""
    class Meta:
        model = DadoBancarioFornecedor
        fields = '__all__'
        read_only_fields = ['tenant']

    sensitive_fields = {
        "agencia": "cadastro.fornecedor_banco.view",
        "conta": "cadastro.fornecedor_banco.view",
        "chave_pix": "cadastro.fornecedor_banco.view",
    }
    write_protected_fields = {
        "agencia": "cadastro.fornecedor_banco.edit",
        "conta": "cadastro.fornecedor_banco.edit",
        "chave_pix": "cadastro.fornecedor_banco.edit",
    }

class ProdutoServicoFornecedorSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ProdutoServicoFornecedor.
    """
    class Meta:
        model = ProdutoServicoFornecedor
        fields = '__all__'
        read_only_fields = ['tenant']