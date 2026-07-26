# backend/clientes/serializers.py
from decimal import Decimal

from rest_framework import serializers
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.field_masking import FieldMaskingSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from . import plano_pagamento
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
    """A venda de uma unidade: qual unidade, por quanto e em que condições.

    O `empreendimento` **não** é escrito pelo cliente da API — sai da unidade
    escolhida. Aceitá-lo permitiria gravar uma aquisição cujo empreendimento
    contradiz o da unidade, e nenhuma tela mostraria a contradição.
    """
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)
    empreendimento = serializers.PrimaryKeyRelatedField(read_only=True)
    empreendimento_nome = serializers.CharField(source='empreendimento.empreendimento', read_only=True)
    # Como a unidade se identifica na tela — montado no cadastro da unidade, que
    # é a fonte única: grade, extrato, ficha e contrato leem do mesmo lugar.
    rotulo_unidade = serializers.CharField(read_only=True)
    unidade_valor_base = serializers.DecimalField(
        source='unidade.valor_base', max_digits=15, decimal_places=2, read_only=True,
    )
    plano = serializers.SerializerMethodField()
    indice_correcao_codigo = serializers.CharField(
        source='indice_correcao.codigo', read_only=True, default=None,
    )
    indice_correcao_nome = serializers.CharField(
        source='indice_correcao.nome', read_only=True, default=None,
    )

    class Meta:
        model = ClienteEmpreendimento
        fields = '__all__'
        # Os três valores são **derivados**, nunca digitados: `valor_tabela` é o
        # preço da unidade no dia da venda (snapshot), e negociado/total saem do
        # motor de cálculo. Aceitá-los do cliente da API permitiria gravar um
        # contrato cujo total não bate com o próprio plano — e nada na tela
        # denunciaria a diferença.
        read_only_fields = [
            'cliente_empreendimento_id', 'tenant', 'valor_tabela', 'valor_compra',
            'valor_total_plano', 'parcelas_geradas_em',
        ]

    def get_plano(self, obj):
        """O resumo da proposta, recalculado do que está gravado — sem o carnê
        inteiro, que é grande e a ficha pede à parte quando precisa."""
        try:
            plano = plano_pagamento.montar_da_aquisicao(obj)
        except ValueError:
            return None
        resumo = plano.como_dict()
        resumo.pop('parcelas')
        return resumo

    def validate_unidade(self, unidade):
        """Duas unidades já vendidas não podem virar a mesma venda de novo, e a
        unidade de outro tenant não existe para quem pergunta."""
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant_id', None)
        if tenant and unidade.tenant_id != tenant:
            raise serializers.ValidationError("Unidade não encontrada.")
        ja_vendida = ClienteEmpreendimento.objects.filter(unidade=unidade)
        if self.instance:
            ja_vendida = ja_vendida.exclude(pk=self.instance.pk)
        if ja_vendida.exists():
            raise serializers.ValidationError(
                "Esta unidade já tem uma aquisição registrada. Cancele a anterior para revendê-la."
            )
        return unidade

    def validate(self, attrs):
        """A proposta precisa fechar antes de virar contrato — o motor de cálculo
        é quem diz se fecha (desconto maior que a tabela, entrada maior que o
        negociado, saldo sem parcela)."""
        dados = {**({} if not self.instance else _dados_da_instancia(self.instance)), **attrs}
        unidade = dados.get('unidade')
        if unidade is not None and 'unidade' in attrs:
            # Trocou de unidade (ou é venda nova): o preço de tabela é o dela,
            # tirado agora. Reprecificar a unidade amanhã não mexe neste contrato.
            dados['valor_tabela'] = unidade.valor_base
            attrs['valor_tabela'] = unidade.valor_base
        try:
            plano = plano_pagamento.montar(
                valor_tabela=dados.get('valor_tabela') or 0,
                desconto_percentual=dados.get('desconto_percentual') or 0,
                desconto_valor=dados.get('desconto_valor') or 0,
                entrada_valor=dados.get('entrada_valor') or 0,
                entrada_parcelas=dados.get('entrada_parcelas') or 1,
                entrada_primeiro_vencimento=dados.get('entrada_primeiro_vencimento'),
                sistema=dados.get('sistema_amortizacao') or 'price',
                juros_mensal=dados.get('juros_mensal') or 0,
                num_parcelas=dados.get('num_parcelas') or 0,
                primeiro_vencimento=dados.get('primeiro_vencimento'),
                balao_valor=dados.get('balao_valor') or 0,
                balao_quantidade=dados.get('balao_quantidade') or 0,
                balao_periodicidade=dados.get('balao_periodicidade') or 'anual',
                balao_primeiro_vencimento=dados.get('balao_primeiro_vencimento'),
                data_compra=dados.get('data_compra'),
                a_vista=dados.get('condicoes_pagamento') == 'a_vista',
            )
        except ValueError as erro:
            raise serializers.ValidationError({'plano': str(erro)})
        # Derivados gravados: o que a carteira soma e a ficha mostra sem recalcular.
        attrs['valor_compra'] = plano.valor_negociado
        attrs['valor_total_plano'] = plano.total
        # À vista não tem prazo: zerar o que a condição anterior deixou para trás
        # impede que uma venda convertida de "financiamento" para "à vista" fique
        # com 60 parcelas gravadas que o plano não reconhece mais.
        if dados.get('condicoes_pagamento') == 'a_vista':
            attrs.update(
                entrada_valor=plano.valor_negociado, entrada_parcelas=1,
                num_parcelas=0, juros_mensal=Decimal('0'),
                balao_valor=Decimal('0'), balao_quantidade=0,
                primeiro_vencimento=None, balao_primeiro_vencimento=None,
            )
        return attrs

    def create(self, validated_data):
        unidade = validated_data['unidade']
        validated_data['empreendimento'] = unidade.empreendimento
        aquisicao = super().create(validated_data)
        _marcar_unidade_vendida(unidade)
        return aquisicao

    def update(self, instance, validated_data):
        anterior = instance.unidade
        aquisicao = super().update(instance, validated_data)
        if aquisicao.unidade_id != anterior.pk:
            _liberar_unidade(anterior)
            _marcar_unidade_vendida(aquisicao.unidade)
        return aquisicao


def _dados_da_instancia(instancia) -> dict:
    """Os campos do plano como estão gravados — base do PATCH parcial, que só
    manda o que mudou e ainda assim precisa ser validado inteiro."""
    campos = (
        'unidade', 'valor_tabela', 'desconto_percentual', 'desconto_valor', 'entrada_valor',
        'entrada_parcelas', 'entrada_primeiro_vencimento', 'sistema_amortizacao', 'juros_mensal',
        'num_parcelas', 'primeiro_vencimento', 'balao_valor', 'balao_quantidade',
        'balao_periodicidade', 'balao_primeiro_vencimento', 'data_compra',
        # A condição entra aqui porque ela **é** parte do plano: sem ela, um
        # PATCH que só mexe no desconto reavaliaria uma venda à vista como se
        # fosse parcelada.
        'condicoes_pagamento',
    )
    return {campo: getattr(instancia, campo) for campo in campos}


def _marcar_unidade_vendida(unidade):
    if unidade.situacao != 'vendida':
        unidade.situacao = 'vendida'
        unidade.save(update_fields=['situacao', 'data_atualizacao'])


def _liberar_unidade(unidade):
    if not unidade.aquisicoes.exists():
        unidade.situacao = 'disponivel'
        unidade.save(update_fields=['situacao', 'data_atualizacao'])


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