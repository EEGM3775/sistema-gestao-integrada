# backend/moduloerp/filters.py
"""
Filtros server-side do ERP financeiro.

Padrão de filtro unificado (docs/modulos/moduloerp.md §5.1): todo listão
financeiro aceita os mesmos eixos — período (data_de/data_ate), obra/
empreendimento, cliente, fornecedor e status — para que o frontend monte uma
única `FilterBar` reaproveitada em todas as telas (o "seletor de camada" vira
barra de filtro, não telas duplicadas).
"""
from django_filters import rest_framework as filters

from .models import (
    Transacao, ContaPagar, ContaReceber, CobrancaCliente, Boleto,
)


class TransacaoFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_transacao', lookup_expr='date__gte')
    data_ate = filters.DateFilter(field_name='data_transacao', lookup_expr='date__lte')

    class Meta:
        model = Transacao
        fields = ['tipo', 'empreendimento', 'obra', 'conta_pagar', 'conta_receber', 'data_de', 'data_ate']


class ContaPagarFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')

    class Meta:
        model = ContaPagar
        fields = ['fornecedor', 'empreendimento', 'status', 'data_de', 'data_ate']


class ContaReceberFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')

    class Meta:
        model = ContaReceber
        fields = ['cliente', 'empreendimento', 'status', 'data_de', 'data_ate']


class CobrancaClienteFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')

    class Meta:
        model = CobrancaCliente
        fields = ['cliente', 'contrato', 'status', 'forma_pagamento', 'data_de', 'data_ate']


class BoletoFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')

    class Meta:
        model = Boleto
        fields = ['status', 'conta_receber', 'conta_pagar', 'data_de', 'data_ate']
