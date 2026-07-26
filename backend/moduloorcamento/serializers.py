# backend/moduloorcamento/serializers.py
"""Serializers do módulo.

Duas famílias, pela mesma fronteira que divide `models.py`:

- **Base referencial** — `ModelSerializer` puro, e **não**
  `TenantScopedModelSerializer`: estes modelos não têm `tenant` (base pública de
  plataforma). Todos de leitura; a escrita é do comando de importação.
- **Planilha (ORC.1+)** — `TenantScopedModelSerializer`, com `tenant` read-only
  sistêmico (D3) e unicidade por-tenant (Fase 8.3).
"""
from django.db import IntegrityError, transaction
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from . import planilha
from .models import (
    BancoPreco,
    BaseReferencial,
    ComponenteBancoPreco,
    ComposicaoBDI,
    ComposicaoReferenciaItem,
    InsumoReferencia,
    ItemBancoPreco,
    ItemOrcado,
    ItemOrcadoInsumo,
    LinhaReprecificacao,
    MemorialNBR,
    Orcamento,
    ParametroObra,
    ParcelaEtapa,
    PastaComposicao,
    PavimentoObra,
    Reprecificacao,
    RevisaoOrcamento,
    UnidadeAutonoma,
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

    def get_unique_together_validators(self):
        """Tira do cliente a unicidade `(obra, versao)`.

        `versao` é `read_only`, então o validador automático do DRF a checava
        pelo **default do modelo (1)** — e recusava com *"Os campos obra, versao
        devem criar um set único"* qualquer orçamento novo numa obra que já
        tivesse um. Quem numera é o servidor (`create` abaixo); a constraint do
        banco segue de pé como garantia real.
        """
        return [
            v for v in super().get_unique_together_validators()
            if "versao" not in getattr(v, "fields", ())
        ]

    def create(self, validated_data):
        """A data-base nasce colada na publicação escolhida.

        Copiar em vez de ler pela FK é deliberado (`models.Orcamento`): a
        publicação pode ser desativada ou substituída, e o orçamento precisa
        continuar dizendo de que mês era o preço que ele congelou.

        A **versão** também nasce aqui: a segunda planilha de uma obra é v2 (o
        reorçamento de escopo/método/mercado), não um erro de formulário. O
        retry existe porque `proxima_versao` lê e escreve em passos separados —
        dois POSTs simultâneos na mesma obra escolheriam o mesmo número e o
        segundo bateria na constraint; sem ele, viraria 500.
        """
        base = validated_data.get("base_referencial")
        if base is not None and not validated_data.get("data_base"):
            validated_data["data_base"] = base.mes_referencia
        if base is not None and not validated_data.get("regime_encargos"):
            validated_data["regime_encargos"] = base.regime_encargos

        obra = validated_data.get("obra")
        if obra is None or validated_data.get("versao"):
            return super().create(validated_data)

        for tentativa in range(3):
            validated_data["versao"] = planilha.proxima_versao(obra.pk)
            try:
                with transaction.atomic():
                    return super().create(validated_data)
            except IntegrityError:
                if tentativa == 2:
                    raise


class RevisaoOrcamentoSerializer(TenantScopedModelSerializer):
    tipo_nome = serializers.CharField(source="get_tipo_display", read_only=True)
    delta = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    orcamento_versao = serializers.IntegerField(source="orcamento.versao", read_only=True)

    class Meta:
        model = RevisaoOrcamento
        fields = "__all__"


# ---------------------------------------------------------------------------
# ORC.2 — BDI analítico e memória de cálculo
# ---------------------------------------------------------------------------


class ComposicaoBDISerializer(TenantScopedModelSerializer):
    """As parcelas do BDI. O resultado é derivado — nunca aceito do cliente.

    Se o percentual viesse do corpo da requisição, a composição analítica
    poderia contradizer o número aplicado, que é justamente o que a peça
    obrigatória de licitação existe para impedir.
    """

    percentual_calculado = serializers.DecimalField(max_digits=7, decimal_places=4, read_only=True)
    tributos = serializers.DecimalField(max_digits=6, decimal_places=3, read_only=True)

    class Meta:
        model = ComposicaoBDI
        fields = "__all__"


class ItemOrcadoInsumoSerializer(TenantScopedModelSerializer):
    """Linha da memória de cálculo."""

    categoria_nome = serializers.CharField(source="get_categoria_display", read_only=True)
    custo_no_item = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)

    class Meta:
        model = ItemOrcadoInsumo
        fields = "__all__"


# ---------------------------------------------------------------------------
# ORC.3 — cronograma físico-financeiro
# ---------------------------------------------------------------------------


class ParcelaEtapaSerializer(TenantScopedModelSerializer):
    """Célula do cronograma. O valor é derivado do percentual — o planejador
    digita percentual, que é o que sobrevive a uma mudança de preço."""

    etapa_nome = serializers.CharField(source="etapa.nome_etapa", read_only=True, default=None)
    valor_previsto = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = ParcelaEtapa
        fields = "__all__"

    def validate(self, attrs):
        orcamento = attrs.get("orcamento") or getattr(self.instance, "orcamento", None)
        etapa = attrs.get("etapa") or getattr(self.instance, "etapa", None)
        if etapa is not None and orcamento is not None and etapa.obra_id != orcamento.obra_id:
            raise serializers.ValidationError(
                {"etapa": "A etapa precisa pertencer à obra do orçamento."}
            )
        competencia = attrs.get("competencia")
        if competencia is not None and competencia.day != 1:
            # Normaliza em vez de recusar: a tela manda o mês, e exigir o dia 1
            # seria burocracia sem ganho.
            attrs["competencia"] = competencia.replace(day=1)
        return attrs


# ---------------------------------------------------------------------------
# ORC.4 — paramétrico e NBR 12721
# ---------------------------------------------------------------------------


class ParametroObraSerializer(TenantScopedModelSerializer):
    """Paramétrico. O custo é derivado — a tela informa área, CUB e adicionais."""

    custo_estimado = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    projeto_padrao_nome = serializers.CharField(source="get_projeto_padrao_display", read_only=True)
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)

    class Meta:
        model = ParametroObra
        fields = "__all__"


class PavimentoObraSerializer(TenantScopedModelSerializer):
    """Pavimento do Quadro I. As áreas derivadas são propriedades do modelo."""

    area_real = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    area_equivalente = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PavimentoObra
        fields = "__all__"


class UnidadeAutonomaSerializer(TenantScopedModelSerializer):
    """Unidade autônoma dos Quadros II e IV.

    `coeficiente_proporcionalidade` e `custo_estimado` são **read-only**: saem
    do cálculo dos quadros. Aceitá-los do cliente permitiria um rateio que não
    fecha com o custo global — exatamente o que gera exigência no cartório.
    A `fracao_ideal` **é** editável: é decisão jurídica do incorporador, não
    resultado de conta.
    """

    coeficiente_proporcionalidade = serializers.DecimalField(
        max_digits=12, decimal_places=8, read_only=True
    )
    custo_estimado = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    area_real_privativa = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    area_equivalente_privativa = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    pavimento_nome = serializers.CharField(source="pavimento.nome", read_only=True, default=None)

    class Meta:
        model = UnidadeAutonoma
        fields = "__all__"

    def validate(self, attrs):
        obra = attrs.get("obra") or getattr(self.instance, "obra", None)
        pavimento = attrs.get("pavimento") or getattr(self.instance, "pavimento", None)
        if pavimento is not None and obra is not None and pavimento.obra_id != obra.pk:
            raise serializers.ValidationError(
                {"pavimento": "O pavimento precisa ser da mesma obra."}
            )
        return attrs


class MemorialNBRSerializer(TenantScopedModelSerializer):
    quadro_nome = serializers.CharField(source="get_quadro_display", read_only=True)

    class Meta:
        model = MemorialNBR
        fields = "__all__"


# ---------------------------------------------------------------------------
# ORC.5b — bancos da empresa, importação e reprecificação
# ---------------------------------------------------------------------------


class BancoPrecoSerializer(TenantScopedModelSerializer):
    """Cabeçalho do banco. A trava é read-only aqui de propósito.

    Travar/destravar tem verbo próprio (`travar/`, `destravar/`) porque é
    decisão com rastro — quem travou e quando. Se `travado` fosse gravável pelo
    PATCH genérico, o rastro poderia ser contornado por um payload comum.
    """

    rotulo = serializers.SerializerMethodField()
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)
    fonte_nome = serializers.CharField(source="get_fonte_display", read_only=True)
    origem_nome = serializers.CharField(source="get_origem_display", read_only=True)
    editavel = serializers.BooleanField(read_only=True)
    total_pastas = serializers.SerializerMethodField()

    class Meta:
        model = BancoPreco
        fields = "__all__"
        read_only_fields = [
            "travado", "travado_em", "travado_por_nome", "total_itens", "origem",
        ]

    def get_rotulo(self, obj) -> str:
        return obj.rotulo_automatico()

    def get_total_pastas(self, obj) -> int:
        return obj.pastas.count()


class PastaComposicaoSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True, default=None)
    total_itens = serializers.SerializerMethodField()

    class Meta:
        model = PastaComposicao
        fields = "__all__"

    def get_total_itens(self, obj) -> int:
        return obj.itens.count()

    def validate(self, attrs):
        banco = attrs.get("banco") or getattr(self.instance, "banco", None)
        if banco is not None and banco.travado:
            raise serializers.ValidationError(
                {"banco": "Banco travado — destrave antes de mexer nas pastas."}
            )
        return attrs


class ItemBancoPrecoSerializer(TenantScopedModelSerializer):
    banco_nome = serializers.CharField(source="banco.nome", read_only=True)
    pasta_nome = serializers.CharField(source="pasta.nome", read_only=True, default=None)
    tipo_nome = serializers.CharField(source="get_tipo_display", read_only=True)
    adotado_item_id = serializers.SerializerMethodField()

    class Meta:
        model = ItemBancoPreco
        fields = "__all__"

    def get_adotado_item_id(self, obj):
        adotados = self.context.get("adotados") or {}
        return adotados.get((obj.banco.fonte, obj.codigo))

    def validate(self, attrs):
        """Trava do banco vale para o item, não só para o cabeçalho.

        Proteger o nome do banco e deixar o coeficiente editável não protege
        nada — o que contamina o orçamento é o número, não o rótulo.
        """
        banco = attrs.get("banco") or getattr(self.instance, "banco", None)
        if banco is not None and banco.travado:
            raise serializers.ValidationError(
                {"banco": f'O banco "{banco.nome}" está travado. Destrave para editar.'}
            )
        pasta = attrs.get("pasta") or getattr(self.instance, "pasta", None)
        if pasta is not None and banco is not None and pasta.banco_id != banco.banco_id:
            raise serializers.ValidationError({"pasta": "A pasta precisa ser do mesmo banco."})
        return attrs


class ComponenteBancoPrecoSerializer(TenantScopedModelSerializer):
    filho_codigo = serializers.CharField(source="filho.codigo", read_only=True)
    filho_descricao = serializers.CharField(source="filho.descricao", read_only=True)
    filho_unidade = serializers.CharField(source="filho.unidade", read_only=True)
    filho_custo_unitario = serializers.DecimalField(
        source="filho.custo_unitario", max_digits=14, decimal_places=4, read_only=True
    )
    custo_no_item = serializers.SerializerMethodField()

    class Meta:
        model = ComponenteBancoPreco
        fields = "__all__"

    def get_custo_no_item(self, obj) -> str:
        return str((obj.coeficiente * obj.filho.custo_unitario).quantize(obj.filho.custo_unitario))

    def validate(self, attrs):
        composicao = attrs.get("composicao") or getattr(self.instance, "composicao", None)
        filho = attrs.get("filho") or getattr(self.instance, "filho", None)
        if composicao is not None and composicao.banco.travado:
            raise serializers.ValidationError(
                {"composicao": "Banco travado — destrave para editar a composição."}
            )
        if composicao is not None and filho is not None:
            if composicao.pk == filho.pk:
                raise serializers.ValidationError(
                    {"filho": "Uma composição não pode conter a si mesma."}
                )
            if composicao.banco_id != filho.banco_id:
                raise serializers.ValidationError(
                    {"filho": "O insumo precisa ser do mesmo banco da composição."}
                )
        return attrs


class LinhaReprecificacaoSerializer(TenantScopedModelSerializer):
    codigo_eap = serializers.CharField(source="item_orcado.codigo_eap", read_only=True)
    descricao = serializers.CharField(source="item_orcado.descricao", read_only=True)
    unidade = serializers.CharField(source="item_orcado.unidade", read_only=True)
    quantidade = serializers.DecimalField(
        source="item_orcado.quantidade", max_digits=16, decimal_places=4, read_only=True
    )
    delta_unitario = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)

    class Meta:
        model = LinhaReprecificacao
        fields = "__all__"
        read_only_fields = [
            "reprecificacao", "item_orcado", "custo_antes", "custo_depois",
            "fonte_antes", "codigo_antes", "data_base_antes",
            "fonte_depois", "codigo_depois", "data_base_depois", "aplicada",
        ]


class ReprecificacaoSerializer(TenantScopedModelSerializer):
    """Lote read-only: nasce de `orcamentos/{id}/reprecificar/`, nunca por POST.

    Mesma razão do `RevisaoOrcamento` — um lote sem as linhas correspondentes
    seria rastro falso, e é o rastro que a auditoria de licitação confere.
    """

    status_nome = serializers.CharField(source="get_status_display", read_only=True)
    delta = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    orcamento_descricao = serializers.CharField(source="orcamento.descricao", read_only=True)
    destino_rotulo = serializers.SerializerMethodField()

    class Meta:
        model = Reprecificacao
        fields = "__all__"

    def get_destino_rotulo(self, obj) -> str | None:
        if obj.base_destino_id:
            return obj.base_destino.rotulo or obj.base_destino.rotulo_automatico()
        if obj.banco_destino_id:
            return obj.banco_destino.rotulo_automatico()
        return None
