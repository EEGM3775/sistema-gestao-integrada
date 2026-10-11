# backend/modulosil/serializers.py
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from .models import (
    Devolucao,
    EmprestimoFerramenta,
    EntregaEPI,
    Ferramenta,
    Inventario,
    ItemDevolucao,
    ItemInventario,
    ItemRequisicao,
    ItemTransferencia,
    LocalEstoque,
    Lote,
    MovimentacaoEstoque,
    Requisicao,
    SaldoEstoque,
    Transferencia,
)


class LocalEstoqueSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)

    class Meta:
        model = LocalEstoque
        fields = "__all__"
        read_only_fields = ["tenant"]


class LoteSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)

    class Meta:
        model = Lote
        fields = "__all__"
        read_only_fields = ["tenant"]


class SaldoEstoqueSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)
    item_codigo = serializers.CharField(source="item.codigo_interno", read_only=True)
    item_unidade = serializers.CharField(source="item.unidade", read_only=True)
    local_nome = serializers.CharField(source="local.nome", read_only=True)
    disponivel = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    valor_total = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    abaixo_minimo = serializers.BooleanField(read_only=True)

    class Meta:
        model = SaldoEstoque
        # quantidade/custo_medio/reservado só mudam pelo ledger (services); a API
        # edita só o ponto de reposição.
        fields = "__all__"
        read_only_fields = ["tenant", "quantidade", "custo_medio", "reservado"]


class MovimentacaoEstoqueSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)
    item_codigo = serializers.CharField(source="item.codigo_interno", read_only=True)
    local_nome = serializers.CharField(source="local.nome", read_only=True)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    usuario_nome = serializers.CharField(source="usuario.username", read_only=True, default=None)
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)
    etapa_nome = serializers.CharField(source="etapa.nome_etapa", read_only=True, default=None)

    class Meta:
        model = MovimentacaoEstoque
        # Ledger: criado só pelos services (actions), nunca por POST direto.
        fields = "__all__"
        read_only_fields = ["tenant"]


class ItemRequisicaoSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)
    item_unidade = serializers.CharField(source="item.unidade", read_only=True)

    class Meta:
        model = ItemRequisicao
        fields = "__all__"
        read_only_fields = ["tenant", "quantidade_atendida"]


class RequisicaoSerializer(TenantScopedModelSerializer):
    local_nome = serializers.CharField(source="local.nome", read_only=True)
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)
    etapa_nome = serializers.CharField(source="etapa.nome_etapa", read_only=True, default=None)
    solicitante_nome = serializers.CharField(source="solicitante.username", read_only=True, default=None)
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)

    class Meta:
        model = Requisicao
        fields = "__all__"
        read_only_fields = ["tenant", "status", "aprovador"]


class ItemTransferenciaSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)

    class Meta:
        model = ItemTransferencia
        fields = "__all__"
        read_only_fields = ["tenant"]


class TransferenciaSerializer(TenantScopedModelSerializer):
    origem_nome = serializers.CharField(source="origem.nome", read_only=True)
    destino_nome = serializers.CharField(source="destino.nome", read_only=True)
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)

    class Meta:
        model = Transferencia
        fields = "__all__"
        read_only_fields = ["tenant", "status"]


class ItemDevolucaoSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)

    class Meta:
        model = ItemDevolucao
        fields = "__all__"
        read_only_fields = ["tenant"]


class DevolucaoSerializer(TenantScopedModelSerializer):
    local_nome = serializers.CharField(source="local.nome", read_only=True)
    fornecedor_nome = serializers.CharField(source="fornecedor.razao_social", read_only=True, default=None)
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)

    class Meta:
        model = Devolucao
        fields = "__all__"
        read_only_fields = ["tenant", "status"]


class ItemInventarioSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)
    diferenca = serializers.SerializerMethodField()

    class Meta:
        model = ItemInventario
        fields = "__all__"
        read_only_fields = ["tenant", "ajuste_aplicado"]

    def get_diferenca(self, obj):
        return obj.quantidade_contada - obj.quantidade_sistema


class InventarioSerializer(TenantScopedModelSerializer):
    local_nome = serializers.CharField(source="local.nome", read_only=True)
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)

    class Meta:
        model = Inventario
        fields = "__all__"
        read_only_fields = ["tenant", "status", "fechado_em"]


class EntregaEPISerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)
    item_codigo = serializers.CharField(source="item.codigo_interno", read_only=True)
    colaborador_label = serializers.SerializerMethodField()
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)
    local_nome = serializers.CharField(source="local.nome", read_only=True, default=None)
    vencido = serializers.BooleanField(read_only=True)

    class Meta:
        model = EntregaEPI
        fields = "__all__"
        read_only_fields = ["tenant", "baixou_estoque"]

    def get_colaborador_label(self, obj):
        nome = getattr(getattr(obj, "colaborador", None), "nome_completo", None)
        return nome or obj.colaborador_nome or None


class FerramentaSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True, default=None)
    local_nome = serializers.CharField(source="local.nome", read_only=True, default=None)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    manutencao_vencendo = serializers.BooleanField(read_only=True)
    emprestimo_ativo = serializers.SerializerMethodField()

    class Meta:
        model = Ferramenta
        fields = "__all__"
        read_only_fields = ["tenant", "estado"]

    def get_emprestimo_ativo(self, obj):
        emp = obj.emprestimos.filter(status=EmprestimoFerramenta.Status.EMPRESTADA).first()
        if not emp:
            return None
        nome = getattr(getattr(emp, "colaborador", None), "nome_completo", None) or emp.colaborador_nome
        return {"emprestimo_id": emp.emprestimo_id, "colaborador": nome, "atrasada": emp.atrasada}


class EmprestimoFerramentaSerializer(TenantScopedModelSerializer):
    ferramenta_nome = serializers.CharField(source="ferramenta.nome", read_only=True)
    ferramenta_patrimonio = serializers.CharField(source="ferramenta.patrimonio", read_only=True, default=None)
    colaborador_label = serializers.SerializerMethodField()
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)
    atrasada = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmprestimoFerramenta
        fields = "__all__"
        read_only_fields = ["tenant", "status", "data_devolucao"]

    def get_colaborador_label(self, obj):
        nome = getattr(getattr(obj, "colaborador", None), "nome_completo", None)
        return nome or obj.colaborador_nome or None
