# backend/clientes/filters.py
from django_filters import rest_framework as filters
from nucleo import autorizacao
from .models import Cliente, ClienteEmpreendimento, ContratoCliente, DocumentoCliente


class ClienteFilter(filters.FilterSet):
    nome = filters.CharFilter(field_name='nome_completo', lookup_expr='icontains')
    cpf_cnpj = filters.CharFilter(method='filtrar_documento')
    email = filters.CharFilter(lookup_expr='icontains')
    cidade = filters.CharFilter(lookup_expr='icontains')
    empreendimento = filters.NumberFilter(method='filter_by_empreendimento')

    class Meta:
        model = Cliente
        fields = ['nome', 'cpf_cnpj', 'email', 'estado_civil', 'profissao', 'cidade', 'estado', 'empreendimento']

    def filter_by_empreendimento(self, queryset, name, value):
        return queryset.filter(clienteempreendimento__empreendimento=value).distinct()

    def filtrar_documento(self, queryset, name, value):
        """Sem `cadastro.cliente_doc.view` o CPF não é critério: a resposta vem
        vazia para qualquer valor, então não diz se o documento existe (D257)."""
        usuario = getattr(self.request, 'user', None)
        if usuario is None or not autorizacao.pode(usuario, 'cadastro.cliente_doc.view'):
            return queryset.none()
        return queryset.filter(cpf_cnpj__icontains=value)


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
