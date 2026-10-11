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
from nucleo.field_masking import FieldMaskingSerializerMixin
from nucleo.tenant_validators import TenantScopedModelSerializer
from nucleo.upload_validation import UploadValidationMixin
from fornecedores.models import Fornecedor
from rh.models import Funcionario

from . import services
from .impexp import (
    ESPECIE_EFICACIA, ESPECIE_FOTO, ESPECIE_ITEM, ESPECIE_NC, RECURSO_FOTO,
    RECURSO_NC, RECURSO_VERIFICACAO,
    ESPECIE_ANEXO, ESPECIE_ATESTADO, RECURSO_SSMA, RECURSO_SSMA_CLINICO,
)
from .models import (
    ParcelaReajusteContrato,
    AcaoAditivo, AditivoContrato, AntecedenciaDeCompra, ApontamentoAvanco, Atividade,
    CalendarioTrabalho, ContratoObra, Cronograma, DeducaoMedicao,
    ExcecaoCalendario, ItemAditivo, ItemContrato, ItemMedicao,
    CausaNaoCumprimento, EquipeObra, ItemProgramacao, LiberacaoRetencao, LocalObra,
    MaterialDaAtividade,
    Medicao, OrigemApontamento, Precedencia, ProgramacaoSemanal, Restricao,
    RegimeContrato, TipoDeducao,
    GravidadeNC, ItemModeloVerificacao, ItemVerificacao, ModeloVerificacao,
    NaoConformidade, PlanoAcao, ResultadoItem, Verificacao,
    VerificacaoEficacia,
    AnexoOcorrencia, ClassificacaoOcorrencia, DialogoSeguranca, Ocorrencia,
    ParticipanteDDS, TipoCAT, TipoOcorrencia,
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


class AntecedenciaDeCompraSerializer(TenantScopedModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)

    class Meta:
        model = AntecedenciaDeCompra
        fields = "__all__"
        read_only_fields = ["tenant", "atualizado_em"]


class GerarDemandaDoPlanoSerializer(serializers.Serializer):
    #: Chaves de insumo da fila (vazio = tudo o que falta comprar).
    insumos = serializers.ListField(child=serializers.CharField(max_length=300), required=False)
    #: Só o que se precisa pedir até esta data.
    ate = serializers.DateField(required=False, allow_null=True)


class CalendarioTrabalhoSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    excecoes = ExcecaoCalendarioSerializer(many=True, read_only=True)
    #: De onde são os feriados: o UF/IBGE digitado ou o lugar da obra (pelo
    #: endereço, como a Agenda). A tela diz "feriados de Nazaré/BA".
    localidade_feriados = serializers.SerializerMethodField()

    class Meta:
        model = CalendarioTrabalho
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em", "atualizado_em"]

    def get_localidade_feriados(self, obj):
        if not obj.considera_feriados:
            return None
        from .services import localidade_dos_feriados
        return localidade_dos_feriados(obj)

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
            # O vínculo com o orçamento é escrito pelos verbos `gerar-do-orcamento`
            # e `atualizar-do-orcamento`, nunca pelo PATCH do plano.
            "orcamento_origem",
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
            "critica", "criado_em", "atualizado_em", "peso_do_orcamento",
        ]

    def get_local_rotulo(self, obj) -> str:
        return str(obj.local) if obj.local_id else ""

    def get_item_orcado_rotulo(self, obj) -> str:
        return str(obj.item_orcado) if obj.item_orcado_id else ""

    def get_tem_filhos(self, obj) -> bool:
        return obj.filhos.exists()

    def update(self, instance, validated_data):
        # O planejador digitou outro peso: deixa de ser o valor da etapa no
        # orçamento e passa a ser dele — não pode seguir contando como orçado.
        if ("peso_informado" in validated_data
                and validated_data["peso_informado"] != instance.peso_informado):
            instance.peso_do_orcamento = False
        return super().update(instance, validated_data)

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

        Ligar atividades de cronogramas diferentes, ligar uma etapa a algo que
        está dentro dela, fechar um ciclo ou mexer num plano já publicado: todas
        apareceriam depois como "o cronograma não calcula", numa tela que não
        saberia dizer qual das centenas de setas está errada.

        A **etapa** (sintética) pode ser ligada desde 09/10/2026 — é a ligação de
        fase, que o CPM expande nas folhas (`services.ligacoes_das_folhas`).
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
        for de_cima, de_baixo in ((origem, destino), (destino, origem)):
            no = de_baixo.pai
            while no is not None:
                if no.pk == de_cima.pk:
                    raise serializers.ValidationError(
                        f"'{de_baixo.codigo}' está dentro de '{de_cima.codigo}'. Uma etapa "
                        "não se liga ao que ela mesma contém — ligue as atividades de "
                        "dentro entre si."
                    )
                no = no.pai

        atual = getattr(self.instance, "pk", None)
        if self._fecha_ciclo(origem, destino, dados, atual):
            raise serializers.ValidationError(
                f"Esta ligação fecharia um ciclo: '{destino.codigo}' já leva, direta ou "
                f"indiretamente, a '{origem.codigo}'."
            )
        return dados

    def _fecha_ciclo(self, origem, destino, dados, atual) -> bool:
        """A seta nova, somada à rede, deixa o grafo **expandido** sem ordem?

        Conferido nas folhas porque, com ligação de fase, o laço pode passar por
        dentro de uma etapa sem que nenhuma seta gravada o feche sozinha."""
        nova = services.LigacaoEntreFolhas(
            0, origem.pk, destino.pk,
            dados.get("tipo", getattr(self.instance, "tipo", Precedencia.Tipo.FS)),
            dados.get("atraso_dias", getattr(self.instance, "atraso_dias", 0)),
        )
        try:
            services.verificar_rede(origem.cronograma, nova=nova, ignorar=atual)
        except DjangoValidationError as erro:
            if "ciclo" in " ".join(erro.messages):
                return True
            raise serializers.ValidationError(erro.messages)
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


class InserirAtividadeSerializer(serializers.Serializer):
    """A linha que nasce **na posição** — o Enter da grade."""

    pai = serializers.IntegerField(required=False, allow_null=True)
    depois_de = serializers.IntegerField(required=False, allow_null=True)
    nome = serializers.CharField(max_length=200, required=False, allow_blank=True)
    duracao_dias = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    eh_marco = serializers.BooleanField(required=False, default=False)
    etapa = serializers.IntegerField(required=False, allow_null=True)


class MoverAtividadeSerializer(serializers.Serializer):
    """Para onde a linha vai: debaixo de quem, e em que posição entre as irmãs."""

    pai = serializers.IntegerField(required=False, allow_null=True)
    posicao = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class LinhaImportadaSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=400, allow_blank=True)
    codigo = serializers.CharField(max_length=60, required=False, allow_blank=True)
    nivel = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    duracao_dias = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True,
    )
    eh_marco = serializers.BooleanField(required=False, allow_null=True, default=None)
    predecessoras = serializers.CharField(max_length=500, required=False, allow_blank=True)
    nao_comecar_antes_de = serializers.CharField(
        max_length=30, required=False, allow_blank=True, allow_null=True,
    )
    peso = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)


class ImportarLinhasSerializer(serializers.Serializer):
    """O corpo de `importar-linhas/` — colar do Excel ou abrir o XML do Project."""

    linhas = LinhaImportadaSerializer(many=True)
    referencia = serializers.ChoiceField(choices=["codigo", "linha"], default="codigo")


class GerarDoOrcamentoSerializer(serializers.Serializer):
    orcamento = serializers.IntegerField()
    #: Duração da etapa que ainda não tem datas no cronograma do orçamento.
    duracao_padrao = serializers.IntegerField(required=False, default=5, min_value=1)
    simular = serializers.BooleanField(required=False, default=False)


class AtualizarDoOrcamentoSerializer(serializers.Serializer):
    orcamento = serializers.IntegerField(required=False, allow_null=True)
    duracao_padrao = serializers.IntegerField(required=False, default=5, min_value=1)


class AnexarModeloSerializer(serializers.Serializer):
    modelo = serializers.IntegerField()


class RestaurarLinhasSerializer(serializers.Serializer):
    """O retrato que a tela tirou antes de excluir — o desfazer da exclusão."""

    pai = serializers.IntegerField(required=False, allow_null=True)
    posicao = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    atividades = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    ligacoes = serializers.ListField(child=serializers.DictField(), required=False, default=list)


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


class ParcelaReajusteContratoSerializer(TenantScopedModelSerializer):
    indice_codigo = serializers.CharField(source="indice.codigo", read_only=True)
    indice_nome = serializers.CharField(source="indice.nome", read_only=True)

    class Meta:
        model = ParcelaReajusteContrato
        fields = "__all__"
        read_only_fields = ["tenant"]


class ContratoObraSerializer(TenantScopedModelSerializer):
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    #: O nome **da parte** — o empreiteiro no custo, o contratante na receita.
    #: O campo guarda o nome antigo porque toda a tela de medição já o lê.
    fornecedor_nome = serializers.CharField(source="parte_nome", read_only=True)
    lado_rotulo = serializers.CharField(source="get_lado_display", read_only=True)
    parcelas_reajuste = ParcelaReajusteContratoSerializer(many=True, read_only=True)
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
    #: O pedido de serviço do Suprimentos ao lado do que a medição já pagou.
    pedido_scm_resumo = serializers.SerializerMethodField()

    class Meta:
        model = ContratoObra
        fields = "__all__"
        read_only_fields = [
            "tenant", "criado_em", "atualizado_em",
            "excluido_em", "excluido_por", "motivo_exclusao",
        ]

    def get_pedido_scm_resumo(self, obj):
        pedido = obj.pedido_scm
        if pedido is None:
            return None
        from decimal import Decimal

        from django.db.models import F, Sum

        valor = pedido.valor_total
        if valor is None:
            valor = pedido.itens.aggregate(v=Sum(F("quantidade") * F("preco_unitario")))["v"] or Decimal("0")
        medido = (ItemMedicao.objects
                  .filter(medicao__contrato=obj, medicao__status=Medicao.Status.APROVADA)
                  .aggregate(v=Sum(F("quantidade") * F("preco_unitario")))["v"] or Decimal("0"))
        return {
            "pedido": pedido.pk, "status": pedido.status, "status_rotulo": pedido.get_status_display(),
            "valor_pedido": str(Decimal(valor).quantize(Decimal("0.01"))),
            "medido_aprovado": str(Decimal(medido).quantize(Decimal("0.01"))),
            "saldo": str((Decimal(valor) - Decimal(medido)).quantize(Decimal("0.01"))),
        }

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

        pedido = valor("pedido_scm")
        obra = valor("obra")
        if pedido is not None and obra is not None:
            obra_do_pedido = getattr(getattr(pedido, "centro_custo", None), "obra_id", None)
            if obra_do_pedido not in (None, getattr(obra, "pk", obra)):
                raise serializers.ValidationError({
                    "pedido_scm": "Este pedido é do centro de custo de outra obra.",
                })
            if pedido.tenant_id != getattr(obra, "tenant_id", pedido.tenant_id):
                raise serializers.ValidationError({"pedido_scm": "Pedido inválido."})

        regime = valor("regime") or RegimeContrato.UNITARIO
        valor_global = valor("valor_global")
        erros = {}

        # A parte conforme o lado (decisão do dono, 10/10/2026: o contrato com
        # o contratante é o mesmo documento, do lado da receita).
        from .models import LadoContrato

        lado = valor("lado") or LadoContrato.CUSTO
        if lado == LadoContrato.CUSTO:
            if valor("fornecedor") is None:
                erros["fornecedor"] = "Contrato de empreiteiro precisa do empreiteiro."
            if valor("cliente") is not None:
                erros["cliente"] = "Contrato de empreiteiro não tem contratante — é custo."
        else:
            if valor("cliente") is None:
                erros["cliente"] = "Contrato com o contratante precisa do cliente que encomendou a obra."
            if valor("fornecedor") is not None:
                erros["fornecedor"] = "Contrato com o contratante não tem empreiteiro — é receita."
            if valor("pedido_scm") is not None:
                erros["pedido_scm"] = "Pedido de serviço do Suprimentos é do lado do custo."

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
        cliente = valor("cliente")
        if cliente is not None and obra is not None and cliente.tenant_id != getattr(obra, "tenant_id", cliente.tenant_id):
            erros["cliente"] = "Cliente inválido."
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
        source="contrato.parte_nome", read_only=True,
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
    lado = serializers.CharField(source="contrato.lado", read_only=True)
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
    #: **O título do ERP, visto de dentro do PDCA.** Existe para o botão
    #: "Cancelar" saber o que vai acontecer *antes* de alguém clicar: com o
    #: título ainda aberto ele cancela os dois; com baixa em cima, a medição só
    #: se conserta por retificadora. O aviso da tela e a trava do servidor saem
    #: do mesmo `services.estado_do_titulo` — dois lugares divergiriam na
    #: primeira mudança de regra.
    #:
    #: `null` quando não há título: medição que ainda não foi aprovada, ou
    #: aprovada com líquido zero (a retificadora que zera outra não gera papel).
    titulo_erp = serializers.SerializerMethodField()

    class Meta:
        model = Medicao
        fields = "__all__"
        read_only_fields = [
            "tenant", "numero", "apurada_em", "congelada_em", "conta_pagar_ref",
            "status", "excluido_em", "excluido_por", "motivo_exclusao",
            # O reajuste sai da fórmula do contrato e do índice publicado —
            # nunca do PATCH (`services.recalcular_reajuste`).
            "conta_receber_ref", "valor_reajuste", "reajuste_memoria", "reajuste_provisorio",
        ]

    def get_totais(self, obj):
        return _decimais_em_string(services.totais_da_medicao(obj))

    def get_escada(self, obj):
        return _escada_de(obj)

    def get_titulo_erp(self, obj):
        estado = services.estado_do_titulo(obj)
        return _decimais_em_string(estado) if estado is not None else None


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
        #: **E sem o título, que é uma consulta por linha.** A lista desenha o
        #: status da medição, não o do título — é a mesma lição do D136: o que
        #: custa uma consulta por item não entra na listagem, entra no
        #: documento aberto.
        self.fields.pop("titulo_erp", None)


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
        source="contrato.parte_nome", read_only=True,
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
    #: A retenção própria que a linha dá ao item. Nula = não mexe.
    retencao_percentual = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
        min_value=0, max_value=100,
    )
    observacao = serializers.CharField(required=False, allow_blank=True)


class AbrirAditivoSerializer(serializers.Serializer):
    """Abre o aditivo. As linhas são opcionais — aditivo só de prazo não tem."""

    contrato = serializers.IntegerField()
    objeto = serializers.CharField()
    justificativa = serializers.CharField()
    data_assinatura = serializers.DateField(required=False, allow_null=True)
    nova_data_fim = serializers.DateField(required=False, allow_null=True)
    #: A nova retenção do contrato, quando o aditivo muda a cláusula.
    retencao_percentual_nova = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
        min_value=0, max_value=100,
    )
    itens = LinhaDeAditivoSerializer(many=True, required=False)


class EditarAditivoSerializer(serializers.Serializer):
    """O cabeçalho do rascunho. Só o que vier no corpo muda."""

    objeto = serializers.CharField(required=False)
    justificativa = serializers.CharField(required=False)
    data_assinatura = serializers.DateField(required=False, allow_null=True)
    nova_data_fim = serializers.DateField(required=False, allow_null=True)
    retencao_percentual_nova = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
        min_value=0, max_value=100,
    )


class LiberacaoRetencaoSerializer(TenantScopedModelSerializer):
    contrato_numero = serializers.CharField(
        source="contrato.numero", read_only=True,
    )
    fornecedor_nome = serializers.CharField(
        source="contrato.parte_nome", read_only=True,
    )
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LiberacaoRetencao
        fields = "__all__"
        read_only_fields = [
            "tenant", "criado_em", "congelada_em", "conta_pagar_ref", "status",
            "solicitada_por", "excluido_em", "excluido_por", "motivo_exclusao",
            "conta_receber_ref",
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


# ---------------------------------------------------------------------------
# PDCA.5 — Last Planner
# ---------------------------------------------------------------------------


class CausaNaoCumprimentoSerializer(TenantScopedModelSerializer):
    categoria_rotulo = serializers.CharField(
        source="get_categoria_display", read_only=True,
    )

    class Meta:
        model = CausaNaoCumprimento
        fields = [
            "causa_id", "codigo", "nome", "categoria", "categoria_rotulo",
            "de_fabrica", "ativo",
        ]
        read_only_fields = ["causa_id", "de_fabrica"]

    def validate_codigo(self, valor):
        #: O código de fábrica é a âncora da comparação entre obras — e um dia
        #: entre empresas na Esfera de Rede. O nome é do tenant; o código, não.
        if self.instance and self.instance.de_fabrica and valor != self.instance.codigo:
            raise serializers.ValidationError(
                "O código de uma causa de fábrica não muda — é por ele que o "
                "histórico de duas obras se compara. Renomeie o nome dela para "
                "o vocabulário da sua casa; o código fica."
            )
        return valor


class EquipeObraSerializer(TenantScopedModelSerializer):
    """A composição da equipe: funcionários (RH) e fornecedores (empreiteiras).

    O nome vazio nasce dos membros — "Zé Silva + Construtora X" — porque o
    nome é o rótulo que viaja no cartão e que o encarregado procura no campo.
    """

    nome = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    funcionarios = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Funcionario.objects.all(),
    )
    fornecedores = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Fornecedor.objects.all(),
    )
    membros = serializers.SerializerMethodField()

    class Meta:
        model = EquipeObra
        fields = [
            "equipe_id", "obra", "nome", "funcionarios", "fornecedores",
            "membros", "ativa",
        ]
        read_only_fields = ["equipe_id"]

    def get_membros(self, obj) -> list[dict]:
        return (
            [{"tipo": "funcionario", "id": f.pk, "nome": f.nome_completo}
             for f in obj.funcionarios.all()]
            + [{"tipo": "fornecedor", "id": f.pk, "nome": f.razao_social}
               for f in obj.fornecedores.all()]
        )

    def validate(self, dados):
        tenant_id = getattr(self.context.get("request"), "user", None)
        tenant_id = getattr(tenant_id, "tenant_id", None)
        obra = dados.get("obra") or getattr(self.instance, "obra", None)
        funcionarios = dados.get(
            "funcionarios",
            list(self.instance.funcionarios.all()) if self.instance else [],
        )
        fornecedores = dados.get(
            "fornecedores",
            list(self.instance.fornecedores.all()) if self.instance else [],
        )
        if tenant_id is not None:
            alheios = [m for m in [obra, *funcionarios, *fornecedores]
                       if m is not None and m.tenant_id != tenant_id]
            if alheios:
                raise serializers.ValidationError("Há membro ou obra que não é desta empresa.")
        if not funcionarios and not fornecedores:
            raise serializers.ValidationError(
                "A equipe é a composição de quem trabalha: escolha ao menos um "
                "funcionário ou um fornecedor."
            )
        nome = (dados.get("nome") or "").strip()
        if not nome and (self.instance is None or "nome" in dados):
            partes = [f.nome_completo.split()[0] if f.nome_completo else "" for f in funcionarios]
            partes += [f.razao_social for f in fornecedores]
            nome = " + ".join(p for p in partes if p)[:150] or "Equipe"
        if nome:
            dados["nome"] = nome
            repetida = EquipeObra.objects.filter(obra=obra, nome__iexact=nome)
            if self.instance is not None:
                repetida = repetida.exclude(pk=self.instance.pk)
            if repetida.exists():
                raise serializers.ValidationError({
                    "nome": f"Já existe a equipe \"{nome}\" nesta obra — dê outro nome.",
                })
        return dados


class GerarRitmoSerializer(serializers.Serializer):
    """O traço da linha de balanço — **um serviço, uma sequência de locais, um ritmo**.

    É um `Serializer` puro, e não de modelo, pela mesma razão do
    `GeracaoEmLoteSerializer` da PDCA.0: o que entra aqui não é um objeto, é uma
    **instrução** que vira dezenas deles.
    """

    #: O serviço que já existe no plano. Sem ele, `nome` + `codigo` criam a
    #: sintética — desenhar a primeira linha de uma obra nova não pode exigir
    #: cadastrar a EAP antes.
    pai = serializers.IntegerField(required=False, allow_null=True)
    nome = serializers.CharField(required=False, allow_blank=True)
    codigo = serializers.CharField(required=False, allow_blank=True)

    #: **A ordem importa e é do planejador**: ele decide se a equipe sobe do
    #: térreo ou desce da cobertura, e reordenar por conta própria apagaria a
    #: decisão. Por isso lista, e não filtro por nível.
    locais = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False,
    )
    inicio = serializers.DateField()
    #: **A mensagem é a da casa, não a do DRF** — a lição do D152, aplicada na
    #: hora. O `services.gerar_ritmo` explica que serviço de duração zero é
    #: marco, e marco não tem ritmo; sem isto o `min_value` recusaria antes, com
    #: "Certifique-se de que este valor seja maior ou igual a 1", e a razão
    #: ficaria no código, para ninguém.
    duracao_por_local = serializers.IntegerField(min_value=1, error_messages={
        "min_value": (
            "A duração em cada local tem de ser de pelo menos um dia. Serviço "
            "de duração zero é marco, e marco não tem ritmo."
        ),
    })
    #: Dias entre o início de um local e o do seguinte — a **inclinação**. Nulo
    #: herda a duração, que é o fluxo contínuo: a equipe termina um pavimento e
    #: sobe. Menor que a duração são equipes se sobrepondo; maior é folga
    #: deliberada entre elas.
    ritmo_dias = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, error_messages={
            "min_value": (
                "O ritmo tem de ser de pelo menos um dia por local. Ritmo zero "
                "faria todos os locais começarem no mesmo dia — isso não é "
                "ritmo, é a obra inteira de uma vez."
            ),
        },
    )
    #: A régua do gerador de locais da PDCA.0: a mesma conta, sem escrever.
    simular = serializers.BooleanField(default=False)


class RestricaoSerializer(TenantScopedModelSerializer):
    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)
    atividade_codigo = serializers.CharField(source="atividade.codigo", read_only=True)
    atividade_nome = serializers.CharField(source="atividade.nome", read_only=True)
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    obra = serializers.IntegerField(
        source="atividade.cronograma.obra_id", read_only=True,
    )
    #: O seam do SCM **visível na tela** (régua de módulo): quando a restrição
    #: já virou compra, o cartão diz qual demanda está segurando a obra em vez
    #: de mandar a pessoa procurar no Suprimentos.
    demanda_scm_status = serializers.CharField(
        source="demanda_scm.status", read_only=True,
    )
    #: Quantos dias faltam (negativo = vencida). `None` quando não há prazo — e
    #: a tela mostra "sem prazo", nunca "vencida há 0 dias".
    dias_para_o_prazo = serializers.SerializerMethodField()
    #: **A trava acompanha a compra** (integração PDCA × Suprimentos × estoque):
    #: demanda → cotação → pedido → recebimento, e `sugerir_destravar` quando
    #: tudo o que foi pedido chegou. Destravar continua sendo da pessoa — o
    #: recebimento só sugere *(decisão do dono, 09/10/2026)*.
    compra = serializers.SerializerMethodField()

    class Meta:
        model = Restricao
        fields = [
            "restricao_id", "atividade", "atividade_codigo", "atividade_nome",
            "obra", "local", "local_rotulo", "tipo", "tipo_rotulo",
            "descricao", "responsavel", "prazo", "dias_para_o_prazo",
            "status", "status_rotulo", "demanda_scm", "demanda_scm_status",
            "criada_por", "criada_em", "removida_em", "removida_por",
            "nota_remocao", "reaberta_em", "reaberta_por", "vezes_reaberta",
            "compra",
        ]
        read_only_fields = [
            "restricao_id", "criada_em", "removida_em", "removida_por",
            "nota_remocao", "demanda_scm", "reaberta_em", "reaberta_por",
            "vezes_reaberta",
        ]

    def get_compra(self, obj):
        demanda = obj.demanda_scm
        if demanda is None:
            return None
        pedidos = [p for p in demanda.pedidos.all() if p.status != "cancelado"]
        cotacoes = sorted(demanda.cotacoes.all(), key=lambda c: c.cotacao_id)
        entregues = [p for p in pedidos if p.status == "recebido_total"]
        if entregues and len(entregues) == len(pedidos):
            etapa = "recebido"
        elif any(p.status == "recebido_parcial" for p in pedidos):
            etapa = "recebido_parcial"
        elif pedidos:
            etapa = "pedido"
        elif cotacoes:
            etapa = "cotacao"
        else:
            etapa = "demanda"
        return {
            "demanda": demanda.pk,
            "demanda_status": demanda.status,
            "cotacao": cotacoes[-1].cotacao_id if cotacoes else None,
            "cotacao_status": cotacoes[-1].status if cotacoes else None,
            "pedidos": [
                {"pedido": p.pk, "status": p.status, "status_rotulo": p.get_status_display(),
                 "entrega_prevista": p.data_entrega_prevista}
                for p in sorted(pedidos, key=lambda p: p.pk)
            ],
            "etapa": etapa,
            "sugerir_destravar": obj.status == Restricao.Status.ABERTA and etapa == "recebido",
        }

    def get_dias_para_o_prazo(self, obj):
        if not obj.prazo or obj.status != Restricao.Status.ABERTA:
            return None
        from django.utils import timezone as _tz
        return (obj.prazo - _tz.localdate()).days


class ItemProgramacaoSerializer(TenantScopedModelSerializer):
    atividade_codigo = serializers.CharField(source="atividade.codigo", read_only=True)
    atividade_nome = serializers.CharField(source="atividade.nome", read_only=True)
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    causa_codigo = serializers.CharField(source="causa.codigo", read_only=True)
    causa_nome = serializers.CharField(source="causa.nome", read_only=True)
    #: Quantas travas abertas pesam sobre a atividade deste cartão. A tela o usa
    #: para pintar o cartão como bloqueado **antes** de a pessoa tentar
    #: comprometer — recusar só no envio faria o time descobrir a trava depois
    #: de a reunião ter acabado.
    restricoes_abertas = serializers.SerializerMethodField()
    #: Quantos defeitos abertos pesam sobre a atividade deste cartão (PDCA.7).
    ncs_abertas = serializers.SerializerMethodField()
    #: **Quanto o campo apontou nesta semana para este serviço.** Não é o
    #: julgamento e não entra no PPC — é a **prova** ao lado dele. Quem julga
    #: deixa de julgar de memória, e a equipe que fez 12 dos 20 pontos
    #: prometidos vê os 12 registrados em vez de um "não saiu" seco.
    #:
    #: `null` quando o campo não apontou nada na semana, que é diferente de
    #: zero: pode ser que ninguém tenha apontado, não que nada tenha andado.
    percentual_apontado = serializers.SerializerMethodField()
    requisicao_sil_status = serializers.CharField(source="requisicao_sil.status", read_only=True, default=None)
    #: O julgamento por % (decisão do dono, 09/10/2026): o acumulado da
    #: atividade agora e a meta da semana — onde ela tinha de chegar. A tela
    #: abre o campo do concluído com o atual e diz se ele bate a meta.
    avanco_atual = serializers.SerializerMethodField()
    meta_da_semana = serializers.SerializerMethodField()

    class Meta:
        model = ItemProgramacao
        fields = [
            "item_programacao_id", "programacao", "atividade", "equipe",
            "atividade_codigo", "atividade_nome", "local", "local_rotulo",
            "responsavel", "percentual_previsto", "percentual_apontado",
            "cumprido", "causa", "causa_codigo", "causa_nome", "nota", "ordem",
            "percentual_concluido", "avanco_atual", "meta_da_semana",
            "restricoes_abertas", "ncs_abertas",
            #: O peso congelado e de onde ele saiu — é o que o PPC ponderado
            #: divide, e a tela mostra ao lado do cartão para o índice não ser
            #: um número sem procedência (ver `services.peso_do_compromisso`).
            "peso", "peso_origem",
            #: E o arrasto: de qual cartão da semana passada este veio, e há
            #: quantas semanas ele está de pé. Um serviço na quarta semana
            #: seguida é o que a reunião precisa ver antes do índice.
            "arrastado_de", "vezes_arrastado",
            #: O material que o cartão pediu ao almoxarifado, e em que pé está.
            "requisicao_sil", "requisicao_sil_status",
        ]
        read_only_fields = [
            "item_programacao_id", "requisicao_sil",
            #: **Congelados pelo servidor, não digitados.** O peso sai do
            #: planejamento (orçamento → peso informado → duração) no momento em
            #: que o cartão entra no quadro; aceitar o valor pelo corpo do POST
            #: deixaria a tela escolher quanto cada compromisso vale, que é o
            #: contrário de o número ter procedência.
            "peso", "peso_origem", "arrastado_de", "vezes_arrastado",
            #: Só o julgamento escreve — ver `services.julgar_itens`.
            "percentual_concluido",
        ]

    def get_restricoes_abertas(self, obj):
        #: Vem de `context` quando o pai já resolveu o agregado da página
        #: inteira; só cai na consulta por linha quando o serializer é usado
        #: sozinho. Sem isso, um quadro de 300 cartões faria 300 consultas.
        mapa = self.context.get("restricoes_por_atividade")
        if mapa is not None:
            return mapa.get(obj.atividade_id, 0)
        return obj.atividade.restricoes.filter(
            status=Restricao.Status.ABERTA
        ).count()

    def get_ncs_abertas(self, obj):
        #: **A PDCA.7 aparecendo no quadro da PDCA.5** — o que conversa no
        #: backend conversa na tela (régua de módulo §1.6). Um defeito aberto no
        #: serviço não impede o compromisso por si (só a restrição faz isso),
        #: mas quem assume a semana precisa saber que vai pegar a frente com
        #: retrabalho pendente. Mesmo agregado por página das travas acima.
        mapa = self.context.get("ncs_por_atividade")
        if mapa is not None:
            return mapa.get(obj.atividade_id, 0)
        return obj.atividade.nao_conformidades.filter(
            status__in=[
                NaoConformidade.Status.ABERTA,
                NaoConformidade.Status.EM_TRATAMENTO,
            ]
        ).count()

    def get_percentual_apontado(self, obj):
        #: Mesma régua do agregado acima: resolvido **uma vez por página** pelo
        #: viewset, e só cai na consulta por linha quando o serializer é usado
        #: sozinho. O quadro de 300 cartões não pode virar 300 consultas.
        mapa = self.context.get("apontado_por_item")
        if mapa is not None:
            valor = mapa.get(obj.pk)
        else:
            valor = services.avanco_apontado_dos_itens(obj.programacao).get(obj.pk)
        return str(valor) if valor is not None else None

    def _andamento(self, obj) -> dict | None:
        mapa = self.context.get("andamento_por_item")
        if mapa is None:
            mapa = services.andamento_dos_itens(obj.programacao)
        return mapa.get(obj.pk)

    def get_avanco_atual(self, obj):
        conta = self._andamento(obj)
        return services.str_decimais(conta["atual"]) if conta else None

    def get_meta_da_semana(self, obj):
        conta = self._andamento(obj)
        return services.str_decimais(conta["meta"]) if conta else None

    def validate(self, dados):
        #: A regra do LPS, dita na entrada: atividade travada não entra no
        #: quadro. O `services` a repete no `comprometer` porque a trava pode
        #: nascer entre montar e assumir.
        atividade = dados.get("atividade") or getattr(self.instance, "atividade", None)
        programacao = (
            dados.get("programacao")
            or getattr(self.instance, "programacao", None)
        )
        if programacao is not None and not programacao.esta_aberta_para_montagem:
            raise serializers.ValidationError(
                f"Esta programação está "
                f"{programacao.get_status_display().lower()}: compromisso novo "
                f"só entra enquanto o quadro é rascunho. Assumir depois que a "
                f"semana andou é escrever a aposta depois do resultado."
            )
        if atividade is not None and programacao is not None:
            try:
                services.validar_pode_comprometer(
                    atividade, tenant_id=programacao.tenant_id,
                )
                services.validar_teto_de_itens_da_programacao(
                    programacao,
                    acrescentando=0 if self.instance else 1,
                )
            except DjangoValidationError as erro:
                raise serializers.ValidationError(erro.messages)

            #: **O mesmo serviço não entra duas vezes no mesmo quadro.** A
            #: `UniqueConstraint` do modelo é a rede de baixo e devolve 409 com
            #: o nome da regra; aqui a recusa fala a língua de quem está na
            #: reunião. O `local` participa da chave porque a mesma atividade
            #: pode ser assumida na torre A e na torre B na mesma semana —
            #: `local=None` é um endereço como outro qualquer, e é o caso comum.
            #:
            #: Achado pelo `pdca5_programacao_test.py`: sem isto o cartão
            #: repetido chegava como "Já existe um registro com este valor", que
            #: não diz que o serviço já está no quadro.
            local = dados.get("local", getattr(self.instance, "local", None))
            irmaos = ItemProgramacao.objects.filter(
                programacao=programacao, atividade=atividade, local=local,
            )
            if self.instance is not None:
                irmaos = irmaos.exclude(pk=self.instance.pk)
            if irmaos.exists():
                onde = f" em «{local.nome}»" if local is not None else ""
                raise serializers.ValidationError(
                    f"«{atividade.nome}»{onde} já está no quadro desta semana. "
                    f"Dois cartões do mesmo serviço fariam o PPC contar a mesma "
                    f"falha duas vezes — para dividir a frente, puxe-a em locais "
                    f"diferentes."
                )

        #: **A equipe e o nome andam juntos.** Com a equipe, o `responsavel` é o
        #: nome dela (é o que o campo procura). Só com o nome — o arrasto entre
        #: colunas, a tela antiga, o comando de bancada —, a equipe de mesmo
        #: nome na obra é ligada sozinha; nome solto fica só como rótulo.
        if programacao is not None and ("equipe" in dados or "responsavel" in dados):
            equipe = dados.get("equipe")
            if equipe is not None:
                if equipe.obra_id != programacao.obra_id:
                    raise serializers.ValidationError({"equipe": "Esta equipe não é desta obra."})
                dados["responsavel"] = equipe.nome
            elif "responsavel" in dados:
                nome = (dados["responsavel"] or "").strip()
                dados["equipe"] = (EquipeObra.objects
                                   .filter(obra_id=programacao.obra_id, nome__iexact=nome)
                                   .first() if nome else None)
        return dados


class ProgramacaoSemanalSerializer(TenantScopedModelSerializer):
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    #: O PPC vem **resolvido pelo servidor**, e é a mesma decisão que a grade de
    #: medição tomou depois do D138: montar a conta no navegador fez a mesma
    #: medição mostrar números diferentes conforme a porta de entrada.
    ppc = serializers.SerializerMethodField()

    class Meta:
        model = ProgramacaoSemanal
        fields = [
            "programacao_id", "obra", "obra_nome", "semana_inicio",
            "semana_fim", "status", "status_rotulo", "nota",
            "criada_por", "criada_em", "comprometida_em", "comprometida_por",
            "encerrada_em", "encerrada_por", "ppc",
            "reaberta_em", "reaberta_por", "motivo_reabertura", "vezes_reaberta",
            #: A semana fechada antes de acabar se anuncia — na tela e na série.
            #: Um ponto apurado na terça não é comparável com um apurado no
            #: domingo, e a diferença tem de estar visível (ver `services.encerrar`).
            "encerrada_antes_do_fim", "motivo_encerramento_antecipado",
        ]
        read_only_fields = [
            "programacao_id", "semana_fim", "criada_em",
            "comprometida_em", "comprometida_por",
            "encerrada_em", "encerrada_por",
            "reaberta_em", "reaberta_por", "motivo_reabertura", "vezes_reaberta",
            "encerrada_antes_do_fim", "motivo_encerramento_antecipado",
        ]

    def get_ppc(self, obj):
        #: String, e não número: é o mesmo contrato da ação `encerrar/`, e o
        #: `types.ts` declara `ppc: string | null`. Os dois caminhos devolvem o
        #: mesmo PPC, então têm de devolvê-lo do mesmo jeito.
        return services.str_decimais(services.ppc_de(obj))


class JulgamentoSerializer(serializers.Serializer):
    """Uma linha do julgamento do fim da semana."""

    item = serializers.IntegerField()
    cumprido = serializers.BooleanField(allow_null=True, required=False)
    causa = serializers.IntegerField(required=False, allow_null=True)
    nota = serializers.CharField(required=False, allow_blank=True)
    #: O % concluído da atividade no fim da semana — quando vem, decide o
    #: `cumprido` e vira apontamento de avanço (`services.julgar_itens`).
    percentual_concluido = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True,
        min_value=0, max_value=100,
    )


class JulgarSerializer(serializers.Serializer):
    """O lote — é assim que a reunião percorre o quadro (ver `julgar_itens`)."""

    julgamentos = JulgamentoSerializer(many=True)


class EncerrarSerializer(serializers.Serializer):
    """O fim da semana.

    **O motivo é opcional aqui e obrigatório lá.** Encerrar a semana que já
    acabou não pede explicação nenhuma — é o gesto normal. Quem precisa de
    motivo é o encerramento **antecipado**, e quem cobra isso é o
    `services.encerrar`, que é quem sabe a data: repetir a regra aqui faria a
    tela pedir justificativa numa sexta-feira à noite sem razão.
    """

    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    #: Arrastar o que não saiu é o padrão (ver `services.arrastar_pendentes`).
    #: O `false` existe para a semana que encerra uma frente concluída, em que
    #: repetir os cartões falhados só sujaria o quadro seguinte.
    arrastar = serializers.BooleanField(required=False, default=True)


class RemoverRestricaoSerializer(serializers.Serializer):
    #: Obrigatória. Restrição que some sem explicação deixa a reunião seguinte
    #: sem saber se ela foi resolvida ou esquecida.
    #:
    #: **A mensagem é a da casa, não a do DRF.** O `services.remover_restricao`
    #: já explica o porquê — mas ele nunca chega a rodar por esta porta: o
    #: `trim_whitespace` do `CharField` transforma "   " em vazio e o campo
    #: recusa antes, com "Este campo não pode ser em branco". Quem digitou um
    #: espaço recebia o erro do framework em vez da razão. Achado pelo
    #: `pdca5_programacao_test.py`.
    nota = serializers.CharField(error_messages={
        "blank": (
            "Diga como a restrição foi removida. Sem isso, a reunião da semana "
            "que vem não sabe se ela foi resolvida ou apenas esquecida."
        ),
        "required": (
            "Diga como a restrição foi removida. Sem isso, a reunião da semana "
            "que vem não sabe se ela foi resolvida ou apenas esquecida."
        ),
    })


class GerarDemandaSerializer(serializers.Serializer):
    quantidade = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True,
    )
    unidade = serializers.CharField(required=False, allow_blank=True)


class ReabrirSerializer(serializers.Serializer):
    #: Obrigatório, com a mensagem da casa (a lição do D152): o `CharField` do
    #: DRF recusaria vazio com o texto dele, e a razão ficaria no `services`,
    #: para ninguém.
    motivo = serializers.CharField(error_messages={
        "blank": (
            "Diga por que a semana está sendo reaberta. O PPC dela já foi lido "
            "por alguém — mudar o número sem deixar a razão escrita contraria "
            "em silêncio a reunião que olhou para ele."
        ),
        "required": (
            "Diga por que a semana está sendo reaberta. O PPC dela já foi lido "
            "por alguém — mudar o número sem deixar a razão escrita contraria "
            "em silêncio a reunião que olhou para ele."
        ),
    })


class AbrirProgramacaoSerializer(serializers.Serializer):
    obra = serializers.IntegerField()
    #: Qualquer dia da semana serve — o servidor ancora na segunda-feira, que é
    #: a convenção do método. Deixar o cliente calcular a segunda produziria uma
    #: semana diferente por fuso horário de navegador.
    semana = serializers.DateField()


# ---------------------------------------------------------------------------
# PDCA.7 — a máquina de verificação
# ---------------------------------------------------------------------------


class ItemModeloVerificacaoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = ItemModeloVerificacao
        fields = [
            "item_modelo_id", "modelo", "ordem", "texto", "criterio",
            "obrigatorio", "exige_foto",
        ]
        read_only_fields = ["item_modelo_id"]


class ModeloVerificacaoSerializer(TenantScopedModelSerializer):
    """A ficha em branco, com os dois números que decidem se ela se apaga."""

    dominio_rotulo = serializers.CharField(
        source="get_dominio_display", read_only=True,
    )
    itens_count = serializers.IntegerField(source="itens.count", read_only=True)
    #: Quantas fichas já foram aplicadas a partir dele. É o que a tela usa para
    #: mostrar "já usado 43 vezes" ao lado do botão de apagar — e o que o
    #: `perform_destroy` cobra.
    aplicacoes = serializers.IntegerField(
        source="verificacoes.count", read_only=True,
    )
    #: Os itens viajam **junto** na leitura de detalhe. A ficha de 150 perguntas
    #: é montada numa tela só, e uma segunda chamada por item faria o editor
    #: piscar a cada linha.
    itens = ItemModeloVerificacaoSerializer(many=True, read_only=True)

    class Meta:
        model = ModeloVerificacao
        fields = [
            "modelo_id", "codigo", "nome", "dominio", "dominio_rotulo",
            "descricao", "ativo", "criado_por", "criado_em",
            "itens_count", "aplicacoes", "itens",
        ]
        read_only_fields = ["modelo_id", "criado_por", "criado_em"]


class ModeloResumoSerializer(ModeloVerificacaoSerializer):
    """O mesmo modelo **sem os itens** — a lista da biblioteca.

    Existe pela lição do D136: a listagem que traz as linhas filhas de todos os
    documentos faz ~200 consultas para desenhar uma tabela que não as mostra.
    """

    class Meta(ModeloVerificacaoSerializer.Meta):
        fields = [
            c for c in ModeloVerificacaoSerializer.Meta.fields if c != "itens"
        ]


class ItemVerificacaoSerializer(UploadValidationMixin, TenantScopedModelSerializer):
    """Uma resposta da ficha. `texto` e `criterio` são **congelados** e por isso
    somente leitura: editá-los aqui mudaria a pergunta depois de respondida."""

    resultado_rotulo = serializers.CharField(
        source="get_resultado_display", read_only=True,
    )
    #: **A gravidade deste defeito** — respondida no item, por quem o viu, e não
    #: uma vez para a ficha inteira (§11.15).
    gravidade_rotulo = serializers.CharField(
        source="get_gravidade_display", read_only=True,
    )
    #: A NC que este item gerou, quando gerou. É o que fecha o laço na tela: o
    #: item reprovado mostra para onde o defeito foi, em vez de o técnico ter de
    #: procurar na lista de NCs.
    nc = serializers.SerializerMethodField()

    class Meta:
        model = ItemVerificacao
        fields = [
            "item_verificacao_id", "verificacao", "item_modelo", "ordem",
            "texto", "criterio", "obrigatorio", "exige_foto",
            "resultado", "resultado_rotulo", "observacao",
            "gravidade", "gravidade_rotulo", "foto",
            "respondido_em", "respondido_por", "nc",
        ]
        read_only_fields = [
            "item_verificacao_id", "verificacao", "item_modelo", "texto",
            "criterio", "obrigatorio", "exige_foto", "respondido_em",
            "respondido_por",
        ]

    def get_nc(self, obj):
        nc = obj.nao_conformidades.first()
        return nc.pk if nc else None

    def to_representation(self, instance):
        """`foto` sai pela porta única, nunca por `/media/` — a régua do D120."""
        dados = super().to_representation(instance)
        dados["foto"] = (
            url_do_arquivo(
                RECURSO_VERIFICACAO, ESPECIE_ITEM, instance.item_verificacao_id,
            )
            if instance.foto else None
        )
        return dados


class VerificacaoSerializer(TenantScopedModelSerializer):
    """A ficha aplicada, com o resultado **derivado** ao lado (§4.9)."""

    modelo_codigo = serializers.CharField(source="modelo.codigo", read_only=True)
    modelo_nome = serializers.CharField(source="modelo.nome", read_only=True)
    dominio = serializers.CharField(source="modelo.dominio", read_only=True)
    dominio_rotulo = serializers.CharField(
        source="modelo.get_dominio_display", read_only=True,
    )
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    atividade_codigo = serializers.CharField(
        source="atividade.codigo", read_only=True,
    )
    atividade_nome = serializers.CharField(
        source="atividade.nome", read_only=True,
    )
    status_rotulo = serializers.CharField(
        source="get_status_display", read_only=True,
    )
    resultado = serializers.SerializerMethodField()

    class Meta:
        model = Verificacao
        fields = [
            "verificacao_id", "modelo", "modelo_codigo", "modelo_nome",
            "dominio", "dominio_rotulo", "obra", "obra_nome",
            "local", "local_rotulo", "atividade", "atividade_codigo",
            "atividade_nome", "inspetor", "data", "status", "status_rotulo",
            "nota", "criada_por", "criada_em", "concluida_em", "concluida_por",
            "resultado",
        ]
        read_only_fields = [
            "verificacao_id", "modelo", "obra", "criada_por", "criada_em",
            "concluida_em", "concluida_por",
        ]

    def get_resultado(self, obj):
        #: Vem de `context` quando o pai já resolveu a página inteira; só cai na
        #: consulta por linha quando o serializer é usado sozinho. Sem isso, uma
        #: lista de 50 fichas faria 50 agregações — o D136 do outro lado.
        mapa = self.context.get("resultado_por_verificacao")
        if mapa is not None:
            return mapa.get(obj.pk)
        return services.str_decimais(services.resultado_da_verificacao(obj))


class PlanoAcaoSerializer(TenantScopedModelSerializer):
    """O 5W2H. `o_que` é o único obrigatório — ver a docstring do model."""

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    status_rotulo = serializers.CharField(
        source="get_status_display", read_only=True,
    )
    #: Negativo = vencido. `None` quando não há prazo — e a tela diz "sem
    #: prazo", nunca "vencido há 0 dias". Mesma régua da restrição da PDCA.5.
    dias_para_o_prazo = serializers.SerializerMethodField()

    class Meta:
        model = PlanoAcao
        fields = [
            "plano_id", "nao_conformidade", "tipo", "tipo_rotulo",
            "o_que", "por_que", "onde", "quando", "quem", "como", "quanto",
            "status", "status_rotulo", "dias_para_o_prazo",
            "concluida_em", "concluida_por", "criada_por", "criada_em",
        ]
        read_only_fields = [
            "plano_id", "concluida_em", "concluida_por", "criada_por",
            "criada_em",
        ]

    def get_dias_para_o_prazo(self, obj):
        if not obj.quando or obj.status in (
            PlanoAcao.Status.CONCLUIDA, PlanoAcao.Status.CANCELADA,
        ):
            return None
        from django.utils import timezone as _tz
        return (obj.quando - _tz.localdate()).days


class VerificacaoEficaciaSerializer(UploadValidationMixin,
                                    TenantScopedModelSerializer):
    class Meta:
        model = VerificacaoEficacia
        fields = [
            "eficacia_id", "nao_conformidade", "data", "eficaz", "evidencia",
            "foto", "verificada_por", "verificada_em",
        ]
        read_only_fields = [
            "eficacia_id", "verificada_por", "verificada_em",
        ]

    def to_representation(self, instance):
        dados = super().to_representation(instance)
        dados["foto"] = (
            url_do_arquivo(RECURSO_NC, ESPECIE_EFICACIA, instance.eficacia_id)
            if instance.foto else None
        )
        return dados


class NaoConformidadeSerializer(UploadValidationMixin,
                                TenantScopedModelSerializer):
    """O defeito, com **o que falta nele** resolvido pelo servidor.

    `estado` traz a regra do encerramento já decidida aqui, e não no navegador:
    a mesma conta feita nos dois lugares produz dois números para a mesma
    pergunta, que foi o que o D138 ensinou na grade de medição.
    """

    gravidade_rotulo = serializers.CharField(
        source="get_gravidade_display", read_only=True,
    )
    status_rotulo = serializers.CharField(
        source="get_status_display", read_only=True,
    )
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    atividade_codigo = serializers.CharField(
        source="atividade.codigo", read_only=True,
    )
    atividade_nome = serializers.CharField(
        source="atividade.nome", read_only=True,
    )
    #: Os dois seams, **visíveis** (régua de módulo): de qual ficha o defeito
    #: veio, e se ele já parou o serviço no quadro da semana.
    verificacao = serializers.IntegerField(
        source="item_verificacao.verificacao_id", read_only=True,
    )
    restricao_status = serializers.CharField(
        source="restricao.status", read_only=True,
    )
    marcacao_guid = serializers.CharField(
        source="marcacao_prancheta.guid", read_only=True,
    )
    estado = serializers.SerializerMethodField()
    acoes = PlanoAcaoSerializer(many=True, read_only=True)
    eficacias = VerificacaoEficaciaSerializer(many=True, read_only=True)

    class Meta:
        model = NaoConformidade
        fields = [
            "nc_id", "obra", "obra_nome", "local", "local_rotulo",
            "atividade", "atividade_codigo", "atividade_nome",
            "item_verificacao", "verificacao",
            "gravidade", "gravidade_rotulo", "descricao", "foto",
            "marcacao_prancheta", "marcacao_guid",
            "restricao", "restricao_status",
            "status", "status_rotulo",
            "aberta_por", "aberta_em", "encerrada_em", "encerrada_por",
            "nota_encerramento", "estado", "acoes", "eficacias",
        ]
        read_only_fields = [
            "nc_id", "item_verificacao", "restricao", "status", "aberta_por",
            "aberta_em", "encerrada_em", "encerrada_por", "nota_encerramento",
        ]

    def get_estado(self, obj):
        return services.str_decimais(services.estado_da_nc(obj))

    def to_representation(self, instance):
        dados = super().to_representation(instance)
        dados["foto"] = (
            url_do_arquivo(RECURSO_NC, ESPECIE_NC, instance.nc_id)
            if instance.foto else None
        )
        return dados


class NcResumoSerializer(NaoConformidadeSerializer):
    """A NC **sem as linhas filhas** — a listagem do painel (D136)."""

    class Meta(NaoConformidadeSerializer.Meta):
        fields = [
            c for c in NaoConformidadeSerializer.Meta.fields
            if c not in ("acoes", "eficacias")
        ]


# --- As entradas dos verbos --------------------------------------------------


class AplicarModeloVerificacaoSerializer(serializers.Serializer):
    """Abrir a ficha. `modelo`, `obra` e `data` decidem; o resto endereça."""

    modelo = serializers.IntegerField()
    obra = serializers.IntegerField()
    data = serializers.DateField()
    local = serializers.IntegerField(required=False, allow_null=True)
    atividade = serializers.IntegerField(required=False, allow_null=True)
    inspetor = serializers.CharField(
        required=False, allow_blank=True, max_length=150,
    )


class DuplicarModeloSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=30)
    nome = serializers.CharField(max_length=150, required=False, allow_blank=True)


class RespostaDeItemSerializer(serializers.Serializer):
    item_verificacao = serializers.IntegerField()
    resultado = serializers.ChoiceField(choices=ResultadoItem.choices)
    observacao = serializers.CharField(
        required=False, allow_blank=True, default="",
    )
    #: Obrigatória quando o item reprova, e recusada nos outros resultados. A
    #: exigência mora no `services` (para a mensagem nomear o item) e no banco.
    gravidade = serializers.ChoiceField(
        choices=GravidadeNC.choices, required=False, allow_null=True,
    )


class ResponderSerializer(serializers.Serializer):
    """O lote de respostas. Ver `services.responder_itens`."""

    respostas = RespostaDeItemSerializer(many=True, allow_empty=False)


#: **Sem corpo, e a ausência é a correção.** Este serializer recebia uma
#: `gravidade` e ela era carimbada em todas as NCs abertas de uma vez. A
#: gravidade é do defeito, foi respondida no item por quem o viu, e este verbo
#: só a lê (§11.15). Fica declarado em vez de sumir para que a próxima pessoa
#: que abrir este arquivo não reintroduza o parâmetro achando que faltou.


class GerarRestricaoSerializer(serializers.Serializer):
    prazo = serializers.DateField(required=False, allow_null=True)
    responsavel = serializers.CharField(
        required=False, allow_blank=True, max_length=150, default="",
    )


class RegistrarEficaciaSerializer(serializers.Serializer):
    """A evidência é obrigatória — um `True` sem história não é verificação."""

    data = serializers.DateField()
    eficaz = serializers.BooleanField()
    evidencia = serializers.CharField(allow_blank=False)

    def validate_evidencia(self, valor):
        if not (valor or "").strip():
            raise serializers.ValidationError(
                "Diga o que você olhou para concluir isso. Verificação de "
                "eficácia sem evidência é um carimbo."
            )
        return valor


class EncerrarNcSerializer(serializers.Serializer):
    nota = serializers.CharField(
        required=False, allow_blank=True, default="",
    )


class CancelarNcSerializer(serializers.Serializer):
    """Cancelar exige motivo, e a razão é a mesma da `nota_remocao` da
    restrição: uma NC que some sem explicação deixa a auditoria sem saber se ela
    não era defeito ou se alguém a varreu para debaixo do tapete."""

    motivo = serializers.CharField(allow_blank=False)

    def validate_motivo(self, valor):
        if not (valor or "").strip():
            raise serializers.ValidationError(
                "Diga por que esta NC não era uma não-conformidade."
            )
        return valor


# ---------------------------------------------------------------------------
# PDCA.8 — SSMA
# ---------------------------------------------------------------------------


class ParticipanteDDSSerializer(TenantScopedModelSerializer):
    """Uma linha da lista de presença."""

    funcionario_nome = serializers.CharField(
        source="funcionario.nome_completo", read_only=True,
    )

    class Meta:
        model = ParticipanteDDS
        fields = [
            "participante_id", "dds", "funcionario", "funcionario_nome",
            "nome", "presente", "assinou",
        ]
        read_only_fields = ["participante_id", "dds"]


class DialogoSegurancaSerializer(TenantScopedModelSerializer):
    """O DDS, com a lista embutida e o seam do diário **visível**."""

    status_rotulo = serializers.CharField(
        source="get_status_display", read_only=True,
    )
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    responsavel_label = serializers.SerializerMethodField()
    participantes = ParticipanteDDSSerializer(many=True, read_only=True)
    presentes = serializers.SerializerMethodField()

    class Meta:
        model = DialogoSeguranca
        fields = [
            "dds_id", "obra", "obra_nome", "local", "local_rotulo", "atividade",
            "data", "tema", "assunto", "duracao_min",
            "responsavel", "responsavel_nome", "responsavel_label",
            "status", "status_rotulo", "encerrado_em", "encerrado_por",
            "diario", "registrado_por", "criado_em",
            "participantes", "presentes",
        ]
        read_only_fields = [
            "dds_id", "status", "encerrado_em", "encerrado_por", "diario",
            "registrado_por", "criado_em",
        ]

    def get_responsavel_label(self, obj) -> str:
        if obj.responsavel_id:
            return getattr(obj.responsavel, "nome_completo", "") or ""
        return obj.responsavel_nome

    def get_presentes(self, obj) -> int:
        return obj.participantes.filter(presente=True).count()


class AnexoOcorrenciaSerializer(UploadValidationMixin,
                                TenantScopedModelSerializer):
    """O arquivo — **e a URL sai pela porta da espécie certa**.

    O atestado é servido por `pdca.ocorrencia_atestado`, que exige o verbo
    clínico; o resto, por `pdca.ocorrencia_anexo`. Montar as duas com a mesma
    URL entregaria o atestado a quem tem só a leitura.
    """

    especie_rotulo = serializers.CharField(
        source="get_especie_display", read_only=True,
    )

    class Meta:
        model = AnexoOcorrencia
        fields = [
            "anexo_id", "ocorrencia", "arquivo", "especie", "especie_rotulo",
            "descricao", "enviado_por", "enviado_em",
        ]
        read_only_fields = ["anexo_id", "enviado_por", "enviado_em"]

    def to_representation(self, instance):
        dados = super().to_representation(instance)
        if not instance.arquivo:
            dados["arquivo"] = None
            return dados
        clinico = instance.especie == AnexoOcorrencia.Especie.ATESTADO
        dados["arquivo"] = url_do_arquivo(
            RECURSO_SSMA_CLINICO if clinico else RECURSO_SSMA,
            ESPECIE_ATESTADO if clinico else ESPECIE_ANEXO,
            instance.anexo_id,
        )
        return dados


class OcorrenciaSerializer(FieldMaskingSerializerMixin,
                           TenantScopedModelSerializer):
    """A ocorrência — **e o bloco clínico atrás de um verbo próprio**.

    Esta é a primeira PII do grupo `pdca`. Natureza da lesão, CID-10, internação
    e dias de atestado só saem para quem tem `pdca.ocorrencia.dado_medico`; para
    todo o resto eles vêm mascarados. A régua é a do `rh.dado_medico`, e a razão
    é a mesma: para classificar o acidente ninguém precisa do diagnóstico.

    `prazo_cat` vem **decidido pelo servidor**, e não pela tela — a mesma conta
    feita nos dois lugares produz dois números para a mesma pergunta, que foi o
    que o D138 ensinou na grade de medição. Aqui o número tem prazo em lei.
    """

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    classificacao_rotulo = serializers.CharField(
        source="get_classificacao_display", read_only=True,
    )
    status_rotulo = serializers.CharField(
        source="get_status_display", read_only=True,
    )
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    atividade_codigo = serializers.CharField(
        source="atividade.codigo", read_only=True,
    )
    acidentado_label = serializers.SerializerMethodField()
    anexos = AnexoOcorrenciaSerializer(many=True, read_only=True)
    #: Os dois seams, **visíveis** (régua de módulo): se o fato já parou o
    #: serviço, e se ele já entrou na máquina de tratamento.
    restricao_status = serializers.CharField(
        source="restricao.status", read_only=True,
    )
    nc_status = serializers.CharField(
        source="nao_conformidade.status", read_only=True,
    )
    exige_cat = serializers.BooleanField(read_only=True)
    prazo_cat = serializers.SerializerMethodField()

    class Meta:
        model = Ocorrencia
        fields = [
            "ocorrencia_id", "obra", "obra_nome", "local", "local_rotulo",
            "atividade", "atividade_codigo",
            "ocorrido_em", "tipo", "tipo_rotulo", "descricao",
            "agente_causador", "situacao_geradora", "houve_registro_policial",
            "horas_trabalhadas_antes", "ultimo_dia_trabalhado",
            "acidentado", "acidentado_nome", "acidentado_label",
            "parte_do_corpo", "lateralidade",
            "natureza_lesao", "cid10", "houve_internacao", "atestado_dias",
            "classificacao", "classificacao_rotulo", "dias_perdidos",
            "dias_debitados", "classificada_em", "classificada_por",
            "cat_tipo", "cat_emitida_em", "cat_protocolo", "cat_registrada_por",
            "restricao", "restricao_status", "nao_conformidade", "nc_status",
            "status", "status_rotulo", "registrada_por", "registrada_em",
            "encerrada_em", "encerrada_por", "nota_encerramento",
            "anexos", "exige_cat", "prazo_cat",
        ]
        read_only_fields = [
            "ocorrencia_id", "classificacao", "dias_perdidos", "dias_debitados",
            "classificada_em", "classificada_por",
            "cat_tipo", "cat_emitida_em", "cat_protocolo", "cat_registrada_por",
            "restricao", "nao_conformidade", "status", "registrada_por",
            "registrada_em", "encerrada_em", "encerrada_por",
            "nota_encerramento",
        ]

    #: O bloco do atestado médico, na régua do `DadoMedicoFuncionarioSerializer`.
    sensitive_fields = {
        "natureza_lesao": "pdca.ocorrencia.dado_medico",
        "cid10": "pdca.ocorrencia.dado_medico",
        "atestado_dias": "pdca.ocorrencia.dado_medico",
    }

    def get_acidentado_label(self, obj) -> str:
        if obj.acidentado_id:
            return getattr(obj.acidentado, "nome_completo", "") or ""
        return obj.acidentado_nome

    def get_prazo_cat(self, obj) -> dict:
        return services.prazo_da_cat(obj)


class OcorrenciaResumoSerializer(serializers.ModelSerializer):
    """A linha da lista — **sem nada do bloco clínico**.

    A listagem não passa pelo mascaramento campo a campo porque ela
    simplesmente não traz os campos: a fila de SSMA e a grade da obra não têm
    por que carregar CID de ninguém, e o jeito mais seguro de não vazar um campo
    é não o serializar.
    """

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    classificacao_rotulo = serializers.CharField(
        source="get_classificacao_display", read_only=True,
    )
    local_rotulo = serializers.CharField(source="local.nome", read_only=True)
    exige_cat = serializers.BooleanField(read_only=True)

    class Meta:
        model = Ocorrencia
        fields = [
            "ocorrencia_id", "obra", "local", "local_rotulo", "atividade",
            "ocorrido_em", "tipo", "tipo_rotulo", "descricao",
            "classificacao", "classificacao_rotulo", "status",
            "cat_emitida_em", "restricao", "nao_conformidade", "exige_cat",
        ]


class RegistrarPresencaSerializer(serializers.Serializer):
    """A lista chega em lote — a tela acumula os nomes e grava de uma vez."""

    participantes = serializers.ListField(
        child=serializers.DictField(), allow_empty=False,
    )


class EncerrarDdsSerializer(serializers.Serializer):
    publicar_no_diario = serializers.BooleanField(default=True)


class ClassificarOcorrenciaSerializer(serializers.Serializer):
    classificacao = serializers.ChoiceField(
        choices=ClassificacaoOcorrencia.choices,
    )
    dias_perdidos = serializers.IntegerField(
        required=False, allow_null=True, min_value=0,
    )
    dias_debitados = serializers.IntegerField(
        required=False, allow_null=True, min_value=0,
    )


class RegistrarCatSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TipoCAT.choices)
    emitida_em = serializers.DateField()
    protocolo = serializers.CharField(required=False, allow_blank=True)


class InterditarFrenteSerializer(serializers.Serializer):
    prazo = serializers.DateField(required=False, allow_null=True)


class EncerrarOcorrenciaSerializer(serializers.Serializer):
    nota = serializers.CharField(required=False, allow_blank=True)


class MaterialDaAtividadeSerializer(TenantScopedModelSerializer):
    """O material informado na atividade (obra sem orçamento ou serviço fora dele)."""

    item_codigo = serializers.CharField(source="item.codigo_interno", read_only=True, default=None)

    class Meta:
        model = MaterialDaAtividade
        fields = [
            "material_id", "atividade", "item", "item_codigo", "descricao", "unidade",
            "categoria", "quantidade", "custo_unitario",
        ]
        read_only_fields = ["material_id"]
        extra_kwargs = {
            "descricao": {"required": False, "allow_blank": True},
            "unidade": {"required": False, "allow_blank": True},
        }

    def validate(self, dados):
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        atividade = dados.get("atividade") or getattr(self.instance, "atividade", None)
        item = dados.get("item")
        for objeto in (atividade, item):
            if objeto is not None and tenant_id is not None and objeto.tenant_id != tenant_id:
                raise serializers.ValidationError("Atividade ou item de outra empresa.")
        if atividade is not None and atividade.filhos.exists():
            raise serializers.ValidationError({
                "atividade": "O material vai na atividade que executa, não na etapa que a agrupa.",
            })
        quantidade = dados.get("quantidade", getattr(self.instance, "quantidade", None))
        if quantidade is not None and quantidade <= 0:
            raise serializers.ValidationError({"quantidade": "A quantidade precisa ser maior que zero."})
        # Com item do catálogo, descrição e unidade vêm dele quando não digitadas.
        if item is not None:
            if not (dados.get("descricao") or "").strip():
                dados["descricao"] = item.descricao
            if not (dados.get("unidade") or "").strip():
                dados["unidade"] = item.unidade
        if self.instance is None:
            if not (dados.get("descricao") or "").strip():
                raise serializers.ValidationError({"descricao": "Diga qual é o material (ou escolha do catálogo)."})
            if not (dados.get("unidade") or "").strip():
                raise serializers.ValidationError({"unidade": "Informe a unidade."})
        return dados
