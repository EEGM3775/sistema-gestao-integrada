# backend/modulopdca/views.py
"""API do PDCA — `/api/pdca/`.

Todo endpoint desta fatia passa por **duas camadas**, na ordem da
docs/acesso-e-permissoes.md: `RequireModule("pdca")` (o tenant assina o módulo?)
e `RequirePermission` (esta pessoa pode isto?). Nada aqui é fundação sem
entitlement — diferente do `Local` do Maps, a hierarquia construtiva só faz
sentido para quem planeja obra, e planejar obra é o produto.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import (
    filters, mixins, permissions, status, views, viewsets,
)
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from nucleo.busca import BuscaSemAcento
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.quotas import checar_quota
from nucleo.tenancy import TenantScopedViewSetMixin
from payment.planos import (
    PDCA_PROFUNDIDADE_MAXIMA_WBS,
    PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
    PDCA_TETO_LINHAS_POR_LOTE,
)

from . import services
from .models import (
    ApontamentoAvanco, Atividade, CalendarioTrabalho, Cronograma,
    ExcecaoCalendario, LocalObra, Precedencia,
)
from .pagination import PdcaPageNumberPagination
from .serializers import (
    ApontamentoAvancoSerializer,
    ApontamentoEmLoteSerializer,
    AplicarModeloSerializer,
    AtividadeSerializer,
    CalendarioTrabalhoSerializer,
    CronogramaSerializer,
    ExcecaoCalendarioSerializer,
    GeracaoEmLoteSerializer,
    LocalObraSerializer,
    LoteSerializer,
    EstornoSerializer,
    MarcarModeloSerializer,
    PrecedenciaSerializer,
    ReplanejarSerializer,
)


class PdcaStatusView(views.APIView):
    """Status do módulo. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "pdca"

    def get(self, request):
        return Response({
            "modulo": "pdca",
            "status": "ativo",
            # A tela precisa saber o que existe para não oferecer o que ainda não
            # foi construído — dado honesto vale para a própria capacidade.
            "fatia": "PDCA.2",
            "recursos": {
                "locais": True,
                "calendario": True,
                "cronograma": True,
                "modelo": True,
                "avanco": True,
                "medicao": False,
            },
            # Os tetos que a TELA precisa respeitar antes de mandar a requisição.
            # Só estes: quem decide o número continua sendo o dono, em
            # `payment/planos.py`, e o cliente lê o que vale hoje em vez de
            # carregar uma cópia que envelhece no bundle. Sem isto, colar 900
            # linhas viraria um 400 no fim de uma espera — em vez de dois blocos
            # com barra de progresso.
            "tetos": {
                "linhas_por_lote": PDCA_TETO_LINHAS_POR_LOTE,
                "atividades_por_cronograma": PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
                "profundidade_wbs": PDCA_PROFUNDIDADE_MAXIMA_WBS,
                "apontamentos_por_lote": PDCA_TETO_APONTAMENTOS_POR_LOTE,
            },
        })


class BasePdcaViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]


class LocalObraViewSet(BasePdcaViewSet):
    """A árvore de locais da obra."""

    queryset = LocalObra.objects.select_related(
        "obra", "pai", "unidade", "maps_local"
    ).all()
    serializer_class = LocalObraSerializer
    required_resource = "pdca.local"
    filterset_fields = ["obra", "pai", "nivel", "ativo", "unidade"]
    search_fields = ["codigo", "nome"]
    ordering_fields = ["profundidade", "ordem", "codigo", "nome"]

    def get_queryset(self):
        qs = super().get_queryset()
        # `?raiz=1` devolve só o topo da árvore — é o primeiro fôlego da tela,
        # que abre a obra mostrando as torres e busca os galhos sob demanda.
        if self.request.query_params.get("raiz") in ("1", "true"):
            qs = qs.filter(pai__isnull=True)
        return qs

    def perform_create(self, serializer):
        pai = serializer.validated_data.get("pai")
        try:
            services.validar_profundidade(pai)
        except DjangoValidationError as erro:
            raise ValidationError({"pai": erro.messages})
        super().perform_create(serializer)
        serializer.instance.profundidade = services.profundidade_de(pai)
        serializer.instance.save(update_fields=["profundidade"])

    def perform_update(self, serializer):
        pai = serializer.validated_data.get("pai", serializer.instance.pai)
        try:
            services.validar_profundidade(pai)
        except DjangoValidationError as erro:
            raise ValidationError({"pai": erro.messages})
        super().perform_update(serializer)
        instancia = serializer.instance
        nova = services.profundidade_de(pai)
        if instancia.profundidade != nova:
            # Mudar de pai move o galho inteiro. Sem reescrever a profundidade
            # dos descendentes, a ordenação da árvore passaria a mentir para
            # todos eles — e o teto deixaria de ser conferido no lugar certo.
            instancia.profundidade = nova
            instancia.save(update_fields=["profundidade"])
            self._reprofundar(instancia)

    def _reprofundar(self, no: LocalObra) -> None:
        filhos = list(no.filhos.all())
        for filho in filhos:
            filho.profundidade = no.profundidade + 1
            filho.save(update_fields=["profundidade"])
            self._reprofundar(filho)

    @action(detail=False, methods=["post"], url_path="gerar-em-lote")
    def gerar_em_lote(self, request):
        """Cria a árvore a partir de uma receita — o recurso que faz a hierarquia
        ser usada em vez de ignorada (planta §4.1).

        `simular: true` devolve a mesma conta sem gravar nada. A tela pede a
        simulação primeiro; quem chama a API direto decide.
        """
        entrada = GeracaoEmLoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        obras = self._scope(self._obras())
        obra = obras.filter(pk=dados["obra"]).first()
        if obra is None:
            raise ValidationError({"obra": "Obra não encontrada nesta empresa."})

        pai = None
        if dados.get("pai"):
            pai = self.get_queryset().filter(pk=dados["pai"]).first()
            if pai is None:
                raise ValidationError({"pai": "Local pai não encontrado nesta empresa."})
            if pai.obra_id != obra.pk:
                raise ValidationError({"pai": "O local pai pertence a outra obra."})

        try:
            relatorio = services.gerar_em_lote(
                obra=obra,
                tenant_id=getattr(request.user, "tenant_id", None),
                receita=dados["receita"],
                pai=pai,
                simular=dados["simular"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"receita": erro.messages})
        return Response(relatorio, status=status.HTTP_200_OK)

    def _obras(self):
        from obras.models import Obra

        return Obra.objects.all()


class CalendarioTrabalhoViewSet(BasePdcaViewSet):
    """Jornada e dias trabalhados."""

    queryset = CalendarioTrabalho.objects.select_related("obra").prefetch_related("excecoes")
    serializer_class = CalendarioTrabalhoSerializer
    required_resource = "pdca.calendario"
    filterset_fields = ["obra", "padrao", "ativo"]
    search_fields = ["nome"]
    ordering_fields = ["nome"]

    def get_queryset(self):
        """`?para_obra=<id>` — os expedientes que **servem** a esta obra.

        Não é sinônimo de `?obra=<id>`, e a diferença é o defeito que esta rota
        já teve ([D118](../../docs/historico-correcoes.md)): o filtro exato casa
        `obra_id = 7` e portanto **exclui os calendários da empresa**, que têm
        `obra` nulo justamente por valerem para todas as obras. O select de quem
        cria um plano ficava vazio numa empresa que tinha expediente cadastrado.

        A regra aqui é a mesma de `services.calendario_da_obra`, que é quem
        resolve o calendário no cálculo: **o da obra, mais os da empresa** — e
        nunca o de uma obra vizinha, que o serializer recusaria depois. A ordem
        põe o específico antes do geral, que é a ordem em que eles vencem.
        """
        qs = super().get_queryset()
        para_obra = self.request.query_params.get("para_obra")
        if para_obra:
            qs = (qs.filter(Q(obra_id=para_obra) | Q(obra__isnull=True))
                    .order_by(F("obra_id").desc(nulls_last=True), "-padrao", "nome"))
        return qs

    @action(detail=True, methods=["get"], url_path="dias-uteis")
    def dias_uteis(self, request, pk=None):
        """`?inicio=AAAA-MM-DD&fim=AAAA-MM-DD` → quantos dias se trabalha, e
        **quais feriados** entraram na conta.

        Devolver os feriados junto não é enfeite: é a diferença entre o
        planejador aceitar o número e desconfiar dele. Quando o cronograma diz
        que a atividade termina três dias depois do esperado, a pergunta é
        sempre "por quê" — e a resposta é esta lista.
        """
        from datetime import date as tipo_data

        calendario = self.get_object()
        try:
            inicio = tipo_data.fromisoformat(request.query_params["inicio"])
            fim = tipo_data.fromisoformat(request.query_params["fim"])
        except (KeyError, ValueError):
            raise ValidationError(
                {"inicio": "Informe `inicio` e `fim` no formato AAAA-MM-DD."}
            )
        if fim < inicio:
            raise ValidationError({"fim": "A data final é anterior à inicial."})

        feriados = services.feriados_do_periodo(calendario, inicio, fim)
        return Response({
            "calendario": calendario.calendario_id,
            "inicio": inicio, "fim": fim,
            "dias_uteis": services.dias_uteis(calendario, inicio, fim),
            "dias_corridos": (fim - inicio).days + 1,
            "feriados": [
                {"data": data, "nome": nome} for data, nome in sorted(feriados.items())
            ],
            # A tabela de feriados é global e nasce vazia (quem a enche é o
            # comando `sincronizar_feriados`). Sem este campo, um calendário que
            # promete considerar feriados devolve a conta sem eles e ninguém
            # fica sabendo — número errado com cara de certo.
            "feriados_sincronizados": services.base_de_feriados_sincronizada(),
        })

    @action(detail=True, methods=["get"], url_path="termino")
    def termino(self, request, pk=None):
        """`?inicio=AAAA-MM-DD&duracao=N` → a data de término. É a função que o
        CPM da PDCA.1 vai chamar; existir como endpoint agora permite que a tela
        de cadastro mostre o efeito da jornada antes de haver cronograma."""
        from datetime import date as tipo_data

        calendario = self.get_object()
        try:
            inicio = tipo_data.fromisoformat(request.query_params["inicio"])
            duracao = int(request.query_params["duracao"])
        except (KeyError, ValueError):
            raise ValidationError(
                {"inicio": "Informe `inicio` (AAAA-MM-DD) e `duracao` (inteiro ≥ 1)."}
            )
        try:
            fim = services.somar_dias_uteis(calendario, inicio, duracao)
        except DjangoValidationError as erro:
            raise ValidationError({"duracao": erro.messages})
        return Response({"inicio": inicio, "duracao": duracao, "termino": fim})


class ExcecaoCalendarioViewSet(BasePdcaViewSet):
    """Recesso, parada de chuva, mutirão de sábado."""

    queryset = ExcecaoCalendario.objects.select_related("calendario")
    serializer_class = ExcecaoCalendarioSerializer
    required_resource = "pdca.calendario"
    filterset_fields = ["calendario", "trabalha"]
    ordering_fields = ["data"]


# ---------------------------------------------------------------------------
# PDCA.1 — o plano de tempo
# ---------------------------------------------------------------------------


class CronogramaViewSet(BasePdcaViewSet):
    """O plano da obra e seus verbos: calcular, publicar, replanejar.

    Os três verbos não são CRUD, e por isso cada um declara a **sua** permissão
    (§8 da planta). Calcular é do mesmo nível de quem edita; publicar e replanejar
    são atos de compromisso — quem monta o plano não é necessariamente quem o
    assume perante a obra, e é a mesma segregação que o ORC.6 provou necessária.
    """

    queryset = Cronograma.objects.select_related("obra", "calendario", "origem")
    serializer_class = CronogramaSerializer
    required_resource = "pdca.cronograma"
    action_permission_map = {
        "publicar": "pdca.cronograma.publicar",
        "replanejar": "pdca.cronograma.replanejar",
        # Marcar um padrão da empresa e aplicá-lo numa obra nova são atos da
        # mesma classe de quem monta o plano — quem edita, edita. Publicar
        # continua sendo o ato à parte, e o modelo aplicado nasce em rascunho
        # justamente para passar por ele.
        "marcar_modelo": "pdca.cronograma.edit",
        "desmarcar_modelo": "pdca.cronograma.edit",
        "aplicar_modelo": "pdca.cronograma.edit",
        "lote": "pdca.cronograma.edit",
        "renumerar_eap": "pdca.cronograma.edit",
    }
    filterset_fields = ["obra", "status", "versao", "eh_modelo"]
    search_fields = ["descricao", "nome_modelo"]
    ordering_fields = ["versao", "data_inicio", "criado_em"]

    def perform_create(self, serializer):
        """Uma obra tem **um** cronograma, que ganha versões.

        Deixar criar um segundo do zero produziria dois planos sem parentesco
        para a mesma obra — e a linha de base, que é o parentesco, deixaria de
        existir justamente onde ela importa.
        """
        obra = serializer.validated_data.get("obra")
        existente = (self.get_queryset().filter(obra=obra).order_by("-versao").first())
        if existente is not None:
            raise ValidationError({
                "obra": (
                    f"Esta obra já tem cronograma (v{existente.versao}). Para mudar o "
                    "plano, replaneje a versão vigente — é o que preserva a anterior "
                    "como linha de base."
                ),
            })
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if not serializer.instance.editavel:
            raise ValidationError(
                "Só um cronograma em rascunho é editável. Para mudar o plano vigente, replaneje."
            )
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status == Cronograma.Status.VIGENTE:
            raise ValidationError(
                "O cronograma vigente não é excluído — ele é substituído por um replanejamento."
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def calcular(self, request, pk=None):
        """Roda o CPM e grava datas, folgas e caminho crítico."""
        cronograma = self.get_object()
        try:
            return Response(services.calcular_cpm(cronograma))
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})

    @action(detail=True, methods=["post"])
    def publicar(self, request, pk=None):
        """Rascunho → vigente, com o CPM rodado antes de virar a chave."""
        cronograma = self.get_object()
        quem = (
            getattr(request.user, "get_full_name", lambda: "")()
            or getattr(request.user, "username", "")
        )
        try:
            resultado = services.publicar(cronograma, por=quem)
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})
        return Response({
            "cronograma": CronogramaSerializer(cronograma, context=self.get_serializer_context()).data,
            "cpm": resultado,
        })

    @action(detail=True, methods=["post"])
    def replanejar(self, request, pk=None):
        """Cria a versão seguinte em rascunho; esta vira linha de base."""
        cronograma = self.get_object()
        entrada = ReplanejarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            nova = services.replanejar(cronograma, motivo=entrada.validated_data["motivo"])
        except DjangoValidationError as erro:
            raise ValidationError({"motivo": erro.messages})
        return Response(
            CronogramaSerializer(nova, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def gantt(self, request, pk=None):
        """**Uma** chamada com o cronograma inteiro — árvore, setas e linha de base.

        Não é atalho de conveniência: o Gantt sincroniza árvore e linha do tempo,
        e montá-lo em três requisições paginadas produziria a tela desenhando a
        WBS antes de saber as datas, depois pulando quando as setas chegassem. O
        payload é grande de propósito, e é o cliente que virtualiza (planta §5.2).
        """
        cronograma = self.get_object()
        atividades = (cronograma.atividades
                      .select_related("local", "etapa", "item_orcado", "calendario",
                                      "responsavel")
                      .prefetch_related("filhos")
                      .order_by("ordem", "codigo", "atividade_id"))
        ligacoes = Precedencia.objects.filter(origem__cronograma=cronograma)
        contexto = self.get_serializer_context()
        return Response({
            "cronograma": CronogramaSerializer(cronograma, context=contexto).data,
            "atividades": AtividadeSerializer(atividades, many=True, context=contexto).data,
            "precedencias": PrecedenciaSerializer(ligacoes, many=True, context=contexto).data,
            "base": services.comparar_com_base(cronograma),
            "cobertura_orcamento": services.cobertura_do_orcamento(cronograma),
            # PDCA.2: o avanço viaja **junto**, pelo mesmo motivo que as datas —
            # a barra do Gantt mostra o executado dentro do previsto, e buscá-lo
            # numa segunda chamada faria a grade desenhar duas vezes, a segunda
            # com as barras mudando de cor na frente de quem olha.
            "avanco": services.avanco_do_cronograma(cronograma),
        })

    @action(detail=True, methods=["get"], url_path="linha-de-base")
    def linha_de_base(self, request, pk=None):
        """Atividade a atividade, o desvio entre este plano e o combinado."""
        return Response(services.comparar_com_base(self.get_object()))

    # -- PDCA.2: o que a obra respondeu ------------------------------------

    @action(detail=True, methods=["get"])
    def avanco(self, request, pk=None):
        """O avanço de cada atividade e o da obra — físico e financeiro.

        Leitura do plano, e por isso `pdca.cronograma.view`: quem enxerga o
        cronograma enxerga o quanto dele já andou. *Apontar* é outro verbo, com
        outra permissão, noutra rota.
        """
        return Response(services.avanco_do_cronograma(self.get_object()))

    @action(detail=True, methods=["get"], url_path="curva-s")
    def curva_s(self, request, pk=None):
        """Prevista × realizada, física × financeira.

        `?granularidade=dia|semana|mes` (padrão `semana`). Passado o teto de
        pontos do `planos.py`, o servidor **engrossa a granularidade e diz qual
        valeu** — a tela lê `granularidade` e `granularidade_pedida` e rotula o
        gráfico pelo que realmente foi desenhado.
        """
        pedida = request.query_params.get("granularidade", "semana")
        try:
            return Response(services.curva_s(self.get_object(), granularidade=pedida))
        except DjangoValidationError as erro:
            raise ValidationError({"granularidade": erro.messages})

    # -- Plano modelo (PDCA.1b) --------------------------------------------

    @action(detail=False, methods=["get"])
    def modelos(self, request):
        """A biblioteca de padrões da empresa, para o seletor da tela.

        Rota **de coleção** e não filtro da listagem porque a pergunta é outra:
        a listagem responde "quais planos esta empresa tem"; esta responde "que
        padrões eu posso aplicar numa obra nova". Quem pergunta a segunda quase
        nunca quer ver as 40 versões de plano das obras em andamento no meio.
        """
        biblioteca = services.modelos_do_tenant(request.user.tenant_id)
        pagina = self.paginate_queryset(biblioteca)
        serializer = self.get_serializer(pagina if pagina is not None else biblioteca, many=True)
        if pagina is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="marcar-modelo")
    def marcar_modelo(self, request, pk=None):
        """Promove este plano a modelo da biblioteca — e é aqui que a quota morde.

        A checagem vem **antes** de gravar, com o mecanismo de sempre: 402 com o
        limite e o uso no corpo, para a tela oferecer upgrade em vez de mandar
        falar com alguém.
        """
        cronograma = self.get_object()
        entrada = MarcarModeloSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        if not cronograma.eh_modelo:
            checar_quota(request.user, "planos_modelo")
        try:
            services.marcar_como_modelo(cronograma, nome=entrada.validated_data["nome"])
        except DjangoValidationError as erro:
            raise ValidationError({"nome": erro.messages})
        return Response(self.get_serializer(cronograma).data)

    @action(detail=True, methods=["post"], url_path="desmarcar-modelo")
    def desmarcar_modelo(self, request, pk=None):
        cronograma = self.get_object()
        services.desmarcar_modelo(cronograma)
        return Response(self.get_serializer(cronograma).data)

    @action(detail=True, methods=["post"], url_path="aplicar-modelo")
    def aplicar_modelo(self, request, pk=None):
        """Cria o plano de uma obra a partir deste modelo."""
        modelo = self.get_object()
        entrada = AplicarModeloSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        # A obra é buscada pelo queryset com escopo do tenant, e não por
        # `Obra.objects`: um id de outra empresa tem de virar 400 aqui, e não
        # um cronograma nascendo do lado de lá da fronteira.
        from obras.models import Obra
        obra = (Obra.objects.filter(pk=dados["obra"], tenant_id=request.user.tenant_id)
                .first())
        if obra is None:
            raise ValidationError({"obra": "Obra não encontrada nesta empresa."})

        calendario = None
        if dados.get("calendario"):
            calendario = (CalendarioTrabalho.objects
                          .filter(pk=dados["calendario"], tenant_id=request.user.tenant_id)
                          .first())
            if calendario is None:
                raise ValidationError({"calendario": "Calendário não encontrado."})
            if calendario.obra_id and calendario.obra_id != obra.pk:
                raise ValidationError({"calendario": "Este calendário é de outra obra."})

        try:
            novo = services.aplicar_modelo(
                modelo, obra=obra, descricao=dados.get("descricao", ""),
                data_inicio=dados["data_inicio"], calendario=calendario,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"modelo": erro.messages})
        return Response(
            CronogramaSerializer(novo, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="renumerar-eap")
    def renumerar_eap(self, request, pk=None):
        """Reescreve a EAP inteira na ordem da árvore, numa transação.

        `{"simular": true}` conta sem escrever — a tela pergunta antes de mexer
        no código de 87 atividades de uma vez.
        """
        cronograma = self.get_object()
        simular = bool(request.data.get("simular"))
        try:
            return Response(services.renumerar_eap(cronograma, simular=simular))
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})

    @action(detail=True, methods=["post"])
    def lote(self, request, pk=None):
        """Muitas células numa requisição — o gesto de colar planilha."""
        cronograma = self.get_object()
        entrada = LoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.escrever_em_lote(
                cronograma, entrada.validated_data["edicoes"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"edicoes": erro.messages})
        return Response(resultado)

    @action(detail=True, methods=["get"])
    def cobertura(self, request, pk=None):
        """Quantas atividades têm régua de custo — vínculo que não existe não é
        inventado (planta §11.1)."""
        return Response(services.cobertura_do_orcamento(self.get_object()))


class AtividadeViewSet(BasePdcaViewSet):
    """A WBS. Pertence ao cronograma, e por isso usa a permissão dele."""

    queryset = Atividade.objects.select_related(
        "cronograma", "pai", "local", "etapa", "item_orcado", "calendario", "responsavel"
    )
    serializer_class = AtividadeSerializer
    required_resource = "pdca.cronograma"
    filterset_fields = ["cronograma", "pai", "critica", "eh_marco", "local", "etapa"]
    search_fields = ["codigo", "nome"]
    ordering_fields = ["ordem", "codigo", "inicio_cedo", "termino_cedo", "folga_total"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("raiz") in ("1", "true"):
            qs = qs.filter(pai__isnull=True)
        return qs

    def perform_create(self, serializer):
        cronograma = serializer.validated_data.get("cronograma")
        pai = serializer.validated_data.get("pai")
        try:
            services.validar_teto_de_atividades(cronograma)
            services.validar_profundidade_wbs(pai)
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})
        super().perform_create(serializer)
        serializer.instance.profundidade = 1 if pai is None else pai.profundidade + 1
        serializer.instance.save(update_fields=["profundidade"])

    def perform_update(self, serializer):
        super().perform_update(serializer)
        instancia = serializer.instance
        nova = 1 if instancia.pai is None else instancia.pai.profundidade + 1
        if instancia.profundidade != nova:
            instancia.profundidade = nova
            instancia.save(update_fields=["profundidade"])
            self._reprofundar(instancia)

    def _reprofundar(self, no: Atividade) -> None:
        for filho in no.filhos.all():
            filho.profundidade = no.profundidade + 1
            filho.save(update_fields=["profundidade"])
            self._reprofundar(filho)

    def perform_destroy(self, instance):
        if not instance.cronograma.editavel:
            raise ValidationError(
                "Este cronograma não é mais rascunho. Para mudar o plano, replaneje."
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def reprogramar(self, request, pk=None):
        """O gesto de **arrastar a barra** no Gantt, com nome de domínio.

        Arrastar não move a barra: fixa uma **restrição de data** ("não começar
        antes de") e manda o CPM recalcular. É a diferença entre uma tela de
        desenho e um cronograma — a barra que o planejador soltou pode voltar
        para trás se uma predecessora não permitir, e é isso que ele precisa ver
        acontecer.

        Aceita também `duracao_dias` (o gesto de esticar a ponta da barra).
        """
        atividade = self.get_object()
        if not atividade.cronograma.editavel:
            raise ValidationError(
                "Este cronograma não é mais rascunho. Para reprogramar, replaneje."
            )

        from datetime import date as tipo_data

        dados = request.data
        if "nao_comecar_antes_de" in dados:
            bruto = dados.get("nao_comecar_antes_de")
            if bruto in (None, ""):
                atividade.nao_comecar_antes_de = None
            else:
                try:
                    atividade.nao_comecar_antes_de = tipo_data.fromisoformat(str(bruto))
                except ValueError:
                    raise ValidationError({
                        "nao_comecar_antes_de": "Use o formato AAAA-MM-DD.",
                    })
        if "duracao_dias" in dados:
            try:
                duracao = int(dados["duracao_dias"])
            except (TypeError, ValueError):
                raise ValidationError({"duracao_dias": "Informe um inteiro."})
            if not atividade.eh_marco and duracao < 1:
                raise ValidationError({
                    "duracao_dias": "A duração precisa ser de ao menos 1 dia útil.",
                })
            atividade.duracao_dias = duracao
        atividade.save(update_fields=["nao_comecar_antes_de", "duracao_dias"])

        try:
            cpm = services.calcular_cpm(atividade.cronograma)
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})
        atividade.refresh_from_db()
        return Response({
            "atividade": AtividadeSerializer(
                atividade, context=self.get_serializer_context()
            ).data,
            "cpm": cpm,
        })


class PrecedenciaViewSet(BasePdcaViewSet):
    """As setas do Gantt. Criar uma é o gesto de ligar duas barras."""

    queryset = Precedencia.objects.select_related("origem", "destino")
    serializer_class = PrecedenciaSerializer
    required_resource = "pdca.cronograma"
    filterset_fields = ["origem", "destino", "tipo"]
    ordering_fields = ["destino", "origem"]

    def get_queryset(self):
        qs = super().get_queryset()
        cronograma = self.request.query_params.get("cronograma")
        if cronograma:
            qs = qs.filter(origem__cronograma_id=cronograma)
        return qs

    def perform_destroy(self, instance):
        if not instance.origem.cronograma.editavel:
            raise ValidationError(
                "Este cronograma não é mais rascunho. Para mudar as precedências, replaneje."
            )
        super().perform_destroy(instance)


# ---------------------------------------------------------------------------
# PDCA.2 — o avanço apontado
# ---------------------------------------------------------------------------


class ApontamentoAvancoViewSet(TenantScopedViewSetMixin,
                               mixins.CreateModelMixin,
                               mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    """O livro-razão do avanço — **lê, cria e estorna; não edita nem apaga**.

    Não é `ModelViewSet` de propósito, e a diferença não é estética: um
    `ModelViewSet` publicaria `PUT`, `PATCH` e `DELETE`, e a fatia inteira existe
    para que esses três verbos não existam aqui. Corrigir é estornar — o registro
    errado continua legível, a correção aponta para ele, e a soma dá o número
    certo.

    **Duas permissões, e não o par `view`/`edit` de um CRUD** (planta §8): ler o
    avanço é do gestor e do cliente do relatório; *apontar* é o ato de campo que
    vira dinheiro na medição da PDCA.3.
    """

    queryset = ApontamentoAvanco.objects.select_related(
        "atividade", "atividade__cronograma", "local", "estorna",
    )
    serializer_class = ApontamentoAvancoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.avanco.view", "write": "pdca.avanco.apontar"}
    action_permission_map = {
        "estornar": "pdca.avanco.apontar",
        "lote": "pdca.avanco.apontar",
    }
    filterset_fields = ["atividade", "local", "origem", "data"]
    search_fields = ["observacao", "apontado_por"]
    ordering_fields = ["data", "registrado_em", "percentual"]

    def get_queryset(self):
        qs = super().get_queryset()
        # O recorte natural do apontamento não é a atividade: é o **plano**
        # (a tela do avanço) ou a **janela de datas** (o boletim da semana).
        cronograma = self.request.query_params.get("cronograma")
        if cronograma:
            qs = qs.filter(atividade__cronograma_id=cronograma)
        obra = self.request.query_params.get("obra")
        if obra:
            qs = qs.filter(atividade__cronograma__obra_id=obra)
        de = self.request.query_params.get("de")
        if de:
            qs = qs.filter(data__gte=de)
        ate = self.request.query_params.get("ate")
        if ate:
            qs = qs.filter(data__lte=ate)
        return qs

    def _quem(self) -> str:
        return (
            getattr(self.request.user, "get_full_name", lambda: "")()
            or getattr(self.request.user, "username", "")
        )

    def _da_minha_empresa(self, atividade) -> None:
        """A FK garante que a atividade existe, não que ela é desta empresa.

        No Postgres a RLS já barraria a escrita; no SQLite de desenvolvimento ela
        é no-op, e sem esta linha um id adivinhado gravaria avanço no plano do
        vizinho. É a mesma defesa em profundidade do resto da casa.
        """
        meu = getattr(self.request.user, "tenant_id", None)
        if meu is not None and atividade.tenant_id != meu:
            raise ValidationError({"atividade": "Esta atividade não é desta empresa."})

    def perform_create(self, serializer):
        """A escrita passa pelo **serviço**, e não pelo `serializer.save()`.

        As recusas do avanço (sintética, marco, plano não vigente, acumulado
        acima de 100) e a trava de concorrência vivem lá porque a escrita em
        lote, o estorno e — depois — o WhatsApp entram pelos mesmos portões sem
        passar por este.
        """
        dados = serializer.validated_data
        atividade = dados["atividade"]
        self._da_minha_empresa(atividade)
        try:
            serializer.instance = services.registrar_apontamento(
                atividade=atividade,
                percentual=dados["percentual"],
                data=dados["data"],
                local=dados.get("local"),
                origem=dados.get("origem") or "web",
                observacao=dados.get("observacao", ""),
                foto=dados.get("foto"),
                por=self._quem(),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"percentual": erro.messages})

    @action(detail=True, methods=["post"])
    def estornar(self, request, pk=None):
        """Corrigir um apontamento é criar o de sinal contrário, com motivo."""
        apontamento = self.get_object()
        entrada = EstornoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estorno = services.estornar(
                apontamento,
                motivo=entrada.validated_data["motivo"],
                data=entrada.validated_data.get("data"),
                por=self._quem(),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"motivo": erro.messages})
        return Response(
            self.get_serializer(estorno).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def lote(self, request):
        """A grade da semana: N frentes numa transação — tudo ou nada."""
        entrada = ApontamentoEmLoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cronograma = entrada.validated_data["cronograma"]
        meu = getattr(request.user, "tenant_id", None)
        if meu is not None and cronograma.tenant_id != meu:
            raise ValidationError({"cronograma": "Este plano não é desta empresa."})
        linhas = [
            {
                "atividade": linha["atividade"],
                "data": linha["data"],
                "percentual": linha["percentual"],
                "local": linha.get("local"),
                "origem": linha.get("origem"),
                "observacao": linha.get("observacao", ""),
            }
            for linha in entrada.validated_data["linhas"]
        ]
        try:
            resultado = services.apontar_em_lote(cronograma, linhas, por=self._quem())
        except DjangoValidationError as erro:
            raise ValidationError({"linhas": erro.messages})
        return Response(resultado, status=status.HTTP_201_CREATED)
