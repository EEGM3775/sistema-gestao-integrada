# backend/clientes/serializers.py

from rest_framework import serializers
from funcoesimpexp.entrega import ArquivoGateadoSerializerMixin
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.field_masking import FieldMaskingSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from . import plano_pagamento
from .impexp import (
    ESPECIE_DOCUMENTO as ESPECIE_DOCUMENTO_CLIENTE,
    RECURSO_DOCUMENTOS as RECURSO_DOCUMENTOS_CLIENTE,
)
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente,
    MeioPagamento,
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

    def validate_email(self, valor):
        # A constraint ignora e-mail vazio, então o validador automático some:
        # a duplicata é checada aqui, no campo.
        if not valor:
            return valor
        request = self.context.get('request')
        tenant_id = getattr(getattr(request, 'user', None), 'tenant_id', None)
        outros = Cliente.objects.filter(email__iexact=valor)
        if tenant_id is not None:
            outros = outros.filter(tenant_id=tenant_id)
        if self.instance:
            outros = outros.exclude(pk=self.instance.pk)
        if outros.exists():
            raise serializers.ValidationError('E-mail já cadastrado.')
        return valor


class MeioPagamentoSerializer(serializers.ModelSerializer):
    """Um meio de pagamento da venda. A ordem é a da lista enviada, e quem diz
    quais campos o tipo comporta é o motor (`plano_pagamento.TIPOS_DE_MEIO`)."""

    class Meta:
        model = MeioPagamento
        fields = [
            'meio_pagamento_id', 'ordem', 'tipo', 'valor', 'descricao', 'parcelas',
            'primeiro_vencimento', 'juros_mensal', 'sistema_amortizacao', 'periodicidade',
            'cronograma',
        ]
        read_only_fields = ['meio_pagamento_id', 'ordem']
        # Nas datas livres o valor sai da soma das linhas (o motor recalcula).
        extra_kwargs = {'valor': {'required': False}}


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
    # A lista livre de meios de pagamento. No PATCH, mandá-la **substitui** a
    # lista inteira (é um documento, não linhas soltas); omiti-la mantém a
    # gravada.
    meios = MeioPagamentoSerializer(many=True, required=False)
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
        # A condição também: ela é o rótulo que os meios dão à venda
        # (`plano_pagamento.condicao_da_venda`), não uma escolha à parte.
        read_only_fields = [
            'cliente_empreendimento_id', 'tenant', 'valor_tabela', 'valor_compra',
            'valor_total_plano', 'parcelas_geradas_em', 'condicoes_pagamento',
        ]

    def get_plano(self, obj):
        """O resumo da proposta, recalculado do que está gravado — sem o carnê
        inteiro, que é grande e a ficha pede à parte quando precisa.

        **Sem calendário bancário de propósito** (`ajustar_vencimento=None`).
        O ajuste de dia útil só mexe em *datas*, e aqui nenhuma data é exibida —
        o resumo é dinheiro e contagem. Ligá-lo custaria uma consulta de feriados
        e uma de `Local` **por linha** da lista de aquisições, para um resultado
        idêntico. O carnê datado sai pelo `/simular/`, que é onde as datas
        importam.
        """
        try:
            plano = plano_pagamento.montar_da_aquisicao(obj, ajustar_vencimento=None)
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
        é quem diz se fecha (desconto maior que a tabela, meios que não somam o
        valor negociado, permuta sem descrição)."""
        dados = {**({} if not self.instance else _dados_da_instancia(self.instance)), **attrs}
        unidade = dados.get('unidade')
        if unidade is not None and 'unidade' in attrs:
            # Trocou de unidade (ou é venda nova): o preço de tabela é o dela,
            # tirado agora. Reprecificar a unidade amanhã não mexe neste contrato.
            dados['valor_tabela'] = unidade.valor_base
            attrs['valor_tabela'] = unidade.valor_base
        if 'meios' in attrs:
            origem = attrs['meios']
        else:
            origem = list(self.instance.meios.all()) if self.instance else []
        try:
            # Lidos pelo motor: é ele que apaga o que cada tipo não comporta
            # (juros num FGTS, prazo numa permuta). O que se grava é o lido, não
            # o enviado — senão a ficha mostraria o que o carnê ignora.
            meios = [plano_pagamento.meio_de(m, i) for i, m in enumerate(origem, start=1)]
            plano = plano_pagamento.montar(
                valor_tabela=dados.get('valor_tabela') or 0,
                desconto_percentual=dados.get('desconto_percentual') or 0,
                desconto_valor=dados.get('desconto_valor') or 0,
                meios=meios,
                data_compra=dados.get('data_compra'),
            )
        except ValueError as erro:
            raise serializers.ValidationError({'meios': str(erro)})
        # Derivados gravados: o que a carteira soma e filtra, e a ficha mostra
        # sem recalcular.
        attrs['valor_compra'] = plano.valor_negociado
        attrs['valor_total_plano'] = plano.total
        attrs['condicoes_pagamento'] = plano.condicao
        if 'meios' in attrs or not self.instance:
            attrs['meios'] = [vars(m) for m in meios]
        return attrs

    def _gravar_meios(self, aquisicao, meios):
        aquisicao.meios.all().delete()
        MeioPagamento.objects.bulk_create([
            MeioPagamento(tenant_id=aquisicao.tenant_id, aquisicao=aquisicao, ordem=ordem, **dados)
            for ordem, dados in enumerate(meios, start=1)
        ])

    def create(self, validated_data):
        meios = validated_data.pop('meios', [])
        unidade = validated_data['unidade']
        validated_data['empreendimento'] = unidade.empreendimento
        aquisicao = super().create(validated_data)
        self._gravar_meios(aquisicao, meios)
        _marcar_unidade_vendida(unidade)
        return aquisicao

    def update(self, instance, validated_data):
        meios = validated_data.pop('meios', None)
        anterior = instance.unidade
        aquisicao = super().update(instance, validated_data)
        if meios is not None:
            self._gravar_meios(aquisicao, meios)
        if aquisicao.unidade_id != anterior.pk:
            _liberar_unidade(anterior)
            _marcar_unidade_vendida(aquisicao.unidade)
        return aquisicao


def _dados_da_instancia(instancia) -> dict:
    """Os campos do plano como estão gravados — base do PATCH parcial, que só
    manda o que mudou e ainda assim precisa ser validado inteiro."""
    campos = (
        'unidade', 'valor_tabela', 'desconto_percentual', 'desconto_valor', 'data_compra',
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


class DocumentoClienteSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, serializers.ModelSerializer):
    """RG, CPF, CNH e comprovante do titular — o arquivo sai gateado (D70)."""
    arquivos_gateados = {"arquivo": (RECURSO_DOCUMENTOS_CLIENTE, ESPECIE_DOCUMENTO_CLIENTE)}

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