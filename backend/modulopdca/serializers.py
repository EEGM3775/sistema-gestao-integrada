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

from nucleo.tenant_validators import TenantScopedModelSerializer
from nucleo.upload_validation import UploadValidationMixin

from . import services
from .models import (
    ApontamentoAvanco, Atividade, CalendarioTrabalho, Cronograma,
    ExcecaoCalendario, LocalObra, OrigemApontamento, Precedencia,
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
    a mesma régua do documento de obra e do anexo do diário.
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
