# backend/modulopdca/serializers.py
"""Serializers do PDCA.

Duas coisas atravessam todos eles, e as duas vêm da régua do projeto:

1. **O vínculo com outro módulo aparece resolvido.** `unidade_rotulo` e
   `maps_local_rotulo` viajam junto do id porque a tela promete integração
   visível — e sem o rótulo o frontend faria N chamadas para escrever "Apto 101"
   ao lado do local.
2. **Nada é fabricado.** Local sem área devolve `null`, não `0`; obra sem
   calendário devolve `null`, não um calendário-fantasma de segunda a sexta.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from funcoesimpexp.entrega import url_do_arquivo
from nucleo.tenant_validators import TenantScopedModelSerializer
from nucleo.upload_validation import UploadValidationMixin

from . import services
from .impexp import ESPECIE_FOTO, RECURSO_FOTO
from .models import (
    AcaoAditivo, AditivoContrato, ApontamentoAvanco, Atividade,
    CalendarioTrabalho, ContratoObra, Cronograma, DeducaoMedicao,
    ExcecaoCalendario, ItemAditivo, ItemContrato, ItemMedicao,
    LiberacaoRetencao, LocalObra, Medicao, OrigemApontamento, Precedencia,
    RegimeContrato, TipoDeducao,
)


class LocalObraSerializer(TenantScopedModelSerializer):
    nivel_rotulo = serializers.CharField(source="get_nivel_display", read_only=True)
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    unidade_rotulo = serializers.SerializerMethodField()
    maps_local_rotulo = serializers.CharField(source="maps_local.nome", read_only=True)
    #: Quantos filhos diretos. É o que a árvore da tela usa para decidir se
    #: desenha a seta de expandir sem carregar o galho inteiro.
    filhos_count = serializers.IntegerField(source="filhos.count", read_only=True)

    class Meta:
        model = LocalObra
        fields = "__all__"
        read_only_fields = ["tenant", "profundidade", "criado_em", "atualizado_em"]

    def get_unidade_rotulo(self, obj) -> str:
        return str(obj.unidade) if obj.unidade_id else ""

    def validate(self, dados):
        """Duas regras que o banco não pega e que viram dado errado silencioso.

        A primeira é o pai de outra obra: a FK garante que o pai existe, não que
        ele é da mesma obra — e um pavimento pendurado na torre da obra vizinha
        quebra a árvore das duas.

        A segunda é o ciclo: `pai = ele mesmo` (ou um descendente) deixa a árvore
        sem raiz, e todo caminhamento recursivo depois disso roda para sempre.
        """
        pai = dados.get("pai", getattr(self.instance, "pai", None))
        obra = dados.get("obra", getattr(self.instance, "obra", None))
        if pai is not None and obra is not None and pai.obra_id != obra.pk:
            raise serializers.ValidationError(
                {"pai": "O local pai pertence a outra obra."}
            )
        if pai is not None and self.instance is not None:
            no = pai
            while no is not None:
                if no.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        {"pai": "Um local não pode ser descendente de si mesmo."}
                    )
                no = no.pai
        return dados


class ExcecaoCalendarioSerializer(TenantScopedModelSerializer):
    class Meta:
        model = ExcecaoCalendario
        fields = "__all__"
        read_only_fields = ["tenant"]


class CalendarioTrabalhoSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    excecoes = ExcecaoCalendarioSerializer(many=True, read_only=True)

    class Meta:
        model = CalendarioTrabalho
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em", "atualizado_em"]

    def validate(self, dados):
        """Um calendário sem nenhum dia da semana ligado não é um calendário —
        é uma obra que nunca anda. Recusar aqui evita que a PDCA.1 descubra isso
        dentro do CPM, onde o sintoma seria "o cronograma não calcula".

        O valor efetivo tem três origens, nesta ordem: **o que veio no payload**,
        **o que já está gravado** (numa edição parcial) e, só então, o **default
        do modelo**. Sem o terceiro degrau, criar um calendário sem citar os dias
        — que é o caso normal, já que segunda a sexta é o padrão — era recusado
        com a mensagem de um erro que o cliente não cometeu.
        """
        campos = [
            "trabalha_segunda", "trabalha_terca", "trabalha_quarta", "trabalha_quinta",
            "trabalha_sexta", "trabalha_sabado", "trabalha_domingo",
        ]

        def efetivo(campo):
            if campo in dados:
                return dados[campo]
            if self.instance is not None:
                return getattr(self.instance, campo)
            return CalendarioTrabalho._meta.get_field(campo).default

        if not any(efetivo(c) for c in campos):
            raise serializers.ValidationError(
                "Marque ao menos um dia da semana como trabalhado."
            )
        return dados


class GeracaoEmLoteSerializer(serializers.Serializer):
    """A receita do gerador. É um `Serializer` puro (não de modelo) porque o que
    entra aqui não é um objeto — é uma **instrução** que vira centenas deles."""

    obra = serializers.IntegerField()
    pai = serializers.IntegerField(required=False, allow_null=True)
    simular = serializers.BooleanField(default=False)
    receita = serializers.ListField(child=serializers.DictField(), allow_empty=False)


# ---------------------------------------------------------------------------
# PDCA.1 — o plano de tempo
# ---------------------------------------------------------------------------


class CronogramaSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    calendario_nome = serializers.CharField(source="calendario.nome", read_only=True)
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)
    editavel = serializers.BooleanField(read_only=True)
    atividades_count = serializers.IntegerField(source="atividades.count", read_only=True)
    #: A versão de que este nasceu — o fio da linha de base, resolvido aqui para
    #: a tela não precisar de uma segunda chamada só para escrever "v2 → v3".
    base_versao = serializers.IntegerField(source="origem.versao", read_only=True)

    class Meta:
        model = Cronograma
        fields = "__all__"
        read_only_fields = [
            "tenant", "versao", "status", "origem", "publicado_em", "publicado_por",
            "calculado_em", "termino_calculado", "criado_em", "atualizado_em",
        ]

    def validate(self, dados):
        """O calendário tem de ser desta empresa e servir a esta obra.

        Um cronograma apontando para o calendário de outra obra converteria
        duração em data pelo expediente errado — e o erro só apareceria como
        "o prazo não bate", que é o sintoma mais caro de diagnosticar.
        """
        calendario = dados.get("calendario", getattr(self.instance, "calendario", None))
        obra = dados.get("obra", getattr(self.instance, "obra", None))
        if calendario is not None and obra is not None:
            if calendario.obra_id and calendario.obra_id != obra.pk:
                raise serializers.ValidationError(
                    {"calendario": "Este calendário pertence a outra obra."}
                )
        return dados

    def get_unique_together_validators(self):
        """Tira **um** validador automático: o do nome de plano modelo.

        A `UniqueConstraint` condicional de `nome_modelo` existe no banco e é a
        trava de verdade; a mensagem acionável vem de `services.marcar_como_
        modelo`. Só que o DRF, ao encontrá-la, gera um `UniqueTogetherValidator`
        — e todo campo dentro de um desses vira **obrigatório**. O efeito era
        absurdo e apareceu no primeiro teste que criou um cronograma comum:
        `{"nome_modelo": ["Este campo é obrigatório."]}` ao cadastrar um plano
        que não é modelo nenhum.

        O filtro é por nome de campo, e não `validators = []`, para as outras
        travas (versão única por obra, um vigente por obra) continuarem valendo.
        """
        return [
            validador for validador in super().get_unique_together_validators()
            if "nome_modelo" not in tuple(getattr(validador, "fields", ()))
        ]


class AtividadeSerializer(TenantScopedModelSerializer):
    local_rotulo = serializers.SerializerMethodField()
    etapa_nome = serializers.CharField(source="etapa.nome_etapa", read_only=True)
    item_orcado_rotulo = serializers.SerializerMethodField()
    responsavel_nome = serializers.CharField(
        source="responsavel.nome_completo", read_only=True,
    )
    calendario_nome = serializers.CharField(source="calendario.nome", read_only=True)
    tem_filhos = serializers.SerializerMethodField()
    #: O peso e **de onde ele veio**. Duas fontes silenciosas para o mesmo número
    #: é como se perde a confiança nas duas (planta §11.2), então a origem viaja
    #: junto: `orcado`, `informado` ou vazio — e vazio quer dizer "sem apuração",
    #: nunca zero.
    peso = serializers.SerializerMethodField()
    peso_origem = serializers.SerializerMethodField()

    class Meta:
        model = Atividade
        fields = "__all__"
        read_only_fields = [
            "tenant", "profundidade", "inicio_cedo", "termino_cedo",
            "inicio_tarde", "termino_tarde", "folga_total", "folga_livre",
            "critica", "criado_em", "atualizado_em",
        ]

    def get_local_rotulo(self, obj) -> str:
        return str(obj.local) if obj.local_id else ""

    def get_item_orcado_rotulo(self, obj) -> str:
        return str(obj.item_orcado) if obj.item_orcado_id else ""

    def get_tem_filhos(self, obj) -> bool:
        return obj.filhos.exists()

    def get_peso(self, obj):
        peso, _origem = services.peso_de(obj)
        return peso

    def get_peso_origem(self, obj) -> str:
        _peso, origem = services.peso_de(obj)
        return origem

    def validate(self, dados):
        def valor(campo, padrao=None):
            if campo in dados:
                return dados[campo]
            if self.instance is not None:
                return getattr(self.instance, campo)
            return padrao

        cronograma = valor("cronograma")
        pai = valor("pai")
        eh_marco = valor("eh_marco", False)
        duracao = valor("duracao_dias")

        if cronograma is not None and not cronograma.editavel:
            raise serializers.ValidationError(
                "Este cronograma não é mais rascunho. Para mudar o plano, replaneje — "
                "é o que preserva a versão anterior como linha de base."
            )

        if pai is not None:
            if cronograma is not None and pai.cronograma_id != cronograma.pk:
                raise serializers.ValidationError(
                    {"pai": "A atividade pai pertence a outro cronograma."}
                )
            if self.instance is not None:
                no = pai
                while no is not None:
                    if no.pk == self.instance.pk:
                        raise serializers.ValidationError(
                            {"pai": "Uma atividade não pode ser descendente de si mesma."}
                        )
                    no = no.pai
            try:
                services.validar_profundidade_wbs(pai)
            except DjangoValidationError as erro:
                raise serializers.ValidationError({"pai": erro.messages})

        if eh_marco:
            if duracao not in (None, 0):
                raise serializers.ValidationError({
                    "duracao_dias": "Marco é um instante — deixe a duração vazia.",
                })
        else:
            tem_filhos = (
                self.instance is not None and self.instance.filhos.exists()
            )
            if not tem_filhos and (duracao is None or duracao < 1):
                raise serializers.ValidationError({
                    "duracao_dias": "A atividade analítica precisa de duração de ao menos 1 dia útil.",
                })

        obra_id = cronograma.obra_id if cronograma is not None else None
        local = valor("local")
        if local is not None and obra_id and local.obra_id != obra_id:
            raise serializers.ValidationError({"local": "Este local pertence a outra obra."})
        etapa = valor("etapa")
        if etapa is not None and obra_id and etapa.obra_id != obra_id:
            raise serializers.ValidationError({"etapa": "Esta etapa pertence a outra obra."})
        item = valor("item_orcado")
        if item is not None and obra_id and item.orcamento.obra_id != obra_id:
            raise serializers.ValidationError({
                "item_orcado": "Este item orçado é de um orçamento de outra obra.",
            })

        return dados


class PrecedenciaSerializer(TenantScopedModelSerializer):
    origem_codigo = serializers.CharField(source="origem.codigo", read_only=True)
    destino_codigo = serializers.CharField(source="destino.codigo", read_only=True)
    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = Precedencia
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em"]

    def validate(self, dados):
        """Quatro recusas, e as quatro existem para o erro ter endereço.

        Ligar atividades de cronogramas diferentes, ligar uma sintética (que não
        entra no grafo), fechar um ciclo ou mexer num plano já publicado: todas
        apareceriam depois como "o cronograma não calcula", numa tela que não
        saberia dizer qual das centenas de setas está errada.
        """
        origem = dados.get("origem", getattr(self.instance, "origem", None))
        destino = dados.get("destino", getattr(self.instance, "destino", None))
        if origem is None or destino is None:
            return dados

        if origem.cronograma_id != destino.cronograma_id:
            raise serializers.ValidationError(
                "As duas atividades precisam ser do mesmo cronograma."
            )
        if origem.pk == destino.pk:
            raise serializers.ValidationError("Uma atividade não precede a si mesma.")
        if not origem.cronograma.editavel:
            raise serializers.ValidationError(
                "Este cronograma não é mais rascunho. Para mudar as precedências, replaneje."
            )
        for papel, atividade in (("origem", origem), ("destino", destino)):
            if atividade.filhos.exists():
                raise serializers.ValidationError({
                    papel: (
                        f"'{atividade.codigo}' é uma atividade sintética (tem filhas). "
                        "A precedência liga as folhas — a sintética é o intervalo delas."
                    ),
                })

        if self._fecha_ciclo(origem, destino):
            raise serializers.ValidationError(
                f"Esta ligação fecharia um ciclo: '{destino.codigo}' já leva, direta ou "
                f"indiretamente, a '{origem.codigo}'."
            )
        return dados

    def _fecha_ciclo(self, origem, destino) -> bool:
        """Chegando de `destino` a `origem`, a seta nova fecharia o laço."""
        atual = getattr(self.instance, "pk", None)
        vistos = set()
        pilha = [destino.pk]
        while pilha:
            no = pilha.pop()
            if no == origem.pk:
                return True
            if no in vistos:
                continue
            vistos.add(no)
            pilha.extend(
                Precedencia.objects
                .filter(origem_id=no)
                .exclude(pk=atual)
                .values_list("destino_id", flat=True)
            )
        return False


class ReplanejarSerializer(serializers.Serializer):
    """O motivo é o único campo — e é obrigatório por desenho (planta §4.2)."""

    motivo = serializers.CharField(max_length=2000, allow_blank=False)


class MarcarModeloSerializer(serializers.Serializer):
    """O nome do padrão — é por ele que alguém o escolhe seis meses depois."""

    nome = serializers.CharField(max_length=120, allow_blank=False)


class AplicarModeloSerializer(serializers.Serializer):
    """Aplicar um modelo é criar o **primeiro** plano de uma obra.

    A data de início é obrigatória e o calendário é opcional pelo mesmo motivo de
    sempre: o modelo guarda **durações e rede**, que é o que se repete; quando a
    obra começa e quando ela trabalha são dela.
    """

    obra = serializers.IntegerField()
    data_inicio = serializers.DateField()
    descricao = serializers.CharField(max_length=200, required=False, allow_blank=True)
    calendario = serializers.IntegerField(required=False, allow_null=True)


class EdicaoEmLoteSerializer(serializers.Serializer):
    atividade = serializers.IntegerField()
    campos = serializers.DictField()


class LoteSerializer(serializers.Serializer):
    """O corpo do `lote/`. A validação de *quais* campos são aceitos fica no
    serviço, com a lista branca — aqui só se garante a forma."""

    edicoes = EdicaoEmLoteSerializer(many=True)


# ---------------------------------------------------------------------------
# PDCA.2 — o avanço apontado
# ---------------------------------------------------------------------------


class ApontamentoAvancoSerializer(UploadValidationMixin, TenantScopedModelSerializer):
    """O lançamento do avanço — **só nasce, nunca muda**.

    Quase tudo aqui é `read_only` de propósito: um apontamento gravado é uma
    linha de livro-razão. Editar `percentual` depois seria o mesmo que rasurar a
    medição que ele vai originar, e a viewset também não expõe `PUT`/`PATCH` — as
    duas paredes existem porque a segunda porta (comando de bancada, importação,
    WhatsApp) não passa pela primeira.

    A foto sobe pela **porta única** da plataforma: o `UploadValidationMixin` lê
    o teto de bytes e a lista de tipos da `ConfiguracaoArquivos` do tenant, que é
    a mesma régua do documento de obra e do anexo do diário. E **desce** pela
    mesma porta — ver `to_representation`.
    """

    atividade_codigo = serializers.CharField(source="atividade.codigo", read_only=True)
    atividade_nome = serializers.CharField(source="atividade.nome", read_only=True)
    local_rotulo = serializers.SerializerMethodField()
    origem_rotulo = serializers.CharField(source="get_origem_display", read_only=True)
    #: Se este lançamento já foi corrigido. A tela risca a linha em vez de
    #: escondê-la: o estorno é parte do histórico, não uma limpeza dele.
    estornado = serializers.SerializerMethodField()

    class Meta:
        model = ApontamentoAvanco
        fields = "__all__"
        read_only_fields = ["tenant", "apontado_por", "registrado_em", "estorna"]

    def get_local_rotulo(self, obj) -> str:
        return str(obj.local) if obj.local_id else ""

    def get_estornado(self, obj) -> bool:
        return obj.estornos.exists()

    def to_representation(self, instance):
        """`foto` sai como a URL da porta única, nunca como `/media/` (D120).

        **A troca é no `to_representation` e não num campo declarado** porque o
        mesmo nome precisa servir aos dois sentidos: na entrada `foto` é o
        `FileField` de verdade, que o `UploadValidationMixin` confere contra o
        teto do tenant; na saída é um endereço nosso. Declarar `foto` como
        `SerializerMethodField` tornaria o campo somente-leitura e derrubaria o
        upload; declarar um `foto_url` ao lado deixaria o `/media/` publicado do
        mesmo jeito, que é justamente o que o D120 acusou.

        Quem não tem foto continua recebendo `null` — e não uma URL que
        responderia 404, que seria fabricar dado contra a régua da casa.
        """
        dados = super().to_representation(instance)
        dados["foto"] = (
            url_do_arquivo(RECURSO_FOTO, ESPECIE_FOTO, instance.apontamento_id)
            if instance.foto else None
        )
        return dados

    def validate(self, dados):
        """As regras que o banco não pega e que viram avanço errado em silêncio.

        As recusas de domínio — sintética, marco, plano não vigente, acumulado
        acima de 100 — moram em `services.validar_apontamento`, porque a escrita
        em lote e o estorno passam por lá sem passar por aqui. O que sobra neste
        ponto é o que só o serializer enxerga: a coerência entre o local
        escolhido e a obra da atividade.
        """
        atividade = dados.get("atividade", getattr(self.instance, "atividade", None))
        local = dados.get("local", getattr(self.instance, "local", None))
        if atividade is not None and local is not None:
            if local.obra_id != atividade.cronograma.obra_id:
                raise serializers.ValidationError(
                    {"local": "Este local pertence a outra obra."}
                )
        percentual = dados.get("percentual")
        if percentual is not None and percentual == 0:
            raise serializers.ValidationError({
                "percentual": (
                    "Apontamento de zero não é avanço. Para registrar uma "
                    "observação sem avanço, use o diário de obra."
                ),
            })
        return dados


class LinhaDeApontamentoSerializer(serializers.Serializer):
    """Uma linha da **grade da semana** (a escrita em lote)."""

    atividade = serializers.IntegerField()
    data = serializers.DateField()
    percentual = serializers.DecimalField(max_digits=7, decimal_places=4)
    local = serializers.PrimaryKeyRelatedField(
        queryset=LocalObra.objects.all(), required=False, allow_null=True,
    )
    origem = serializers.ChoiceField(
        choices=OrigemApontamento.choices, required=False, allow_blank=True,
    )
    observacao = serializers.CharField(required=False, allow_blank=True)


class ApontamentoEmLoteSerializer(serializers.Serializer):
    cronograma = serializers.PrimaryKeyRelatedField(queryset=Cronograma.objects.all())
    linhas = LinhaDeApontamentoSerializer(many=True)


class EstornoSerializer(serializers.Serializer):
    """O motivo é obrigatório — é ele que separa a correção do erro."""

    motivo = serializers.CharField()
    data = serializers.DateField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# PDCA.3 — contrato, medição e liberação de retenção
# ---------------------------------------------------------------------------


class ItemContratoSerializer(TenantScopedModelSerializer):
    #: O valor da linha viaja resolvido porque a grade contratual soma colunas na
    #: tela; recalcular no navegador daria um número por implementação de
    #: JavaScript — a mesma razão que manteve o CPM no servidor (planta §5.5).
    valor_contratado = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True,
    )
    item_orcado_descricao = serializers.CharField(
        source="item_orcado.descricao", read_only=True,
    )
    atividade_nome = serializers.CharField(source="atividade.nome", read_only=True)
    #: Sem isto a tela não consegue explicar por que uma linha não recebeu
    #: proposta. "Sem vínculo" é um estado que o gestor precisa **ver** no
    #: cadastro do item, não descobrir na hora de medir.
    tem_vinculo_de_avanco = serializers.SerializerMethodField()
    #: **O que vale hoje** — original + aditivos aprovados. Viaja resolvido
    #: porque `quantidade_contratada` é o do dia da assinatura, e num contrato
    #: aditado ele deixou de ser o limite: uma tela que mostrasse só o campo
    #: estaria mostrando um número que não governa mais nada.
    quantidade_atual = serializers.SerializerMethodField()
    quantidade_aditivada = serializers.SerializerMethodField()

    class Meta:
        model = ItemContrato
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em", "atualizado_em"]

    def get_tem_vinculo_de_avanco(self, obj) -> bool:
        return bool(obj.atividade_id or obj.item_orcado_id)

    def validate(self, dados):
        """O item é de um contrato; a atividade e o item orçado são da obra dele.

        Sem esta trava, um item apontaria para a atividade de **outra** obra e a
        medição herdaria o avanço errado — um erro que só apareceria no valor do
        título, que é tarde demais.

        **E as duas regras numéricas que o banco já cobra.** As
        `CheckConstraint` do model são a rede de baixo — valem para o comando de
        bancada e para a importação —, mas quando *elas* são a primeira a falar,
        a recusa chega como `IntegrityError`: 500 e página de depuração
        ([D133](../../docs/historico-correcoes.md), achado pelo dono cadastrando
        um item sem quantidade). Aqui a mesma regra vira **mensagem no campo**,
        que é o que quem preenche o formulário consegue usar.
        """
        def valor(campo):
            if campo in dados:
                return dados[campo]
            return getattr(self.instance, campo, None)

        erros = {}
        quantidade = valor("quantidade_contratada")
        if quantidade is not None and quantidade <= 0:
            erros["quantidade_contratada"] = (
                "A quantidade contratada precisa ser maior que zero — um item de "
                "quantidade zero atravessaria a medição inteira sem erro e "
                "produziria um título de R$ 0,00 que ninguém consegue explicar. "
                "Se o item não vale mais, exclua-o em vez de zerá-lo."
            )
        preco = valor("preco_unitario")
        if preco is not None and preco < 0:
            erros["preco_unitario"] = (
                "O preço unitário não pode ser negativo. Devolver dinheiro é "
                "supressão, e supressão é aditivo — não linha de contrato."
            )
        if erros:
            raise serializers.ValidationError(erros)

        contrato = dados.get("contrato") or getattr(self.instance, "contrato", None)
        atividade = dados.get("atividade")
        if contrato is not None and atividade is not None:
            if atividade.cronograma.obra_id != contrato.obra_id:
                raise serializers.ValidationError(
                    {"atividade": "Esta atividade é de outra obra."}
                )
        item_orcado = dados.get("item_orcado")
        if contrato is not None and item_orcado is not None:
            obra_do_orcamento = getattr(item_orcado.orcamento, "obra_id", None)
            if obra_do_orcamento and obra_do_orcamento != contrato.obra_id:
                raise serializers.ValidationError(
                    {"item_orcado": "Este item orçado é de outra obra."}
                )
        return dados

    def get_quantidade_atual(self, obj):
        atual = services.contratado_atual_por_item(obj.contrato)
        return str(atual.get(obj.pk, obj.quantidade_contratada))

    def get_quantidade_aditivada(self, obj):
        return str(services.aditivo_por_item(obj.contrato).get(obj.pk, 0))


class ContratoObraSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    fornecedor_nome = serializers.CharField(
        source="fornecedor.razao_social", read_only=True,
    )
    regime_rotulo = serializers.CharField(source="get_regime_display", read_only=True)
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)
    retencao_natureza_rotulo = serializers.CharField(
        source="get_retencao_natureza_display", read_only=True,
    )
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)
    #: **A tela nunca oferece um botão que a API vai recusar.** A regra de quando
    #: a planilha contratual ainda aceita edição direta mora em
    #: `services.planilha_editavel`, e viaja resolvida: sem isto, o frontend
    #: teria de reimplementá-la — e foi exatamente assim que a tela passou a
    #: dizer "não se edita mais aqui" enquanto a API aceitava a edição.
    planilha_editavel = serializers.SerializerMethodField()
    planilha_fechada_porque = serializers.SerializerMethodField()
    medicoes_count = serializers.IntegerField(source="medicoes.count", read_only=True)

    class Meta:
        model = ContratoObra
        fields = "__all__"
        read_only_fields = [
            "tenant", "criado_em", "atualizado_em",
            "excluido_em", "excluido_por", "motivo_exclusao",
        ]

    def validate(self, dados):
        """As coerências que a constraint do banco cobra, ditas em português.

        A `CheckConstraint` do model é a rede de baixo — ela vale para o comando
        de bancada e para a importação. Aqui a mesma regra vira **mensagem**: um
        `IntegrityError` traduzido diz "violação de restrição", e quem está
        preenchendo o formulário precisa saber qual campo falta.
        """
        def valor(campo):
            if campo in dados:
                return dados[campo]
            return getattr(self.instance, campo, None)

        regime = valor("regime") or RegimeContrato.UNITARIO
        valor_global = valor("valor_global")
        erros = {}

        if regime == RegimeContrato.UNITARIO and valor_global is not None:
            erros["valor_global"] = (
                "No regime de preço unitário o valor do contrato é a soma dos "
                "itens — deixe este campo vazio para não criar um segundo total "
                "que diverge da planilha."
            )
        if regime in (RegimeContrato.GLOBAL, RegimeContrato.ADMINISTRACAO):
            if valor_global is None:
                erros["valor_global"] = (
                    f"O regime '{regime}' precisa do valor fechado do contrato."
                )
        if regime == RegimeContrato.ADMINISTRACAO and valor("taxa_administracao") is None:
            erros["taxa_administracao"] = (
                "Contrato por administração precisa da taxa — é ela que separa o "
                "reembolso de custo da remuneração do empreiteiro."
            )
        if regime != RegimeContrato.ADMINISTRACAO and valor("taxa_administracao") is not None:
            erros["taxa_administracao"] = (
                "A taxa de administração só se aplica ao regime de administração."
            )

        # A retenção sem natureza é dinheiro parado sem dono: ninguém sabe sob
        # que condição ele volta, e a liberação não tem o que declarar.
        from .models import NaturezaRetencao

        retencao = valor("retencao_percentual") or 0
        if retencao > 0 and valor("retencao_natureza") == NaturezaRetencao.NENHUMA:
            erros["retencao_natureza"] = (
                "Há retenção definida — diga de que natureza ela é, senão não há "
                "como declarar a condição que a libera."
            )
        if valor("regime_publico") and valor("limite_acrescimo_percentual") is None:
            erros["limite_acrescimo_percentual"] = (
                "Regime público ligado: informe o limite legal de acréscimo deste "
                "contrato. O sistema confere contra o número que você declarar — "
                "ele não escolhe o percentual por você."
            )
        if erros:
            raise serializers.ValidationError(erros)
        return dados

    def get_planilha_editavel(self, obj) -> bool:
        return services.planilha_editavel(obj)[0]

    def get_planilha_fechada_porque(self, obj) -> str:
        return services.planilha_editavel(obj)[1]


def _decimais_em_string(dados):
    """`Decimal` vira string no JSON, **recursivamente** — e só o `Decimal`.

    O `float` do JSON tem 53 bits de mantissa e não representa centavo
    exatamente; é por isso que o DRF serializa `DecimalField` como string, e é
    por isso que estes dicionários montados à mão precisam do mesmo tratamento.

    **A recursão não é detalhe.** A primeira escrita fazia
    `{chave: str(valor) for chave, valor in totais.items()}` — um nível só —, e
    isso transformava a **lista de deduções** na string `"[]"`. O boletim
    percorre essa lista, e uma string não tem `.map`: a tela da medição ficava
    **em branco** (`r.deducoes.map is not a function`), que é como o dono
    encontrou o defeito. Achatar estrutura com `str()` é sempre isto — funciona
    enquanto o valor for escalar e some com a tela no dia em que não for.
    """
    from decimal import Decimal as _D

    if isinstance(dados, _D):
        return str(dados)
    if isinstance(dados, dict):
        return {chave: _decimais_em_string(valor) for chave, valor in dados.items()}
    if isinstance(dados, (list, tuple)):
        return [_decimais_em_string(valor) for valor in dados]
    return dados


def _escada_de(obj):
    """O degrau em que o documento está parado, para a tela dizer *de quem* se
    espera a decisão — em vez de um "em aprovação" que não ajuda ninguém.

    **Ordena em Python, e isso não é preguiça.** `obj.aprovacoes.order_by(...)`
    dispara uma consulta nova mesmo com o `prefetch_related` armado, porque
    qualquer refinamento do queryset invalida o cache do prefetch. Numa lista de
    100 medições isso são 100 consultas — e era exatamente o que a carteira de
    contratos fazia antes desta função existir.
    """
    pedidos = sorted(
        obj.aprovacoes.all(), key=lambda p: p.solicitado_em, reverse=True,
    )
    if not pedidos:
        return None
    pedido = pedidos[0]
    return {
        "pedido_id": pedido.pk,
        "estado": pedido.estado,
        "nivel": getattr(pedido.nivel_atual, "nome", None),
        "permissao_exigida": getattr(pedido.nivel_atual, "permissao_exigida", None),
        "solicitante": pedido.solicitante_nome,
        # **As assinaturas.** É o que o boletim imprime e o que responde "quem
        # autorizou este pagamento, quando e com que autoridade" — a pergunta
        # que a tela não sabia responder, embora o `Atesto` guarde tudo desde a
        # PDCA.0. Ordena em Python pelo mesmo motivo do `sorted` acima: um
        # `order_by` aqui invalidaria o prefetch e viraria consulta por linha.
        "atestos": [
            {
                "atesto_id": atesto.pk,
                "nivel_ordem": atesto.nivel_ordem,
                "nivel_nome": atesto.nivel_nome,
                "decisao": atesto.decisao,
                "autor": atesto.autor_nome,
                "permissao_conferida": atesto.permissao_conferida,
                "decidido_em": atesto.decidido_em,
                "observacao": atesto.observacao,
            }
            for atesto in sorted(
                pedido.atestos.all(), key=lambda a: a.nivel_ordem,
            )
        ],
    }


class ItemMedicaoSerializer(TenantScopedModelSerializer):
    codigo = serializers.CharField(source="item_contrato.codigo", read_only=True)
    descricao = serializers.CharField(
        source="item_contrato.descricao", read_only=True,
    )
    unidade = serializers.CharField(source="item_contrato.unidade", read_only=True)
    origem_rotulo = serializers.CharField(source="get_origem_display", read_only=True)
    valor = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True,
    )
    #: A diferença entre o que o sistema propôs e o que o gestor confirmou. É o
    #: que torna o ajuste auditável na tela — sem isto, a proposta automática
    #: vira caixa preta.
    ajuste = serializers.SerializerMethodField()

    class Meta:
        model = ItemMedicao
        fields = "__all__"
        read_only_fields = ["tenant"]

    def get_ajuste(self, obj):
        if obj.quantidade_proposta is None:
            return None
        return obj.quantidade - obj.quantidade_proposta


class DeducaoMedicaoSerializer(TenantScopedModelSerializer):
    """Uma linha de desconto do boletim, com o valor **aplicado** resolvido.

    O valor aplicado depende do bruto da medição (o percentual sem base incide
    sobre ele), e por isso não é campo: é derivado na leitura, como todo o resto
    do dinheiro desta seção.
    """

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    valor_aplicado = serializers.SerializerMethodField()

    class Meta:
        model = DeducaoMedicao
        fields = "__all__"
        read_only_fields = ["tenant"]

    def get_valor_aplicado(self, obj):
        bruto = services.totais_da_medicao(obj.medicao)["bruto"]
        return str(services.valor_da_deducao(obj, bruto))


class LinhaDeDeducaoSerializer(serializers.Serializer):
    """A entrada da reescrita das deduções. `percentual` **ou** `valor`."""

    tipo = serializers.ChoiceField(choices=TipoDeducao.choices)
    descricao = serializers.CharField(required=False, allow_blank=True)
    base_calculo = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True,
    )
    percentual = serializers.DecimalField(
        max_digits=6, decimal_places=3, required=False, allow_null=True,
    )
    valor = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True,
    )


class MedicaoSerializer(TenantScopedModelSerializer):
    contrato_numero = serializers.CharField(
        source="contrato.numero", read_only=True,
    )
    fornecedor_nome = serializers.CharField(
        source="contrato.fornecedor.razao_social", read_only=True,
    )
    obra_nome = serializers.CharField(
        source="contrato.obra.nome_obra", read_only=True,
    )
    #: O **id** da obra, e não só o nome: desde que a medição passou a morar sob
    #: a obra (`/app/pdca/obra/:id/contratos/:id`), a fila de decisão precisa
    #: montar o endereço sozinha. Sem ele a tela faria uma consulta ao contrato
    #: por linha da fila só para descobrir para onde navegar.
    contrato_obra = serializers.IntegerField(
        source="contrato.obra_id", read_only=True,
    )
    regime = serializers.CharField(source="contrato.regime", read_only=True)
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)
    custo_origem_rotulo = serializers.CharField(
        source="get_custo_origem_display", read_only=True,
    )
    itens = ItemMedicaoSerializer(many=True, read_only=True)
    #: Bruto → retenção → líquido, calculados na leitura (§4.9). Não há coluna
    #: para nenhum dos três — o que a tela mostra é o que o servidor soma agora,
    #: sobre as parcelas congeladas.
    #: As linhas de desconto do boletim. Vêm no documento, e não numa chamada
    #: à parte, porque o líquido não se explica sem elas — e é o líquido que
    #: vira título no ERP.
    deducoes = DeducaoMedicaoSerializer(many=True, read_only=True)
    totais = serializers.SerializerMethodField()
    escada = serializers.SerializerMethodField()

    class Meta:
        model = Medicao
        fields = "__all__"
        read_only_fields = [
            "tenant", "numero", "apurada_em", "congelada_em", "conta_pagar_ref",
            "status", "excluido_em", "excluido_por", "motivo_exclusao",
        ]

    def get_totais(self, obj):
        return _decimais_em_string(services.totais_da_medicao(obj))

    def get_escada(self, obj):
        return _escada_de(obj)


class MedicaoResumoSerializer(MedicaoSerializer):
    """A medição **sem as linhas** — o que a lista precisa, e só isso.

    A lista do contrato desenha `#3 · aprovada · R$ 40.000`, e o serializer
    completo mandava junto todos os itens de todas as medições: numa carteira
    com 40 boletins de 300 linhas, meio megabyte de JSON para escrever quarenta
    linhas de texto. Aqui a régua é a do gesto — quem abre um documento pede o
    documento (`retrieve`), e aí as linhas vêm.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("itens", "deducoes"):
            self.fields.pop(campo, None)


class PropostaDeMedicaoSerializer(serializers.Serializer):
    """Os parâmetros da prévia — o gesto de "o que se mede neste período?"."""

    inicio = serializers.DateField()
    fim = serializers.DateField()


class LinhaDeMedicaoSerializer(serializers.Serializer):
    """Uma linha da grade, como a tela a envia.

    `quantidade` tem default zero porque uma linha pode existir **só** pelo
    material estocado (o serviço ainda não começou e o material já está na obra,
    pago). Exigir a quantidade aqui obrigaria a tela a mandar um zero explícito
    que não quer dizer nada.
    """

    item_contrato_id = serializers.IntegerField()
    quantidade = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, default=0,
    )
    #: **Saldo** de material posto na obra, não delta (ver o campo no model).
    quantidade_estocada = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, default=0,
    )
    #: A memória de cálculo da linha — "medido em campo com o fiscal, croqui
    #: anexo". Some da grade e aparece no boletim, que é onde ela é lida.
    observacao = serializers.CharField(required=False, allow_blank=True)


class AbrirMedicaoSerializer(serializers.Serializer):
    """Abre o boletim. `linhas` ausente aceita a proposta inteira; `linhas`
    presente é o gestor conferindo antes de abrir."""

    inicio = serializers.DateField()
    fim = serializers.DateField()
    linhas = LinhaDeMedicaoSerializer(many=True, required=False)
    custo_reembolsavel = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True,
    )
    observacao = serializers.CharField(required=False, allow_blank=True)


class SubmeterSerializer(serializers.Serializer):
    observacao = serializers.CharField(required=False, allow_blank=True)


class RetificarSerializer(serializers.Serializer):
    """O motivo é obrigatório — mesmo princípio do estorno do apontamento: é ele
    que separa a correção do erro."""

    motivo = serializers.CharField()


class CabecalhoDeMedicaoSerializer(serializers.Serializer):
    """Os campos do documento que não são a grade.

    Existe porque a medição **não tem `PATCH`** (ver a nota do viewset): o
    documento tem ciclo de vida, e um `PATCH` genérico publicaria um caminho que
    atravessa o congelamento. Estes dois campos, porém, mudam em rascunho tanto
    quanto uma quantidade — o custo reembolsável é a única coisa que se mede num
    contrato por administração, e sem este endpoint esse regime inteiro fica sem
    porta na tela.
    """

    custo_reembolsavel = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True,
    )
    observacao = serializers.CharField(required=False, allow_blank=True)


class AtestarSerializer(serializers.Serializer):
    """Um degrau da escada. **Reprovar exige motivo.**

    A planta manda registrar o atesto com autor, data e observação; aprovar sem
    comentário é legítimo (a assinatura já é a mensagem), mas reprovar sem dizer
    por quê devolve o documento a quem o montou sem nenhuma informação sobre o
    que corrigir — e a próxima versão volta com o mesmo problema.
    """

    aprovar = serializers.BooleanField(default=True)
    observacao = serializers.CharField(required=False, allow_blank=True)

    def validate(self, dados):
        if not dados.get("aprovar", True) and not (
            dados.get("observacao") or ""
        ).strip():
            raise serializers.ValidationError({
                "observacao": (
                    "Diga por que está reprovando — quem montou o documento "
                    "precisa saber o que corrigir."
                ),
            })
        return dados


class ItemAditivoSerializer(TenantScopedModelSerializer):
    """A linha do aditivo, com o item de contrato resolvido.

    `codigo` e `descricao` vêm do item quando ele existe e dos campos `_novo`
    quando o aditivo ainda não foi aplicado — é o que permite conferir um
    aditivo de inclusão na tela antes de a linha existir na planilha.
    """

    acao_rotulo = serializers.CharField(source="get_acao_display", read_only=True)
    codigo = serializers.SerializerMethodField()
    descricao = serializers.SerializerMethodField()
    unidade = serializers.SerializerMethodField()
    quantidade_atual = serializers.SerializerMethodField()

    class Meta:
        model = ItemAditivo
        fields = "__all__"
        read_only_fields = ["tenant", "preco_unitario_anterior"]

    def get_codigo(self, obj):
        return obj.item_contrato.codigo if obj.item_contrato_id else obj.codigo_novo

    def get_descricao(self, obj):
        return (
            obj.item_contrato.descricao if obj.item_contrato_id
            else obj.descricao_nova
        )

    def get_unidade(self, obj):
        return (
            obj.item_contrato.unidade if obj.item_contrato_id else obj.unidade_nova
        )

    def get_quantidade_atual(self, obj):
        """A quantidade que a linha tem **hoje** — o denominador do delta.

        Sem ela, a tela mostra "+120" e quem lê não sabe se é 120 sobre 200 ou
        sobre 20.000, que é a diferença entre um ajuste e um contrato novo.
        """
        if obj.item_contrato_id is None:
            return None
        atual = services.contratado_atual_por_item(obj.aditivo.contrato)
        return str(atual.get(obj.item_contrato_id, obj.item_contrato.quantidade_contratada))


class AditivoContratoSerializer(TenantScopedModelSerializer):
    """O aditivo com o resumo financeiro resolvido — nunca somado na tela."""

    contrato_numero = serializers.CharField(source="contrato.numero", read_only=True)
    contrato_obra = serializers.IntegerField(source="contrato.obra_id", read_only=True)
    fornecedor_nome = serializers.CharField(
        source="contrato.fornecedor.razao_social", read_only=True,
    )
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)
    itens = ItemAditivoSerializer(many=True, read_only=True)
    resumo = serializers.SerializerMethodField()
    escada = serializers.SerializerMethodField()

    class Meta:
        model = AditivoContrato
        fields = "__all__"
        read_only_fields = [
            "tenant", "numero", "status", "criado_em", "aplicado_em",
            "excluido_em", "excluido_por", "motivo_exclusao",
        ]

    def get_resumo(self, obj):
        return _decimais_em_string(services.resumo_do_aditivo(obj))

    def get_escada(self, obj):
        return _escada_de(obj)


class LinhaDeAditivoSerializer(serializers.Serializer):
    """A entrada da reescrita das linhas do aditivo.

    `item_contrato_id` é obrigatório em tudo que não seja inclusão; a inclusão
    traz o item que ainda não existe nos campos `_novo`. A conferência de quais
    campos cada ação exige mora no serviço, e não aqui, porque ela precisa da
    planilha contratual inteira (código repetido, item já medido) — e porque a
    lista de problemas sai de uma vez, em vez de um erro por requisição.
    """

    acao = serializers.ChoiceField(choices=AcaoAditivo.choices)
    item_contrato_id = serializers.IntegerField(required=False, allow_null=True)
    quantidade_delta = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False,
    )
    preco_unitario = serializers.DecimalField(
        max_digits=15, decimal_places=4, required=False, allow_null=True,
    )
    codigo_novo = serializers.CharField(required=False, allow_blank=True)
    descricao_nova = serializers.CharField(required=False, allow_blank=True)
    unidade_nova = serializers.CharField(required=False, allow_blank=True)
    observacao = serializers.CharField(required=False, allow_blank=True)


class AbrirAditivoSerializer(serializers.Serializer):
    """Abre o aditivo. As linhas são opcionais — aditivo só de prazo não tem."""

    contrato = serializers.IntegerField()
    objeto = serializers.CharField()
    justificativa = serializers.CharField()
    data_assinatura = serializers.DateField(required=False, allow_null=True)
    nova_data_fim = serializers.DateField(required=False, allow_null=True)
    itens = LinhaDeAditivoSerializer(many=True, required=False)


class LiberacaoRetencaoSerializer(TenantScopedModelSerializer):
    contrato_numero = serializers.CharField(
        source="contrato.numero", read_only=True,
    )
    fornecedor_nome = serializers.CharField(
        source="contrato.fornecedor.razao_social", read_only=True,
    )
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LiberacaoRetencao
        fields = "__all__"
        read_only_fields = [
            "tenant", "criado_em", "congelada_em", "conta_pagar_ref", "status",
            "solicitada_por", "excluido_em", "excluido_por", "motivo_exclusao",
        ]


class SolicitarLiberacaoSerializer(serializers.Serializer):
    valor = serializers.DecimalField(max_digits=15, decimal_places=2)
    data = serializers.DateField()
    #: **`allow_blank=True` de propósito**, e não por frouxidão. O `CharField`
    #: padrão recusa o vazio com "este campo não pode ser em branco" — e isso
    #: tornaria **inalcançável pela API** a recusa do serviço, que é a única que
    #: diz *qual* condição o contrato exige ("a cláusula deste contrato diz:
    #: recebimento definitivo da obra"). Quem está liberando caução precisa ler
    #: a cláusula, não o nome do campo. A obrigatoriedade continua existindo;
    #: ela só passou a ser cobrada por quem tem o contexto para explicá-la.
    condicao_atendida = serializers.CharField(allow_blank=True)
