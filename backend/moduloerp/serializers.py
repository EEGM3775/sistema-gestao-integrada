# backend/moduloerp/serializers.py
from rest_framework import serializers
from .models import (
    Fatura, Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto
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

class FaturaSerializer(serializers.ModelSerializer):
    transacoes = TransacaoSerializer(many=True, read_only=True)
    nota_fiscal_servico = NotaFiscalServicoSerializer(read_only=True)
    nota_fiscal_produto = NotaFiscalProdutoSerializer(read_only=True)

    class Meta:
        model = Fatura
        fields = (
            'fatura_id', 'tipo', 'status', 'descricao', 'valor', 
            'data_emissao', 'data_vencimento', 'data_pagamento', 'empreendimento', 
            'cliente', 'fornecedor', 'transacoes', 
            'nota_fiscal_servico', 'nota_fiscal_produto', 'nota_fiscal_recebida'
        )

class NotaFiscalSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo NotaFiscal.
    """
    class Meta:
        model = NotaFiscal
        fields = '__all__'

class ContaPagarSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaPagar.
    """
    boletos = BoletoSerializer(many=True, read_only=True)

    class Meta:
        model = ContaPagar
        fields = [f.name for f in model._meta.fields] + ['boletos']

class ContaReceberSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaReceber.
    """
    boletos = BoletoSerializer(many=True, read_only=True)

    class Meta:
        model = ContaReceber
        fields = [f.name for f in model._meta.fields] + ['boletos']

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