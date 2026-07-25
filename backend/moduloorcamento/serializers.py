# backend/moduloorcamento/serializers.py
"""Serializers da base referencial.

`ModelSerializer` puro, e **não** `TenantScopedModelSerializer`: estes modelos não
têm `tenant` (base pública de plataforma — ver `models.py`). Todos são de
leitura; a escrita é do comando de importação.
"""
from rest_framework import serializers

from .models import BaseReferencial, ComposicaoReferenciaItem, InsumoReferencia


class BaseReferencialSerializer(serializers.ModelSerializer):
    rotulo_exibicao = serializers.SerializerMethodField()
    fonte_nome = serializers.CharField(source="get_fonte_display", read_only=True)
    regime_nome = serializers.CharField(source="get_regime_encargos_display", read_only=True)

    class Meta:
        model = BaseReferencial
        fields = "__all__"

    def get_rotulo_exibicao(self, obj) -> str:
        return obj.rotulo or obj.rotulo_automatico()


class InsumoReferenciaSerializer(serializers.ModelSerializer):
    base_rotulo = serializers.SerializerMethodField()
    base_fonte = serializers.CharField(source="base.fonte", read_only=True)
    base_mes = serializers.DateField(source="base.mes_referencia", read_only=True)
    # Sinaliza na lista o que já existe no catálogo da empresa, para a tela não
    # oferecer "adotar" no que já foi adotado. Preenchido pela view (um SELECT
    # por página, não um por linha).
    adotado_item_id = serializers.SerializerMethodField()

    class Meta:
        model = InsumoReferencia
        fields = "__all__"

    def get_base_rotulo(self, obj) -> str:
        return obj.base.rotulo or obj.base.rotulo_automatico()

    def get_adotado_item_id(self, obj):
        adotados = self.context.get("adotados") or {}
        return adotados.get((obj.base.fonte, obj.codigo))


class ComposicaoReferenciaItemSerializer(serializers.ModelSerializer):
    filho_codigo = serializers.CharField(source="filho.codigo", read_only=True)
    filho_descricao = serializers.CharField(source="filho.descricao", read_only=True)
    filho_unidade = serializers.CharField(source="filho.unidade", read_only=True)
    filho_tipo = serializers.CharField(source="filho.tipo", read_only=True)
    filho_custo_unitario = serializers.DecimalField(
        source="filho.custo_unitario", max_digits=14, decimal_places=4, read_only=True
    )
    custo_no_item = serializers.SerializerMethodField()

    class Meta:
        model = ComposicaoReferenciaItem
        fields = "__all__"

    def get_custo_no_item(self, obj) -> str:
        """Coeficiente × custo do filho — a parcela deste insumo no custo da
        composição. É a memória de cálculo que a composição analítica entrega e a
        sintética não."""
        return str((obj.coeficiente * obj.filho.custo_unitario).quantize(obj.filho.custo_unitario))
