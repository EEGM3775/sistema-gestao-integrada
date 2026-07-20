# backend/rh/serializers.py
# Este arquivo define como os modelos do app 'rh' são convertidos para o formato JSON para a API.
from rest_framework import serializers
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.field_masking import FieldMaskingSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from .models import (
    Cargo,
    Funcionario,
    DadoMedicoFuncionario,
    ASOFuncionario,
    DocumentoFuncionario,
    DadoBancarioFuncionario,
    PagamentoFuncionario,
    FolhaPagamento
)

class CargoSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo Cargo.
    Define os campos que serão incluídos na representação da API.
    """
    class Meta:
        model = Cargo
        fields = '__all__' # Inclui todos os campos do modelo.
        # `tenant` é injetado pelo perform_create (Fase 8.2 o tornou NOT NULL →
        # DRF o exigiria no payload); read-only para não travar a criação.
        read_only_fields = ['tenant']

class FuncionarioSerializer(UploadValidationMixin, FieldMaskingSerializerMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Ficha do funcionário — PII mascarada por permissão (Fase 9.C).

    Substitui o hack ad-hoc do ``salario_base`` (que checava o nome do papel
    ``rh_financeiro``): agora o CPF exige ``rh.cpf.view`` e o salário exige
    ``rh.folha.view``. Quem só tem ``rh.funcionario.view`` vê o cadastro, mas
    com CPF e salário mascarados — a ficha "para de chover 403".
    """
    class Meta:
        model = Funcionario
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2)

    # Leitura: CPF e salário mascarados por permissão.
    sensitive_fields = {
        "cpf": "rh.cpf.view",
        "salario_base": "rh.folha.view",
    }
    # Escrita: só o salário é protegido (tem `.edit` concedível). O CPF faz parte
    # do cadastro — sua escrita é governada pelo gate do endpoint
    # (`rh.funcionario.edit`); protegê-lo aqui travaria a criação da ficha.
    write_protected_fields = {
        "salario_base": "rh.folha.edit",
    }

class DadoMedicoFuncionarioSerializer(FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Prontuário/ASO — PII médica sensível (LGPD). Mascarada por permissão."""
    class Meta:
        model = DadoMedicoFuncionario
        fields = '__all__'
        read_only_fields = ['tenant']

    sensitive_fields = {
        "numero_cartao_sus": "rh.dado_medico.view",
        "alergias": "rh.dado_medico.view",
        "medicamentos": "rh.dado_medico.view",
        "historico_doencas": "rh.dado_medico.view",
        "contato_emergencia_telefone": "rh.dado_medico.view",
        "observacoes_medicas": "rh.dado_medico.view",
    }

class ASOFuncionarioSerializer(UploadValidationMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo ASOFuncionario (registros de exame ocupacional, 1 por ano).
    """
    class Meta:
        model = ASOFuncionario
        fields = '__all__'
        read_only_fields = ['tenant']

class DocumentoFuncionarioSerializer(UploadValidationMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo DocumentoFuncionario.
    """
    class Meta:
        model = DocumentoFuncionario
        fields = '__all__'
        read_only_fields = ['tenant']

class DadoBancarioFuncionarioSerializer(FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Dados bancários do funcionário — PII sensível (LGPD). Mascarada por permissão."""
    class Meta:
        model = DadoBancarioFuncionario
        fields = '__all__'
        read_only_fields = ['tenant']

    sensitive_fields = {
        "agencia": "rh.dado_bancario.view",
        "conta": "rh.dado_bancario.view",
        "titular_cpf_cnpj": "rh.dado_bancario.view",
        "chave_pix": "rh.dado_bancario.view",
    }

class PagamentoFuncionarioSerializer(FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Pagamentos — valores financeiros mascarados por ``rh.folha.view``."""
    class Meta:
        model = PagamentoFuncionario
        fields = '__all__'
        read_only_fields = ['tenant']

    sensitive_fields = {
        "salario_base": "rh.folha.view",
        "salario_liquido": "rh.folha.view",
        "descontos": "rh.folha.view",
        "adicionais": "rh.folha.view",
        "extras": "rh.folha.view",
        "bonus": "rh.folha.view",
    }

class FolhaPagamentoSerializer(UploadValidationMixin, FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Folha de pagamento — valores financeiros mascarados por ``rh.folha.view``."""
    class Meta:
        model = FolhaPagamento
        fields = '__all__'
        read_only_fields = ['tenant']

    sensitive_fields = {
        "salario_bruto": "rh.folha.view",
        "salario_liquido": "rh.folha.view",
        "total_descontos": "rh.folha.view",
        "total_proventos": "rh.folha.view",
    }
