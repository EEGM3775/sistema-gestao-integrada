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

from .listao import filtro_de_faixa, filtro_de_mes, hoje_local
from .models import (
    Transacao, ContaPagar, ContaReceber, CobrancaCliente, Boleto,
    NotaFiscalServico,
)


class _FiltrosDoListao(filters.FilterSet):
    """Os filtros que abrem um grupo da grade (listao.py): cada dimensão de
    agrupamento tem o seu, senão clicar no grupo não saberia pedir as linhas dele."""
    faixa = filters.CharFilter(method="filtrar_faixa")
    mes = filters.CharFilter(method="filtrar_mes")

    def filtrar_faixa(self, queryset, name, value):
        return queryset.filter(filtro_de_faixa(value, hoje_local()))

    def filtrar_mes(self, queryset, name, value):
        return queryset.filter(filtro_de_mes(value))


class NotaFiscalServicoFilter(filters.FilterSet):
    """
    Filtro das NFS-e emitidas. Além do `status` exato, expõe `excluir_status`
    para as abas da tela de Notas Fiscais (D.1.3): "Emitidas" exclui `CANCELADA`;
    "Canceladas" filtra por ela — sem precisar de duas rotas nem de duplicar
    canceladas nas duas abas.
    """
    excluir_status = filters.CharFilter(field_name='status', exclude=True)

    class Meta:
        model = NotaFiscalServico
        fields = ['status']


class TransacaoFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_transacao', lookup_expr='date__gte')
    data_ate = filters.DateFilter(field_name='data_transacao', lookup_expr='date__lte')

    class Meta:
        model = Transacao
        fields = ['tipo', 'empreendimento', 'obra', 'conta_pagar', 'conta_receber', 'data_de', 'data_ate']


class ContaPagarFilter(_FiltrosDoListao):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')

    class Meta:
        model = ContaPagar
        fields = ['fornecedor', 'empreendimento', 'obra', 'etapa', 'status', 'data_de', 'data_ate']


class ContaReceberFilter(_FiltrosDoListao):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')
    quadra = filters.CharFilter(field_name='cliente_empreendimento__unidade__quadra', lookup_expr='iexact')

    class Meta:
        model = ContaReceber
        fields = ['cliente', 'empreendimento', 'obra', 'status', 'data_de', 'data_ate']


class CobrancaClienteFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')

    class Meta:
        model = CobrancaCliente
        fields = ['cliente', 'contrato', 'status', 'forma_pagamento', 'data_de', 'data_ate']


class BoletoFilter(filters.FilterSet):
    data_de = filters.DateFilter(field_name='data_vencimento', lookup_expr='gte')
    data_ate = filters.DateFilter(field_name='data_vencimento', lookup_expr='lte')
    # Abas da tela de Boletos: "Ativos" exclui CANCELADO; "Cancelados" filtra por
    # ele (mesmo padrão do NotaFiscalServicoFilter) — sem duas rotas.
    excluir_status = filters.CharFilter(field_name='status', exclude=True)
    # Os eixos da grade (listao.py): abrir o grupo "cliente X" ou "mar/2026"
    # pede as linhas por eles.
    cliente = filters.NumberFilter(field_name='conta_receber__cliente')
    empreendimento = filters.NumberFilter(field_name='conta_receber__empreendimento')
    mes = filters.CharFilter(method='filtrar_mes')

    class Meta:
        model = Boleto
        fields = ['status', 'conta_receber', 'conta_pagar', 'data_de', 'data_ate']

    def filtrar_mes(self, queryset, name, value):
        return queryset.filter(filtro_de_mes(value))
