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
    Proposta,
    Recebimento,
)


class CentroCustoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = CentroCusto
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
    # Reputação p/ as estrelas do mapa comparativo: média (1–5) e nº de avaliações.
    # `None`/0 quando o fornecedor ainda não tem avaliação ("sem avaliação").
    fornecedor_avaliacao_media = serializers.SerializerMethodField()
    fornecedor_avaliacao_count = serializers.SerializerMethodField()
    # MAP.2 — distância fornecedor→canteiro. `None` quando a obra ou o
    # fornecedor não tem coordenada: a tela mostra "—", nunca um zero (que
    # seria lido como "está na esquina"). Frete e prazo saem daqui.
    distancia_km = serializers.SerializerMethodField()

    class Meta:
        model = Proposta
        fields = "__all__"
        # status muda pelo adjudicar; origem_tenant é do caminho de rede (sistema).
        read_only_fields = ["tenant", "status", "origem_tenant"]

    def get_fornecedor_label(self, obj):
        if obj.fornecedor_id and obj.fornecedor:
            return obj.fornecedor.razao_social
        return obj.fornecedor_nome or "Fornecedor externo"

    def _avaliacao(self, obj):
        """(media, count) do fornecedor. Lê o cache do contexto (montado pelo
        viewset, uma query por lista); sem cache, cai numa consulta pontual."""
        if not obj.fornecedor_id:
            return (None, 0)
        cache = self.context.get("avaliacao_agg")
        if cache is not None:
            return cache.get(obj.fornecedor_id, (None, 0))
        agg = AvaliacaoFornecedor.agg_por_fornecedor(obj.tenant_id, [obj.fornecedor_id])
        return agg.get(obj.fornecedor_id, (None, 0))

    def get_fornecedor_avaliacao_media(self, obj):
        return self._avaliacao(obj)[0]

    def get_fornecedor_avaliacao_count(self, obj):
        return self._avaliacao(obj)[1]

    def get_distancia_km(self, obj):
        """Lê o mapa `(cotacao, fornecedor) → km` montado pelo viewset.

        Sem o cache (detalhe, ou instalação sem Maps), devolve `None` em vez de
        consultar — a distância é enfeite decisório do comparativo, e não vale
        uma query por linha para preenchê-la fora dele.
        """
        cache = self.context.get("distancia_km")
        if not cache or not obj.fornecedor_id:
            return None
        return cache.get((obj.cotacao_id, obj.fornecedor_id))


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
    #: Medição × compra de serviço: os contratos do PDCA que medem este pedido.
    medicao_pdca = serializers.SerializerMethodField()

    class Meta:
        model = PedidoCompra
        fields = "__all__"
        # ref_externa auto; conta_pagar_ref/origem_tenant são seams de sistema
        # (ERP/rede); status muda pelas actions/recebimentos.
        read_only_fields = ["tenant", "ref_externa", "conta_pagar_ref", "origem_tenant"]

    def get_medicao_pdca(self, obj):
        contratos = getattr(obj, "contratos_pdca", None)
        if contratos is None:
            return []
        from decimal import Decimal

        from django.db.models import F, Sum

        saida = []
        for c in contratos.all():
            medido = (c.medicoes.filter(status="aprovada")
                      .aggregate(v=Sum(F("itens__quantidade") * F("itens__preco_unitario")))["v"] or Decimal("0"))
            saida.append({"contrato": c.pk, "numero": c.numero, "obra": c.obra_id,
                          "medido_aprovado": str(Decimal(medido).quantize(Decimal("0.01")))})
        return saida


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
