# obras/filters.py
from django_filters import rest_framework as filters
from django.db.models import Q
from .models import Obra

class ObraFilter(filters.FilterSet):
    membro_id = filters.NumberFilter(method='filter_by_membro')
    empreendimento_id = filters.NumberFilter(field_name='empreendimento')

    class Meta:
        model = Obra
        fields = ['empreendimento', 'empreendimento_id', 'status_obra']

    def filter_by_membro(self, queryset, name, value):
        return queryset.filter(
            Q(responsaveis_tecnicos__funcionario_id=value) | Q(equipe__funcionario_id=value)
        ).distinct()
