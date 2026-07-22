# backend/moduloscm/serializers.py
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from .models import (
    AvaliacaoFornecedor,
    CentroCusto,
    Cotacao,
    Demanda,
    FaixaPrecoOferta,
    ItemDemanda,
    ItemPedido,
    ItemProposta,
    ItemRecebimento,
    OfertaFornecedor,
    PedidoCompra,
    Produto,
    Proposta,
    Recebimento,
)


class CentroCustoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = CentroCusto
        fields = "__all__"
        read_only_fields = ["tenant"]


class ProdutoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = Produto
        fields = "__all__"
        read_only_fields = ["tenant"]


class OfertaFornecedorSerializer(TenantScopedModelSerializer):
    # Rótulos denormalizados (read-only) — a lista de ofertas mostra produto e
    # fornecedor sem uma segunda ida à API (padrão de listagem de marketplace).
    produto_descricao = serializers.CharField(source="produto.descricao", read_only=True)
    produto_codigo = serializers.CharField(source="produto.codigo_interno", read_only=True)
    produto_unidade = serializers.CharField(source="produto.unidade", read_only=True)
    fornecedor_nome = serializers.CharField(source="fornecedor.razao_social", read_only=True)
    estoque_livre = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = OfertaFornecedor
        fields = "__all__"
        read_only_fields = ["tenant", "estoque_reservado"]


class FaixaPrecoOfertaSerializer(TenantScopedModelSerializer):
    class Meta:
        model = FaixaPrecoOferta
        fields = "__all__"
        read_only_fields = ["tenant"]


class DemandaSerializer(TenantScopedModelSerializer):
    centro_custo_nome = serializers.CharField(source="centro_custo.nome", read_only=True, default=None)
    solicitante_nome = serializers.CharField(source="solicitante.username", read_only=True, default=None)
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)

    class Meta:
        model = Demanda
        fields = "__all__"
        # ref_externa é auto (editable=False); status/visibilidade mudam pelos
        # verbos de domínio (publicar/adjudicar), não pelo PUT direto.
        read_only_fields = ["tenant", "ref_externa", "visibilidade"]


class ItemDemandaSerializer(TenantScopedModelSerializer):
    produto_descricao = serializers.CharField(source="produto.descricao", read_only=True, default=None)
    produto_codigo = serializers.CharField(source="produto.codigo_interno", read_only=True, default=None)

    class Meta:
        model = ItemDemanda
        fields = "__all__"
        read_only_fields = ["tenant"]


class CotacaoSerializer(TenantScopedModelSerializer):
    propostas_count = serializers.IntegerField(source="propostas.count", read_only=True)

    class Meta:
        model = Cotacao
        fields = "__all__"
        read_only_fields = ["tenant", "status"]


class PropostaSerializer(TenantScopedModelSerializer):
    # Rótulo do fornecedor: interno usa a razão social; da rede usa o nome-cópia.
    fornecedor_label = serializers.SerializerMethodField()

    class Meta:
        model = Proposta
        fields = "__all__"
        # status muda pelo adjudicar; origem_tenant é do caminho de rede (sistema).
        read_only_fields = ["tenant", "status", "origem_tenant"]

    def get_fornecedor_label(self, obj):
        if obj.fornecedor_id and obj.fornecedor:
            return obj.fornecedor.razao_social
        return obj.fornecedor_nome or "Fornecedor externo"


class ItemPropostaSerializer(TenantScopedModelSerializer):
    class Meta:
        model = ItemProposta
        fields = "__all__"
        read_only_fields = ["tenant"]


class PedidoCompraSerializer(TenantScopedModelSerializer):
    fornecedor_nome = serializers.CharField(source="fornecedor.razao_social", read_only=True)
    centro_custo_nome = serializers.CharField(source="centro_custo.nome", read_only=True, default=None)
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)
    recebimentos_count = serializers.IntegerField(source="recebimentos.count", read_only=True)

    class Meta:
        model = PedidoCompra
        fields = "__all__"
        # ref_externa auto; conta_pagar_ref/origem_tenant são seams de sistema
        # (ERP/rede); status muda pelas actions/recebimentos.
        read_only_fields = ["tenant", "ref_externa", "conta_pagar_ref", "origem_tenant"]


class ItemPedidoSerializer(TenantScopedModelSerializer):
    produto_descricao = serializers.CharField(source="produto.descricao", read_only=True, default=None)
    produto_codigo = serializers.CharField(source="produto.codigo_interno", read_only=True, default=None)

    class Meta:
        model = ItemPedido
        fields = "__all__"
        read_only_fields = ["tenant"]


class RecebimentoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = Recebimento
        fields = "__all__"
        read_only_fields = ["tenant"]


class ItemRecebimentoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = ItemRecebimento
        fields = "__all__"
        read_only_fields = ["tenant"]


class AvaliacaoFornecedorSerializer(TenantScopedModelSerializer):
    fornecedor_nome = serializers.CharField(source="fornecedor.razao_social", read_only=True)

    class Meta:
        model = AvaliacaoFornecedor
        fields = "__all__"
        read_only_fields = ["tenant"]
