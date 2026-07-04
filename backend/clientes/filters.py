# backend/clientes/filters.py
from django_filters import rest_framework as filters
from .models import Cliente, ClienteEmpreendimento, ContratoCliente, DocumentoCliente


class ClienteFilter(filters.FilterSet):
    nome = filters.CharFilter(field_name='nome_completo', lookup_expr='icontains')
    cpf_cnpj = filters.CharFilter(lookup_expr='icontains')
    email = filters.CharFilter(lookup_expr='icontains')
    cidade = filters.CharFilter(lookup_expr='icontains')
    empreendimento = filters.NumberFilter(method='filter_by_empreendimento')

    class Meta:
        model = Cliente
        fields = ['nome', 'cpf_cnpj', 'email', 'estado_civil', 'profissao', 'cidade', 'estado', 'empreendimento']

    def filter_by_empreendimento(self, queryset, name, value):
        return queryset.filter(clienteempreendimento__empreendimento=value).distinct()


class ClienteEmpreendimentoFilter(filters.FilterSet):
    class Meta:
        model = ClienteEmpreendimento
        fields = ['cliente', 'empreendimento', 'condicoes_pagamento']


class ContratoClienteFilter(filters.FilterSet):
    class Meta:
        model = ContratoCliente
        fields = ['cliente', 'empreendimento', 'status_contrato', 'responsavel', 'vendedor']


class DocumentoClienteFilter(filters.FilterSet):
    class Meta:
        model = DocumentoCliente
        fields = ['cliente', 'tipo_documento']
