# backend/fornecedores/serializers.py
# Converte os modelos do app 'fornecedores' para o formato JSON para a API.
from django.db.models import Q
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

    emails_adicionais = serializers.ListField(
        child=serializers.EmailField(max_length=255), required=False, allow_empty=True,
    )

    class Meta:
        model = Fornecedor
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2)

    def validate(self, attrs):
        # Principal + adicionais formam um conjunto: sem repetir dentro do
        # fornecedor nem em outro do mesmo tenant.
        atual = self.instance
        principal = (attrs.get('email', atual.email if atual else '') or '').strip().lower()
        extras = [e.strip().lower() for e in attrs.get(
            'emails_adicionais', atual.emails_adicionais if atual else [])]
        todos = ([principal] if principal else []) + extras
        if len(set(todos)) != len(todos):
            raise serializers.ValidationError({'emails_adicionais': ['E-mail repetido.']})
        if todos:
            request = self.context.get('request')
            tenant_id = getattr(getattr(request, 'user', None), 'tenant_id', None)
            outros = Fornecedor.objects.all()
            if tenant_id is not None:
                outros = outros.filter(tenant_id=tenant_id)
            if atual:
                outros = outros.exclude(pk=atual.pk)
            for e in todos:
                if outros.filter(Q(email__iexact=e) | Q(emails_adicionais__contains=[e])).exists():
                    campo = 'email' if e == principal else 'emails_adicionais'
                    raise serializers.ValidationError({campo: ['E-mail já cadastrado.']})
        if 'emails_adicionais' in attrs:
            attrs['emails_adicionais'] = extras  # minúsculas: é o que a busca por contains compara
        return attrs


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