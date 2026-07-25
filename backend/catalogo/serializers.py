# backend/catalogo/serializers.py
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from .models import ComponenteComposicao, Item


class ItemSerializer(TenantScopedModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"
        read_only_fields = ["tenant"]


class ComponenteComposicaoSerializer(TenantScopedModelSerializer):
    item_filho_descricao = serializers.CharField(source="item_filho.descricao", read_only=True)
    item_filho_unidade = serializers.CharField(source="item_filho.unidade", read_only=True)

    class Meta:
        model = ComponenteComposicao
        fields = "__all__"
        read_only_fields = ["tenant"]
