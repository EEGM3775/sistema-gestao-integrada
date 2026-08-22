# backend/rh/serializers.py
# Este arquivo define como os modelos do app 'rh' são convertidos para o formato JSON para a API.
from rest_framework import serializers
from funcoesimpexp.entrega import ArquivoGateadoSerializerMixin
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.field_masking import FieldMaskingSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from .impexp import (
    ESPECIE_ASO,
    ESPECIE_CTPS,
    ESPECIE_DOCUMENTO,
    ESPECIE_HOLERITE,
    RECURSO_ASO,
    RECURSO_DOCUMENTOS,
    RECURSO_HOLERITE,
)
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

class FuncionarioSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, FieldMaskingSerializerMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Ficha do funcionário — PII mascarada por permissão (Fase 9.C).

    Substitui o hack ad-hoc do ``salario_base`` (que checava o nome do papel
    ``rh_financeiro``): agora o CPF exige ``rh.cpf.view`` e o salário exige
    ``rh.folha.view``. Quem só tem ``rh.funcionario.view`` vê o cadastro, mas
    com CPF e salário mascarados — a ficha "para de chover 403".

    **A CTPS é o caso que mostrava o buraco do D70 inteiro numa linha:** o
    serializer mascarava `cpf` e entregava, no mesmo JSON, a URL do PDF da
    carteira de trabalho — onde o CPF está em claro, e sem gate nenhum. A máscara
    protegia o campo e o arquivo passava por baixo dela.
    """
    #: D70 — o campo continua sendo o do modelo (escrita intacta); só a leitura
    #: passa a apontar para a porta única, com `rh.documento.view` na frente.
    arquivos_gateados = {"carteira_trabalho": (RECURSO_DOCUMENTOS, ESPECIE_CTPS)}

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

class ASOFuncionarioSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, serializers.ModelSerializer):
    """ASO — atestado de saúde ocupacional (1 por ano, por exame).

    **Dado de saúde (LGPD art. 11).** O arquivo sai por `rh.dado_medico.view`,
    a mesma permissão que mascara o prontuário no `DadoMedicoFuncionarioSerializer` —
    antes do D70 ele era baixável de `/media/asos_funcionarios/` sem token.
    """
    arquivos_gateados = {"arquivo": (RECURSO_ASO, ESPECIE_ASO)}

    class Meta:
        model = ASOFuncionario
        fields = '__all__'
        read_only_fields = ['tenant']

class DocumentoFuncionarioSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, serializers.ModelSerializer):
    """RG, CPF, CNH, comprovante — a pasta do colaborador, gateada (D70)."""
    arquivos_gateados = {"arquivo": (RECURSO_DOCUMENTOS, ESPECIE_DOCUMENTO)}

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

class FolhaPagamentoSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, FieldMaskingSerializerMixin, serializers.ModelSerializer):
    """Folha de pagamento — valores financeiros mascarados por ``rh.folha.view``.

    O holerite segue o **mesmo** gate dos valores: mascarar `salario_liquido` e
    entregar o PDF que o contém era a mesma incoerência do CPF com a CTPS (D70).
    """
    arquivos_gateados = {"holerite": (RECURSO_HOLERITE, ESPECIE_HOLERITE)}

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
