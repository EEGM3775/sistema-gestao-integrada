# backend/moduloorcamento/serializers.py
"""Serializers do módulo.

Duas famílias, pela mesma fronteira que divide `models.py`:

- **Base referencial** — `ModelSerializer` puro, e **não**
  `TenantScopedModelSerializer`: estes modelos não têm `tenant` (base pública de
  plataforma). Todos de leitura; a escrita é do comando de importação.
- **Planilha (ORC.1+)** — `TenantScopedModelSerializer`, com `tenant` read-only
  sistêmico (D3) e unicidade por-tenant (Fase 8.3).
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from . import carga, oficial, planilha
from .models import (
    BancoPreco,
    BaseReferencial,
    CargaBase,
    ComponenteBancoPreco,
    ComposicaoBDI,
    ComposicaoEncargos,
    ComposicaoReferenciaItem,
    FonteOficial,
    InsumoReferencia,
    ItemBancoPreco,
    ItemOrcado,
    ItemOrcadoInsumo,
    LinhaMedicao,
    LinhaReprecificacao,
    MemorialNBR,
    Orcamento,
    ParametroObra,
    ParcelaEtapa,
    PastaComposicao,
    PavimentoObra,
    Reprecificacao,
    RevisaoOrcamento,
    RubricaEncargos,
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


class FonteOficialSerializer(serializers.ModelSerializer):
    """ORC.8 — o endereço da fonte, editável pelo dono da plataforma.

    É o único serializer de escrita desta família, e a razão é a decisão de
    rumo: a URL da Caixa já mudou uma vez, e o conserto tem de ser uma caixa de
    texto e não um deploy.
    """

    fonte_nome = serializers.CharField(source="get_fonte_display", read_only=True)
    # O que o botão proporia agora — a competência já descontada da defasagem.
    # Vem daqui, e não da tela, porque quem sabe que a SINAPI publica M no dia 10
    # de M+1 é a fonte, não o React.
    competencia_sugerida = serializers.SerializerMethodField()
    # Se o motor sabe ler o arquivo desta fonte sozinho. `Fonte` aceita seis
    # desde a ORC.0 e o importador manual é genérico, mas o formato largo é o
    # arquivo da Caixa: oferecer o botão nas outras seria vender um caminho que
    # sempre falha.
    carga_automatica = serializers.SerializerMethodField()
    # ORC.8b — se esta fonte publica **um menu** em vez de um arquivo do mês. A
    # tela precisa saber antes de desenhar: na SINAPI o certo é um botão
    # "carregar 07/2026"; na EMBASA, que põe 65 tabelas por semestre no ar, um
    # botão só esconderia a pergunta que importa — qual delas.
    exige_documento = serializers.SerializerMethodField()

    class Meta:
        model = FonteOficial
        fields = "__all__"

    def get_competencia_sugerida(self, obj):
        return oficial.competencia_alvo(obj.defasagem_meses)

    def get_carga_automatica(self, obj) -> bool:
        return obj.fonte in carga.fontes_conhecidas()

    def get_exige_documento(self, obj) -> bool:
        return carga.exige_escolha_de_documento(obj.fonte)


class CargaBaseSerializer(serializers.ModelSerializer):
    """A corrida, do jeito que a tela precisa lê-la."""

    fonte_nome = serializers.CharField(source="get_fonte_display", read_only=True)
    estado_nome = serializers.CharField(source="get_estado_display", read_only=True)
    origem_nome = serializers.CharField(source="get_origem_display", read_only=True)
    em_andamento = serializers.BooleanField(read_only=True)
    mb_lidos = serializers.SerializerMethodField()

    class Meta:
        model = CargaBase
        # `arquivo` fica **fora**, e é o que sustenta a linha `cargas_base: "—"`
        # da tabela de portas do D70: o ZIP do plano B é entrada operacional, não
        # mídia. Com `__all__` o DRF publicaria a URL dele em `/media/`, que é
        # exatamente o caminho que aquele invariante existe para fechar. O que a
        # tela precisa é o **nome**, e esse continua aqui.
        exclude = ["arquivo"]
        read_only_fields = [
            "estado", "etapa", "resumo", "erro", "bytes_lidos", "url_origem",
            "arquivo_nome", "total_publicacoes", "total_insumos", "total_composicoes",
            "total_analitica", "solicitada_por_nome", "concluida_em",
        ]

    def get_mb_lidos(self, obj) -> float:
        return round(obj.bytes_lidos / (1024 * 1024), 2)


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
    # ORC.10e — deixou de ser read-only, mas **só** aceita valor quando a linha
    # declara `eap_manual`. Aberto sem essa marca, o próximo recálculo
    # sobrescreveria o que foi digitado e o campo passaria a mentir: aceitaria a
    # escrita e descartaria o valor, que é pior que recusar.
    codigo_eap = serializers.CharField(required=False, allow_blank=True)
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

        manual = attrs.get("eap_manual")
        if manual is None:
            manual = getattr(self.instance, "eap_manual", False)
        if attrs.get("codigo_eap") and not manual:
            raise serializers.ValidationError({
                "codigo_eap": (
                    "O código EAP é derivado da árvore. Marque `eap_manual` na mesma "
                    "requisição para assumi-lo à mão."
                )
            })

        # Sintético é soma dos filhos (ver `ItemOrcado.custa`). Deixar a linha
        # virar analítica com filhos pendurados faria o custo dela ser contado
        # duas vezes — uma no próprio número, outra nos filhos.
        tipo = attrs.get("tipo_linha") or getattr(self.instance, "tipo_linha", None)
        if (
            tipo == ItemOrcado.TipoLinha.ANALITICO
            and self.instance is not None
            and self.instance.tipo_linha != tipo
            and self.instance.filhos.exists()
        ):
            raise serializers.ValidationError({
                "tipo_linha": (
                    "Esta linha tem sub-itens. Mova-os para fora antes de transformá-la em linha "
                    "que custa, para o valor não ser somado duas vezes."
                )
            })
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

    def update(self, instance, validated_data):
        """Trocar a publicação arrasta data-base e regime junto.

        O `create` acima já cola a data-base na publicação escolhida; a
        atualização **não fazia isso**, e era uma incoerência que nascia calada:
        um PATCH que só trocasse `base_referencial` deixava `data_base`
        apontando para o mês da publicação anterior — ou nulo, quando o
        orçamento tinha nascido "sem base". Data-base é o que o edital cobra e o
        que separa orçado de realizado; errada, ela não avisa, só mente.

        **Só arrasta o que o cliente não mandou** e **só quando a publicação
        mudou**: quem informa `data_base` na mesma requisição está dizendo que
        sabe o que quer, e data de edital diferente do mês da publicação é caso
        real, não engano.

        Tirar a base (`None`) **não** apaga a data-base, de propósito: ela
        sobrevive à publicação (ver `models.Orcamento`), porque o preço já
        congelado continua sendo de algum mês.

        O que este método **não** faz é reprecificar. As linhas são fotografias;
        mexer nelas é o trabalho da `Reprecificacao`, que tem prévia, histórico
        e desfazer. Trocar a base aqui muda de onde os **próximos** itens vão
        buscar preço — os que já estão na planilha ficam como estão.
        """
        base = validated_data.get("base_referencial", instance.base_referencial)
        trocou = (
            "base_referencial" in validated_data
            and base != instance.base_referencial
        )
        if trocou and base is not None:
            validated_data.setdefault("data_base", base.mes_referencia)
            validated_data.setdefault("regime_encargos", base.regime_encargos)
        return super().update(instance, validated_data)


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
    """Linha da memória de cálculo — **editável** desde a ORC.10c.

    Era só leitura: a explosão gerava a composição a partir do catálogo e nada
    sabia lê-la de volta. Editar a decomposição é o núcleo do Arquimedes, e a
    assimetria era grande — o preço de um serviço só podia ser aceito inteiro ou
    digitado por cima, nunca ajustado no coeficiente que estava errado.

    `custo_no_item` continua **derivado**, e é aqui que ele é derivado: é
    `coeficiente × custo_unitario` com o **encargo social** aplicado quando o
    insumo é mão de obra, pelo mesmo resolvedor que a explosão usa
    (horista × mensalista pela unidade). Aceitá-lo do cliente deixaria a soma da
    composição divergir do preço da linha sem nada apontar a divergência.
    """

    categoria_nome = serializers.CharField(source="get_categoria_display", read_only=True)
    custo_no_item = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)

    class Meta:
        model = ItemOrcadoInsumo
        fields = "__all__"

    def validate_item_orcado(self, linha):
        """Composição pendurada em agrupador contaria o mesmo insumo duas vezes."""
        if linha.tipo_linha == ItemOrcado.TipoLinha.SINTETICO:
            raise serializers.ValidationError(
                "Linha sintética é agrupador: o custo dela é a soma dos filhos, e ela "
                "não tem composição própria."
            )
        return linha

    def _com_encargo(self, instance, validated_data):
        from . import encargos as encargos_mod

        linha = validated_data.get("item_orcado") or getattr(instance, "item_orcado", None)
        coeficiente = validated_data.get(
            "coeficiente", getattr(instance, "coeficiente", Decimal("0")),
        )
        custo = validated_data.get(
            "custo_unitario", getattr(instance, "custo_unitario", Decimal("0")),
        )
        categoria = validated_data.get(
            "categoria", getattr(instance, "categoria", ItemOrcadoInsumo.Categoria.MATERIAL),
        )
        unidade = validated_data.get("unidade", getattr(instance, "unidade", ""))

        bruto = Decimal(coeficiente) * Decimal(custo)
        if categoria == ItemOrcadoInsumo.Categoria.MAO_DE_OBRA:
            bruto *= encargos_mod.ResolvedorEncargos(linha.orcamento).fator(unidade)
        validated_data["custo_no_item"] = bruto.quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP,
        )
        return validated_data

    def create(self, validated_data):
        return super().create(self._com_encargo(None, validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._com_encargo(instance, validated_data))


# ---------------------------------------------------------------------------
# ORC.3 — cronograma físico-financeiro
# ---------------------------------------------------------------------------


class ParcelaEtapaSerializer(TenantScopedModelSerializer):
    """Célula do cronograma. O valor é derivado do percentual — o planejador
    digita percentual, que é o que sobrevive a uma mudança de preço."""

    etapa_nome = serializers.CharField(source="grupo.descricao", read_only=True, default=None)
    valor_previsto = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = ParcelaEtapa
        fields = "__all__"

    def validate(self, attrs):
        orcamento = attrs.get("orcamento") or getattr(self.instance, "orcamento", None)
        grupo = attrs.get("grupo") or getattr(self.instance, "grupo", None)
        if grupo is not None and orcamento is not None and (
            grupo.orcamento_id != orcamento.pk or grupo.pai_id is not None
        ):
            raise serializers.ValidationError(
                {"grupo": "A etapa precisa ser um grupo de 1º nível deste orçamento."}
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


# ---------------------------------------------------------------------------
# ORC.7 — encargos analíticos, memória do quantitativo e reajuste
# ---------------------------------------------------------------------------


class RubricaEncargosSerializer(TenantScopedModelSerializer):
    """Uma linha do quadro de encargos.

    A alíquota do **grupo D** é derivada, então quem manda uma `percentual` numa
    rubrica de reincidência não está errado — está sendo ignorado, e a tela
    precisa saber disso para desenhar o campo bloqueado em vez de aceitar
    digitação que some no próximo cálculo. É o que `derivada` informa.
    """

    grupo_nome = serializers.CharField(source="get_grupo_display", read_only=True)
    derivada = serializers.SerializerMethodField()

    class Meta:
        model = RubricaEncargos
        fields = "__all__"

    def get_derivada(self, obj) -> bool:
        return obj.base_calculo != RubricaEncargos.BaseCalculo.DIRETA


class ComposicaoEncargosSerializer(TenantScopedModelSerializer):
    """O quadro. Todos os totais são derivados — nenhum vem do cliente.

    Mesma razão do `ComposicaoBDI`: se o percentual resultante viesse do corpo
    da requisição, o quadro analítico poderia contradizer o número aplicado na
    planilha, que é exatamente o que a peça de conferência existe para impedir.
    """

    tipo_nome = serializers.CharField(source="get_tipo_mao_de_obra_display", read_only=True)
    regime_nome = serializers.CharField(source="get_regime_display", read_only=True)
    rubricas = RubricaEncargosSerializer(many=True, read_only=True)
    total_grupo_a = serializers.DecimalField(max_digits=7, decimal_places=4, read_only=True)
    total_grupo_b = serializers.DecimalField(max_digits=7, decimal_places=4, read_only=True)
    total_grupo_c = serializers.DecimalField(max_digits=7, decimal_places=4, read_only=True)
    total_grupo_d = serializers.DecimalField(max_digits=7, decimal_places=4, read_only=True)
    percentual_calculado = serializers.DecimalField(max_digits=7, decimal_places=4, read_only=True)

    class Meta:
        model = ComposicaoEncargos
        fields = "__all__"


class LinhaMedicaoSerializer(TenantScopedModelSerializer):
    """Uma parcial da memória do quantitativo.

    `total` é read-only porque é a conta — aceitar o total do cliente permitiria
    uma parcial que diz `2 × 3,50 × 2,80 = 40,00`, e uma memória de cálculo que
    não confere é pior que memória nenhuma: ela **parece** conferida.
    """

    total = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)
    sinal_nome = serializers.CharField(source="get_sinal_display", read_only=True)

    class Meta:
        model = LinhaMedicao
        fields = "__all__"

    def validate(self, attrs):
        item = attrs.get("item_orcado") or getattr(self.instance, "item_orcado", None)
        if item is not None and item.tipo_linha == ItemOrcado.TipoLinha.SINTETICO:
            raise serializers.ValidationError({
                "item_orcado": "Linha sintética soma os filhos — não tem quantidade própria a medir.",
            })
        formula = attrs.get("formula", getattr(self.instance, "formula", ""))
        if formula:
            from .quantitativos import FormulaInvalida, avaliar_formula

            try:
                avaliar_formula(formula)
            except FormulaInvalida as erro:
                raise serializers.ValidationError({"formula": str(erro)}) from erro
        return attrs


