# backend/moduloorcamento/serializers.py
"""Serializers do módulo.

Duas famílias, pela mesma fronteira que divide `models.py`:

- **Base referencial** — `ModelSerializer` puro, e **não**
  `TenantScopedModelSerializer`: estes modelos não têm `tenant` (base pública de
  plataforma). Todos de leitura; a escrita é do comando de importação.
- **Planilha (ORC.1+)** — `TenantScopedModelSerializer`, com `tenant` read-only
  sistêmico (D3) e unicidade por-tenant (Fase 8.3).
"""
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from .models import (
    BaseReferencial,
    ComposicaoReferenciaItem,
    InsumoReferencia,
    ItemOrcado,
    Orcamento,
    RevisaoOrcamento,
)


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


# ---------------------------------------------------------------------------
# ORC.1 — planilha orçamentária
# ---------------------------------------------------------------------------


class ItemOrcadoSerializer(TenantScopedModelSerializer):
    """Linha da planilha.

    Os totais são **read-only por desenho**: quem os calcula é
    `planilha.recalcular_orcamento`, não o cliente. Aceitar total do cliente
    abriria a porta para uma planilha cujo somatório não bate com as linhas —
    exatamente o que um sistema de orçamento existe para impedir.
    """

    total_custo_direto = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_com_bdi = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    codigo_eap = serializers.CharField(read_only=True)
    etapa_nome = serializers.CharField(source="etapa.nome_etapa", read_only=True, default=None)
    item_codigo = serializers.CharField(source="item.codigo_interno", read_only=True, default=None)
    tipo_linha_nome = serializers.CharField(source="get_tipo_linha_display", read_only=True)

    class Meta:
        model = ItemOrcado
        fields = "__all__"

    def validate(self, attrs):
        """Duas regras que o banco não tem como impor sozinho."""
        orcamento = attrs.get("orcamento") or getattr(self.instance, "orcamento", None)
        pai = attrs.get("pai") or getattr(self.instance, "pai", None)
        if pai is not None and orcamento is not None and pai.orcamento_id != orcamento.orcamento_id:
            raise serializers.ValidationError(
                {"pai": "A linha-pai precisa ser do mesmo orçamento."}
            )
        etapa = attrs.get("etapa") or getattr(self.instance, "etapa", None)
        if etapa is not None and orcamento is not None and etapa.obra_id != orcamento.obra_id:
            raise serializers.ValidationError(
                {"etapa": "A etapa precisa pertencer à obra do orçamento."}
            )
        return attrs


class OrcamentoSerializer(TenantScopedModelSerializer):
    """Cabeçalho do orçamento. Os totais vêm desnormalizados do recálculo."""

    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    status_nome = serializers.CharField(source="get_status_display", read_only=True)
    base_rotulo = serializers.SerializerMethodField()
    custo_direto_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    valor_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    editavel = serializers.BooleanField(read_only=True)
    total_itens = serializers.SerializerMethodField()

    class Meta:
        model = Orcamento
        fields = "__all__"
        read_only_fields = ["aprovado_em", "aprovado_por_nome", "versao", "orcamento_origem"]

    def get_base_rotulo(self, obj) -> str | None:
        if obj.base_referencial_id is None:
            return None
        return obj.base_referencial.rotulo or obj.base_referencial.rotulo_automatico()

    def get_total_itens(self, obj) -> int:
        return getattr(obj, "itens_count", None) or obj.itens.count()

    def create(self, validated_data):
        """A data-base nasce colada na publicação escolhida.

        Copiar em vez de ler pela FK é deliberado (`models.Orcamento`): a
        publicação pode ser desativada ou substituída, e o orçamento precisa
        continuar dizendo de que mês era o preço que ele congelou.
        """
        base = validated_data.get("base_referencial")
        if base is not None and not validated_data.get("data_base"):
            validated_data["data_base"] = base.mes_referencia
        if base is not None and not validated_data.get("regime_encargos"):
            validated_data["regime_encargos"] = base.regime_encargos
        return super().create(validated_data)


class RevisaoOrcamentoSerializer(TenantScopedModelSerializer):
    tipo_nome = serializers.CharField(source="get_tipo_display", read_only=True)
    delta = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    orcamento_versao = serializers.IntegerField(source="orcamento.versao", read_only=True)

    class Meta:
        model = RevisaoOrcamento
        fields = "__all__"
