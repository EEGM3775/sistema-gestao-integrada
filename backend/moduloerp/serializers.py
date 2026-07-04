# backend/moduloerp/serializers.py
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from .models import (
    Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto,
    CentroCusto, RateioContaPagar, RateioContaReceber, LoteRemessa, RevisaoBaixa
)

# --- Serializers for API Endpoints ---

class BoletoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Boleto.
    """
    class Meta:
        model = Boleto
        fields = '__all__'

class NotaFiscalServicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaFiscalServico
        fields = '__all__'

class NotaFiscalProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaFiscalProduto
        fields = '__all__'

class TransacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transacao
        fields = '__all__'

class NotaFiscalSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo NotaFiscal.
    """
    class Meta:
        model = NotaFiscal
        fields = '__all__'

class CentroCustoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CentroCusto
        fields = ['centro_custo_id', 'nome', 'codigo', 'empreendimento', 'ativo']


class RateioContaPagarSerializer(serializers.ModelSerializer):
    centro_custo_nome = serializers.CharField(source='centro_custo.nome', read_only=True)

    class Meta:
        model = RateioContaPagar
        fields = ['rateio_id', 'centro_custo', 'centro_custo_nome', 'valor']


class RateioContaReceberSerializer(serializers.ModelSerializer):
    centro_custo_nome = serializers.CharField(source='centro_custo.nome', read_only=True)

    class Meta:
        model = RateioContaReceber
        fields = ['rateio_id', 'centro_custo', 'centro_custo_nome', 'valor']


def _validar_rateios(rateios, valor, campo='rateios'):
    """
    Valida o array de rateio antes de chegar no banco — sem isso, um centro de
    custo repetido só apareceria como IntegrityError (UniqueConstraint) e um
    500 cru, em vez de um 400 com mensagem legível para o formulário.
    """
    if not rateios:
        return

    centros = [r['centro_custo'].pk for r in rateios]
    if len(centros) != len(set(centros)):
        raise serializers.ValidationError({
            campo: _('Cada centro de custo só pode aparecer uma vez no rateio.')
        })

    soma = sum((r['valor'] for r in rateios), Decimal('0'))
    if valor is not None and soma != valor:
        raise serializers.ValidationError({
            campo: _(
                'A soma dos rateios (R$ %(soma)s) deve ser igual ao valor da conta (R$ %(valor)s).'
            ) % {'soma': soma, 'valor': valor}
        })


class ContaPagarSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaPagar.

    Campos de baixa (status, valor_pago, juros, multa, desconto, data_pagamento)
    são somente leitura aqui — só são alterados via a ação `dar_baixa`, que é o
    único caminho (manual ou futuro webhook do Asaas) que mantém esses valores e
    o ledger de Transacao consistentes entre si.
    """
    boletos = BoletoSerializer(many=True, read_only=True)
    rateios = RateioContaPagarSerializer(many=True, required=False)
    total_devido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    saldo_aberto = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = ContaPagar
        fields = [
            'conta_pagar_id', 'fornecedor', 'empreendimento', 'nota_fiscal',
            'descricao', 'valor', 'data_emissao', 'data_vencimento', 'data_agendamento',
            'status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_pagamento',
            'total_devido', 'saldo_aberto', 'rateios', 'boletos',
        ]
        read_only_fields = ['status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_pagamento']

    def validate(self, attrs):
        rateios = attrs.get('rateios')
        valor = attrs.get('valor', getattr(self.instance, 'valor', None))
        _validar_rateios(rateios, valor)
        return attrs

    def create(self, validated_data):
        rateios_data = validated_data.pop('rateios', [])
        conta = super().create(validated_data)
        for rateio in rateios_data:
            RateioContaPagar.objects.create(conta_pagar=conta, tenant=conta.tenant, **rateio)
        return conta

    def update(self, instance, validated_data):
        rateios_data = validated_data.pop('rateios', None)
        conta = super().update(instance, validated_data)
        if rateios_data is not None:
            conta.rateios.all().delete()
            for rateio in rateios_data:
                RateioContaPagar.objects.create(conta_pagar=conta, tenant=conta.tenant, **rateio)
        return conta


class ContaReceberSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaReceber.

    Mesma regra do ContaPagarSerializer: campos de baixa são somente leitura,
    alterados exclusivamente pela ação `dar_baixa`.
    """
    boletos = BoletoSerializer(many=True, read_only=True)
    rateios = RateioContaReceberSerializer(many=True, required=False)
    total_devido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    saldo_aberto = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = ContaReceber
        fields = [
            'conta_receber_id', 'cliente', 'empreendimento',
            'nota_fiscal_recebida', 'nota_fiscal_servico', 'nota_fiscal_produto',
            'descricao', 'valor', 'data_emissao', 'data_vencimento', 'data_agendamento',
            'status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_recebimento',
            'total_devido', 'saldo_aberto', 'rateios', 'boletos',
        ]
        read_only_fields = ['status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_recebimento']

    def validate(self, attrs):
        rateios = attrs.get('rateios')
        valor = attrs.get('valor', getattr(self.instance, 'valor', None))
        _validar_rateios(rateios, valor)
        return attrs

    def create(self, validated_data):
        rateios_data = validated_data.pop('rateios', [])
        conta = super().create(validated_data)
        for rateio in rateios_data:
            RateioContaReceber.objects.create(conta_receber=conta, tenant=conta.tenant, **rateio)
        return conta

    def update(self, instance, validated_data):
        rateios_data = validated_data.pop('rateios', None)
        conta = super().update(instance, validated_data)
        if rateios_data is not None:
            conta.rateios.all().delete()
            for rateio in rateios_data:
                RateioContaReceber.objects.create(conta_receber=conta, tenant=conta.tenant, **rateio)
        return conta


class BaixaSerializer(serializers.Serializer):
    """
    Valida o payload da ação `dar_baixa` — usado tanto pela baixa manual (UI)
    quanto, futuramente, pelo handler de webhook do Asaas (D.1.2), garantindo
    que os dois caminhos cheguem ao model.dar_baixa() com os mesmos tipos/regras.
    """
    valor = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    data = serializers.DateField()
    juros = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, default=Decimal('0'), min_value=Decimal('0'))
    multa = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, default=Decimal('0'), min_value=Decimal('0'))
    desconto = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, default=Decimal('0'), min_value=Decimal('0'))
    meio_pagamento = serializers.CharField(required=False, allow_blank=True, default='')


class RevisaoBaixaSerializer(serializers.ModelSerializer):
    """
    Fila de revisão do financeiro para baixas tentadas em títulos já
    QUITADOS/CANCELADOS (ver `ContaPagar.dar_baixa`/`BaixaRequerRevisao`).
    Somente leitura — a decisão acontece pelas ações `aprovar`/`rejeitar`
    do `RevisaoBaixaViewSet`, nunca por escrita direta nos campos.
    """
    conta_tipo = serializers.SerializerMethodField()
    conta_descricao = serializers.SerializerMethodField()

    class Meta:
        model = RevisaoBaixa
        fields = [
            'revisao_id', 'conta_pagar', 'conta_receber', 'conta_tipo', 'conta_descricao',
            'valor', 'data', 'juros', 'multa', 'desconto', 'meio_pagamento', 'origem', 'motivo',
            'status', 'solicitado_por', 'solicitado_em',
            'revisado_por', 'revisado_em', 'observacao_revisor',
        ]
        read_only_fields = fields

    def get_conta_tipo(self, obj):
        return 'pagar' if obj.conta_pagar_id else 'receber'

    def get_conta_descricao(self, obj):
        conta = obj.conta
        return conta.descricao if conta else ''


class LoteRemessaSerializer(serializers.ModelSerializer):
    """
    Registro do lote de remessa bancária. Geração do arquivo CNAB em si fica
    fora deste serializer — ver nota em models.LoteRemessa sobre o adiamento.
    """
    contas_pagar = serializers.PrimaryKeyRelatedField(many=True, queryset=ContaPagar.objects.all(), required=False)
    contas_resumo = serializers.SerializerMethodField()

    class Meta:
        model = LoteRemessa
        fields = [
            'lote_id', 'status', 'banco', 'data_geracao', 'data_envio',
            'valor_total', 'observacoes', 'contas_pagar', 'contas_resumo',
        ]
        read_only_fields = ['valor_total', 'data_geracao']

    def get_contas_resumo(self, obj):
        return [
            {
                'id': conta.conta_pagar_id,
                'descricao': conta.descricao,
                'fornecedor': conta.fornecedor.razao_social if conta.fornecedor else None,
                'valor': conta.valor,
            }
            for conta in obj.contas_pagar.all()[:50]
        ]

class CobrancaClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo CobrancaCliente.
    """
    class Meta:
        model = CobrancaCliente
        fields = '__all__'

# --- Serializers for Dashboard Aggregations ---

class AgingDataSerializer(serializers.Serializer):
    categoria = serializers.CharField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)

class FluxoCaixaMensalSerializer(serializers.Serializer):
    mes = serializers.DateField()
    receitas = serializers.DecimalField(max_digits=12, decimal_places=2)
    despesas = serializers.DecimalField(max_digits=12, decimal_places=2)

class DashboardERPSerializer(serializers.Serializer):
    agingContasAReceber = AgingDataSerializer(many=True)
    agingContasAPagar = AgingDataSerializer(many=True)
    fluxoDeCaixaMensal = FluxoCaixaMensalSerializer(many=True)
