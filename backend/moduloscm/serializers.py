# backend/moduloscm/serializers.py
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
    class Meta:
        model = Demanda
        fields = "__all__"
        # ref_externa é auto (editable=False); status/visibilidade mudam pelos
        # verbos de domínio (publicar/adjudicar), não pelo PUT direto.
        read_only_fields = ["tenant", "ref_externa", "visibilidade"]


class ItemDemandaSerializer(TenantScopedModelSerializer):
    class Meta:
        model = ItemDemanda
        fields = "__all__"
        read_only_fields = ["tenant"]


class CotacaoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = Cotacao
        fields = "__all__"
        read_only_fields = ["tenant", "status"]


class PropostaSerializer(TenantScopedModelSerializer):
    class Meta:
        model = Proposta
        fields = "__all__"
        # status muda pelo adjudicar; origem_tenant é do caminho de rede (sistema).
        read_only_fields = ["tenant", "status", "origem_tenant"]


class ItemPropostaSerializer(TenantScopedModelSerializer):
    class Meta:
        model = ItemProposta
        fields = "__all__"
        read_only_fields = ["tenant"]


class PedidoCompraSerializer(TenantScopedModelSerializer):
    class Meta:
        model = PedidoCompra
        fields = "__all__"
        # ref_externa auto; conta_pagar_ref/origem_tenant são seams de sistema
        # (ERP/rede); status muda pelas actions/recebimentos.
        read_only_fields = ["tenant", "ref_externa", "conta_pagar_ref", "origem_tenant"]


class ItemPedidoSerializer(TenantScopedModelSerializer):
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
    class Meta:
        model = AvaliacaoFornecedor
        fields = "__all__"
        read_only_fields = ["tenant"]
