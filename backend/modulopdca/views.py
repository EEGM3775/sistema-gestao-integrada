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
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import (
    filters, mixins, permissions, status, views, viewsets,
)
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from nucleo.busca import BuscaSemAcento
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.quotas import checar_quota
from nucleo.tenancy import TenantScopedViewSetMixin
from payment.planos import (
    PDCA_PROFUNDIDADE_MAXIMA_WBS,
    PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO,
    PDCA_TETO_DEDUCOES_POR_MEDICAO,
    PDCA_TETO_ITENS_POR_ADITIVO,
    PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
    PDCA_TETO_ITENS_POR_CONTRATO,
    PDCA_TETO_LINHAS_POR_LOTE,
    PDCA_TETO_LINHAS_POR_MEDICAO,
)

from . import services
from .models import (
    AditivoContrato, ApontamentoAvanco, Atividade, CalendarioTrabalho,
    ContratoObra, Cronograma, ExcecaoCalendario, ItemContrato,
    LiberacaoRetencao, LocalObra, Medicao, Precedencia,
)
from .pagination import PdcaPageNumberPagination
from .serializers import (
    AbrirAditivoSerializer,
    AbrirMedicaoSerializer,
    AditivoContratoSerializer,
    AtestarSerializer,
    CabecalhoDeMedicaoSerializer,
    LinhaDeAditivoSerializer,
    LinhaDeDeducaoSerializer,
    MedicaoResumoSerializer,
    ApontamentoAvancoSerializer,
    ApontamentoEmLoteSerializer,
    AplicarModeloSerializer,
    AtividadeSerializer,
    CalendarioTrabalhoSerializer,
    ContratoObraSerializer,
    CronogramaSerializer,
    ExcecaoCalendarioSerializer,
    GeracaoEmLoteSerializer,
    ItemContratoSerializer,
    LiberacaoRetencaoSerializer,
    LinhaDeMedicaoSerializer,
    LocalObraSerializer,
    LoteSerializer,
    EstornoSerializer,
    MarcarModeloSerializer,
    MedicaoSerializer,
    PrecedenciaSerializer,
    PropostaDeMedicaoSerializer,
    ReplanejarSerializer,
    RetificarSerializer,
    SolicitarLiberacaoSerializer,
    SubmeterSerializer,
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
            "fatia": "PDCA.4",
            "recursos": {
                "locais": True,
                "calendario": True,
                "cronograma": True,
                "modelo": True,
                "avanco": True,
                "contrato": True,
                "medicao": True,
                "retencao": True,
                # PDCA.4 — o aditivo existe, e com ele a trava do acumulado
                # passou a ser contra o contratado **atual** (original + deltas
                # aprovados), e não contra o do dia da assinatura.
                "aditivo": True,
                "deducoes": True,
                "material_estocado": True,
                # O que a PDCA.4 **não** fecha, dito na própria capacidade: a
                # planilha do empreiteiro entra colando coluna na grade, não por
                # um wizard de xlsx com conferência lado a lado; e o anexo por
                # linha de medição é texto — a evidência fotográfica mora no
                # apontamento de avanço, e a memória de cálculo é a ponte até
                # ela. A tela precisa saber disto para não oferecer botão que
                # não foi feito.
                "importar_planilha_do_empreiteiro": False,
                "anexo_por_linha": False,
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
                "itens_por_contrato": PDCA_TETO_ITENS_POR_CONTRATO,
                "linhas_por_medicao": PDCA_TETO_LINHAS_POR_MEDICAO,
                "itens_por_aditivo": PDCA_TETO_ITENS_POR_ADITIVO,
                "aditivos_abertos_por_contrato": (
                    PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO
                ),
                "deducoes_por_medicao": PDCA_TETO_DEDUCOES_POR_MEDICAO,
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


# ---------------------------------------------------------------------------
# PDCA.3 — contrato, medição e liberação de retenção
# ---------------------------------------------------------------------------
#
# A segregação da planta §8 aparece aqui como **três verbos para a medição**, e
# não o par `view`/`edit`:
#
#   - `pdca.medicao.view` — ler. É do gestor, da diretoria e de quem recebe
#     relatório;
#   - `pdca.medicao.apurar` — abrir o boletim e conferir a proposta. É o gesto
#     de quem acompanha a obra;
#   - `pdca.medicao.atestar` — decidir. É o que faz o dinheiro sair.
#
# Quem apura **não** ateste, e a máquina do `nucleo` já recusa o autoatesto por
# padrão. Separar os dois verbos aqui é o que torna essa recusa configurável em
# vez de acidental — um tenant que queira a mesma pessoa nos dois papéis liga
# `permite_autoatesto` no fluxo, por escrito.


def _quem_e(request) -> str:
    """Rótulo durável de quem agiu, no molde do resto do módulo."""
    return (
        getattr(request.user, "get_full_name", lambda: "")()
        or getattr(request.user, "username", "")
    )


def _meu_contrato(request, contrato_id):
    """O contrato, conferido contra o tenant de quem pede.

    A RLS já recusaria o cruzamento no banco, mas ela devolve "não existe" — e
    quem está montando um aditivo precisa saber a diferença entre um id errado e
    um contrato de outra empresa.
    """
    if not contrato_id:
        raise ValidationError({"contrato": "Informe o contrato."})
    contrato = ContratoObra.objects.filter(pk=contrato_id).first()
    if contrato is None:
        raise ValidationError({"contrato": "Contrato não encontrado."})
    meu = getattr(request.user, "tenant_id", None)
    if meu is not None and contrato.tenant_id != meu:
        raise ValidationError({"contrato": "Este contrato não é desta empresa."})
    return contrato


def _exige(request, permissao: str, motivo: str) -> None:
    """Confere uma permissão **além** da do portão, com a mesma leitura
    fail-closed do `RequirePermission`: admin de tenant e superusuário passam,
    os demais precisam do código exato na claim.

    É o que separa "submeter" de "aprovar" no tenant que ainda não montou
    escada — ali submeter aprova em um passo, e quem não tem a permissão de
    decidir não pode exercê-la por falta de configuração alheia.
    """
    usuario = request.user
    if getattr(usuario, "is_tenant_admin", False) or getattr(
        usuario, "is_superuser", False
    ):
        return
    if permissao not in (getattr(usuario, "iam_permissions", None) or []):
        raise PermissionDenied(motivo)


class ContratoObraViewSet(BasePdcaViewSet):
    """O que foi combinado com o empreiteiro, e o cockpit do saldo.

    **Só dois verbos** (`view`/`edit`), diferente da medição: montar o contrato é
    um ato só. A segregação que importa está do outro lado — quem monta o
    contrato pode não ser quem ateste a medição que nasce dele.
    """

    queryset = ContratoObra.objects.select_related("obra", "fornecedor")
    serializer_class = ContratoObraSerializer
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.contrato.edit"}
    action_permission_map = {
        "saldo": "pdca.contrato.view",
        "proposta_de_medicao": "pdca.medicao.view",
        "periodo_sugerido": "pdca.medicao.view",
        "retencao": "pdca.contrato.view",
        # **Liberar retenção é ato de atesto, não de cadastro.** Sem esta linha
        # a ação cairia no `write` do mapa acima (`pdca.contrato.edit`) e quem
        # monta a planilha contratual poderia devolver a caução sozinho — a
        # mesma pessoa definindo o valor retido e mandando-o de volta. É a
        # segregação da §8 aplicada ao dinheiro que estava parado.
        "liberar_retencao": "pdca.medicao.atestar",
    }
    filterset_fields = ["obra", "fornecedor", "status", "regime", "regime_publico"]
    search_fields = ["numero", "objeto", "fornecedor__razao_social"]
    ordering_fields = ["criado_em", "numero", "data_inicio"]

    @action(detail=True, methods=["get"])
    def saldo(self, request, pk=None):
        """Contratado × medido × saldo × retenção — derivado inteiro (§4.9).

        É a leitura que abre a tela do contrato. Vem do servidor, e não montada
        no navegador a partir da lista de medições, pelo mesmo motivo do CPM:
        é número de dinheiro, e dois lugares somando dariam duas verdades.
        """
        contrato = self.get_object()
        dados = services.saldo_do_contrato(contrato)
        return Response(_str_decimais(dados))

    @action(detail=True, methods=["get"], url_path="proposta-de-medicao")
    def proposta_de_medicao(self, request, pk=None):
        """A prévia: o que se mediria neste período, **sem gravar nada**.

        Existe separada do `abrir` porque o gesto do gestor é olhar antes de
        decidir. Abrir a medição só para ver a proposta encheria o contrato de
        rascunhos que ele teria de apagar depois — e cada rascunho apagado é uma
        linha na lixeira.
        """
        contrato = self.get_object()
        entrada = PropostaDeMedicaoSerializer(data=request.query_params)
        entrada.is_valid(raise_exception=True)
        try:
            proposta = services.propor_medicao(
                contrato,
                inicio=entrada.validated_data["inicio"],
                fim=entrada.validated_data["fim"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"periodo": erro.messages})
        return Response(_str_decimais(proposta))

    @action(detail=True, methods=["get"], url_path="periodo-sugerido")
    def periodo_sugerido(self, request, pk=None):
        """De quando a **próxima** medição deveria falar.

        Medição de obra é uma corrente: o período começa no dia seguinte ao fim
        do anterior. A tela abria sempre em "primeiro do mês → hoje", o que
        produzia sobreposição no mês medido quinzenalmente e buraco no mês em
        que a medição atrasou — e nenhum dos dois aparecia em lugar nenhum.
        """
        contrato = self.get_object()
        return Response(_str_decimais(services.sugerir_periodo(contrato)))

    @action(detail=True, methods=["get"], url_path="retencao")
    def retencao(self, request, pk=None):
        """Retido, liberado e disponível — as três parcelas, não só o saldo."""
        contrato = self.get_object()
        return Response(_str_decimais(services.retencao_disponivel(contrato)))

    @action(detail=True, methods=["post"], url_path="liberar-retencao")
    def liberar_retencao(self, request, pk=None):
        """Põe na escada o pedido de devolver o retido.

        **Escada própria, não a da medição** (ver o model): quem ateste medição
        confere serviço executado; quem libera caução confere condição
        contratual cumprida.
        """
        contrato = self.get_object()
        entrada = SolicitarLiberacaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.solicitar_liberacao(
                contrato=contrato,
                valor=entrada.validated_data["valor"],
                data=entrada.validated_data["data"],
                condicao_atendida=entrada.validated_data["condicao_atendida"],
                solicitante=request.user,
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"valor": erro.messages})
        return Response(
            {
                "estado": resultado["estado"],
                "escada": resultado["escada"],
                "liberacao": LiberacaoRetencaoSerializer(
                    resultado["liberacao"], context=self.get_serializer_context(),
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ItemContratoViewSet(BasePdcaViewSet):
    """As linhas do contrato. O teto do `planos.py` é cobrado na criação."""

    queryset = ItemContrato.objects.select_related(
        "contrato", "item_orcado", "atividade",
    )
    serializer_class = ItemContratoSerializer
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.contrato.edit"}
    filterset_fields = ["contrato", "item_orcado", "atividade"]
    search_fields = ["codigo", "descricao"]
    ordering_fields = ["ordem", "codigo"]

    def perform_create(self, serializer):
        """Confere o teto e o estado do contrato, e **delega a gravação**.

        O `super()` no fim não é formalidade: é ele que injeta o `tenant_id` do
        usuário (`TenantScopedViewSetMixin.perform_create`). Um `serializer.save()`
        direto aqui gravaria a linha sem tenant — e a RLS fail-closed da tabela
        recusa o INSERT com um 500 seco, que foi exatamente o que o E2E pegou
        nesta view antes de esta linha existir.
        """
        contrato = serializer.validated_data["contrato"]
        try:
            services.validar_teto_de_itens(contrato)
        except DjangoValidationError as erro:
            raise ValidationError({"contrato": erro.messages})
        self._so_com_contrato_editavel(contrato)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        contrato = serializer.instance.contrato
        self._so_com_contrato_editavel(contrato)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._so_com_contrato_editavel(instance.contrato)
        if instance.medicoes.exists():
            raise ValidationError({
                "detail": (
                    f"O item {instance.codigo} já foi medido — excluí-lo apagaria "
                    f"a razão de uma linha paga. Se ele não vale mais, a saída é "
                    f"o aditivo de supressão."
                ),
            })
        super().perform_destroy(instance)

    def _so_com_contrato_editavel(self, contrato) -> None:
        """**A planilha contratual fecha quando alguém já mediu contra ela.**

        A regra mora em `services.planilha_editavel`, e esta view só a aplica —
        a mesma função responde ao serializer, para a tela nunca oferecer um
        botão que a API vai recusar.

        **Esta trava nasceu de um achado do dono** (15/09/2026): a tela dizia
        *"a planilha não se edita mais aqui"* e a API aceitava a edição do mesmo
        jeito — ele mudou uma quantidade contratada de 53.150 para 631.500 num
        contrato com medição em aprovação. Regra que mora só na interface não é
        regra: é aviso. O comando de bancada, a importação e a aba antiga
        aberta no navegador continuam passando por aqui.
        """
        aberta, motivo = services.planilha_editavel(contrato)
        if not aberta:
            raise ValidationError({"contrato": motivo})



class MedicaoViewSet(TenantScopedViewSetMixin,
                     mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    """O boletim do período — **abre, submete, retifica; não se edita por PUT**.

    Não é `ModelViewSet`, e pelo mesmo motivo do apontamento: o documento tem
    ciclo de vida, e um `PATCH` genérico publicaria um caminho que atravessa o
    congelamento. Criar é `abrir/` (que roda a proposta); mudar a grade é
    `linhas/` e só em rascunho; corrigir depois de aprovada é `retificar/`.

    `DELETE` existe e vai para a **lixeira** (o `Excluivel` no model), não para o
    banco — e só em rascunho: medição que já subiu a escada é documento com
    decisão registrada.
    """

    queryset = Medicao.objects.select_related(
        "contrato", "contrato__obra", "contrato__fornecedor", "retifica",
    ).prefetch_related(
        "itens", "itens__item_contrato", "deducoes",
        # Sem estes dois, `escada` dispara uma consulta **por medição** — 100
        # consultas para desenhar a lista lateral de um contrato antigo.
        "aprovacoes", "aprovacoes__nivel_atual", "aprovacoes__atestos",
    )
    serializer_class = MedicaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.medicao.view", "write": "pdca.medicao.apurar"}
    action_permission_map = {
        "abrir": "pdca.medicao.apurar",
        "linhas": "pdca.medicao.apurar",
        "submeter": "pdca.medicao.apurar",
        "retificar": "pdca.medicao.apurar",
        "cancelar": "pdca.medicao.apurar",
        # Decidir é verbo de outra pessoa (planta §8). Quando há escada
        # configurada, o motor do `nucleo` confere a permissão do **degrau** e
        # esta aqui é só o portão de entrada; sem escada, ela é a decisão.
        "atestar": "pdca.medicao.atestar",
    }
    filterset_fields = ["contrato", "status", "contrato__obra"]
    search_fields = ["observacao", "apurada_por", "contrato__numero"]
    ordering_fields = ["numero", "periodo_fim", "apurada_em"]

    def get_serializer_class(self):
        """`?resumo=1` devolve a medição **sem as linhas**.

        Quem lista quer o cabeçalho; quem abre um documento pede o documento. A
        lista da tela do contrato mandava todos os itens de todas as medições —
        meio megabyte de JSON para escrever quarenta linhas de texto.
        """
        if self.action == "list" and self.request.query_params.get("resumo") in (
            "1", "true",
        ):
            return MedicaoResumoSerializer
        return super().get_serializer_class()

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        """Abre o boletim do período a partir da proposta do avanço."""
        contrato_id = request.data.get("contrato")
        if not contrato_id:
            raise ValidationError({"contrato": "Informe o contrato."})
        contrato = self._meu_contrato(contrato_id)

        entrada = AbrirMedicaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        linhas = dados.get("linhas")
        try:
            medicao = services.criar_medicao(
                contrato=contrato,
                inicio=dados["inicio"],
                fim=dados["fim"],
                por=_quem_e(request),
                linhas=(
                    [
                        {"item_contrato_id": l["item_contrato_id"],
                         "quantidade": l["quantidade"]}
                        for l in linhas
                    ] if linhas is not None else None
                ),
                custo_reembolsavel=dados.get("custo_reembolsavel"),
                observacao=dados.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            self.get_serializer(medicao).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def contexto(self, request, pk=None):
        """**A grade desta medição, inteira, calculada no servidor.**

        Devolve uma linha por item do contrato — com contratado original,
        aditivos, contratado atual, acumulado anterior (já **sem** esta
        medição), proposta do período, material estocado, saldo e o que está
        gravado aqui —, mais os totais e o degrau da escada.

        **Existe porque a tela não pode fazer esta conta.** A primeira escrita
        da página montava `saldo = contratado − já medido` no navegador, a
        partir de uma prévia que só era buscada quando *não* havia medição
        aberta. Quem chegasse pelo link direto de uma medição via "já medido"
        **negativo** e saldo acima do contratado — e, como a trava de excesso da
        grade compara contra esse saldo, ela também parava de funcionar
        exatamente ali. Um endpoint, uma verdade.
        """
        medicao = self.get_object()
        try:
            dados = services.contexto_de_medicao(medicao)
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        dados["escada"] = self.get_serializer(medicao).data.get("escada")
        return Response(_str_decimais(dados))

    @action(detail=True, methods=["post"])
    def cabecalho(self, request, pk=None):
        """Os campos do documento que não são a grade, em rascunho.

        São dois — custo reembolsável e observação —, e eles não cabiam em
        `linhas/`: no regime de **administração** não há linha nenhuma, o que se
        mede é o custo, e sem este endpoint esse regime inteiro ficava sem porta
        na tela (abria a medição e nunca conseguia submetê-la).
        """
        medicao = self.get_object()
        self._so_rascunho(medicao)
        entrada = CabecalhoDeMedicaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        campos = []
        if "custo_reembolsavel" in dados:
            medicao.custo_reembolsavel = dados["custo_reembolsavel"]
            campos.append("custo_reembolsavel")
        if "observacao" in dados:
            medicao.observacao = dados["observacao"]
            campos.append("observacao")
        if campos:
            medicao.save(update_fields=campos)
        return Response(self.get_serializer(medicao).data)

    @action(detail=True, methods=["post"])
    def deducoes(self, request, pk=None):
        """Reescreve as deduções do rascunho — substitui, não soma.

        Retenção contratual **não** entra aqui: ela é cláusula do contrato,
        congelada no nascimento do documento, e volta para o empreiteiro pela
        `LiberacaoRetencao`. O que entra são os descontos que **não voltam** —
        imposto retido, amortização de adiantamento, multa.
        """
        medicao = self.get_object()
        self._so_rascunho(medicao)
        entrada = LinhaDeDeducaoSerializer(
            data=request.data.get("deducoes", []), many=True,
        )
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reescrever_deducoes(
                medicao=medicao,
                deducoes=[dict(linha) for linha in entrada.validated_data],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"deducoes": erro.messages})
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def linhas(self, request, pk=None):
        """Reescreve a grade do rascunho — o gestor conferindo item a item.

        Substitui, não soma: a grade da tela é o documento inteiro, e um
        endpoint que acumulasse faria dois envios acidentais dobrarem a medição.
        """
        medicao = self.get_object()
        self._so_rascunho(medicao)
        entrada = LinhaDeMedicaoSerializer(data=request.data.get("linhas", []), many=True)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reescrever_linhas(
                medicao=medicao, linhas=entrada.validated_data,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"linhas": erro.messages})
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def submeter(self, request, pk=None):
        """Rascunho → escada de atesto (ou aprovação em um passo, sem fluxo).

        **Sem fluxo configurado o caminho é de um passo, e ele exige
        `pdca.medicao.atestar`** — não o `apurar` que abriu o documento. Sem
        essa conferência, um tenant que ainda não montou a escada daria a quem
        apura o poder de aprovar o próprio boletim, que é exatamente a
        segregação que a fatia existe para manter.
        """
        from nucleo import aprovacao as motor

        medicao = self.get_object()
        entrada = SubmeterSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        if motor.fluxo_para(medicao, tenant_id=medicao.tenant_id) is None:
            self._exige(request, "pdca.medicao.atestar", (
                "Esta empresa não tem escada de aprovação configurada para "
                "medição, então submeter aprovaria em um passo — e aprovar exige "
                "'pdca.medicao.atestar', que você não tem. Peça ao administrador "
                "do tenant que monte o fluxo em /api/aprovacao/fluxos/ (alvo "
                "'modulopdca.medicao'), para separar quem apura de quem decide."
            ))
        try:
            resultado = services.submeter_medicao(
                medicao=medicao, solicitante=request.user,
                observacao=entrada.validated_data.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        medicao.refresh_from_db()
        return Response({
            "estado": resultado["estado"],
            "escada": resultado["escada"],
            "avisos": resultado["avisos"],
            "medicao": self.get_serializer(medicao).data,
        })

    @action(detail=True, methods=["post"])
    def retificar(self, request, pk=None):
        """Abre a medição que corrige uma já congelada (§11.5)."""
        medicao = self.get_object()
        entrada = RetificarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            nova = services.retificar(
                medicao=medicao,
                motivo=entrada.validated_data["motivo"],
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"motivo": erro.messages})
        return Response(
            self.get_serializer(nova).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def atestar(self, request, pk=None):
        """Um degrau da escada, decidido a partir da tela da medição.

        É um encaminhador fino para `/api/aprovacao/`, e existe por um motivo de
        produto: quem ateste está **olhando a medição** — a grade, os itens, o
        líquido. Obrigá-lo a sair para outra tela para clicar em "aprovar"
        separaria a decisão da evidência, que é o oposto do que a escada existe
        para garantir.

        Quem decide de verdade é o motor do `nucleo`: ele confere a permissão
        **do degrau**, recusa o autoatesto e trava a linha do pedido. Esta view
        não redecide nada disso.
        """
        from nucleo import aprovacao as motor

        medicao = self.get_object()
        pedido = motor.pedido_de(medicao)
        if pedido is None:
            raise ValidationError({
                "detail": (
                    "Esta medição não está em nenhuma escada de aprovação "
                    f"(status: {medicao.get_status_display().lower()})."
                ),
            })
        entrada = AtestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            pedido = motor.decidir(
                pedido=pedido, usuario=request.user,
                aprovar=entrada.validated_data["aprovar"],
                observacao=entrada.validated_data.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        medicao.refresh_from_db()
        return Response({
            "estado_do_pedido": pedido.estado,
            "nivel_atual": getattr(pedido.nivel_atual, "nome", None),
            "medicao": self.get_serializer(medicao).data,
        })

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Retira o documento sem decidir o mérito.

        Cancelar **também congela** (ver `Medicao.esta_congelada`): um documento
        retirado que voltasse a ser editável seria o caminho para reaproveitar
        número de medição.
        """
        from nucleo import aprovacao as motor

        medicao = self.get_object()
        if medicao.esta_congelada:
            raise ValidationError({
                "detail": (
                    f"A medição já está {medicao.get_status_display().lower()} e "
                    f"não se cancela."
                ),
            })
        pedido = motor.pedido_de(medicao)
        if pedido is not None:
            try:
                motor.cancelar(
                    pedido=pedido, usuario=request.user,
                    motivo=request.data.get("motivo", ""),
                )
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        medicao.status = Medicao.Status.CANCELADA
        medicao.congelada_em = timezone.now()
        medicao.save(update_fields=["status", "congelada_em"])
        return Response(self.get_serializer(medicao).data)

    def perform_destroy(self, instance):
        self._so_rascunho(instance)
        super().perform_destroy(instance)

    # --- apoio ------------------------------------------------------------
    def _meu_contrato(self, contrato_id):
        return _meu_contrato(self.request, contrato_id)

    def _so_rascunho(self, medicao) -> None:
        if medicao.status != Medicao.Status.RASCUNHO:
            raise ValidationError({
                "detail": (
                    f"A medição está {medicao.get_status_display().lower()} e não "
                    f"aceita mais mudança. Para corrigir uma medição aprovada, "
                    f"use 'retificar'."
                ),
            })

    def _exige(self, request, permissao: str, motivo: str) -> None:
        _exige(request, permissao, motivo)


class AditivoContratoViewSet(TenantScopedViewSetMixin,
                             mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.DestroyModelMixin,
                             viewsets.GenericViewSet):
    """O aditivo — **abre, submete, aprova; não se edita por PUT**.

    Mesma forma da medição, pelo mesmo motivo: o documento tem ciclo de vida, e
    um `PATCH` genérico publicaria um caminho que atravessa a aprovação. Criar é
    `abrir/`, mudar as linhas é `itens/` e só em rascunho, decidir é `atestar/`.

    **Aprovar é `pdca.aditivo.aprovar`, e montar é `pdca.aditivo.edit`.** A
    separação é a mesma da medição e existe pela mesma razão: quem negocia o
    acréscimo com o empreiteiro não pode ser quem autoriza a empresa a gastá-lo.
    """

    queryset = AditivoContrato.objects.select_related(
        "contrato", "contrato__obra", "contrato__fornecedor",
    ).prefetch_related(
        "itens", "itens__item_contrato",
        "aprovacoes", "aprovacoes__nivel_atual", "aprovacoes__atestos",
    )
    serializer_class = AditivoContratoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.aditivo.edit"}
    action_permission_map = {
        "abrir": "pdca.aditivo.edit",
        "itens": "pdca.aditivo.edit",
        "submeter": "pdca.aditivo.edit",
        "cancelar": "pdca.aditivo.edit",
        "atestar": "pdca.aditivo.aprovar",
    }
    filterset_fields = ["contrato", "status", "contrato__obra"]
    search_fields = ["objeto", "justificativa", "contrato__numero"]
    ordering_fields = ["numero", "criado_em"]

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        """Abre o aditivo em rascunho. Não move saldo nenhum ainda."""
        entrada = AbrirAditivoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        contrato = _meu_contrato(request, dados["contrato"])
        try:
            aditivo = services.criar_aditivo(
                contrato=contrato,
                objeto=dados["objeto"],
                justificativa=dados["justificativa"],
                data_assinatura=dados.get("data_assinatura"),
                nova_data_fim=dados.get("nova_data_fim"),
                por=_quem_e(request),
                itens=[dict(linha) for linha in dados.get("itens", [])],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            self.get_serializer(aditivo).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def itens(self, request, pk=None):
        """Reescreve as linhas do rascunho — substitui, não soma."""
        aditivo = self.get_object()
        entrada = LinhaDeAditivoSerializer(
            data=request.data.get("itens", []), many=True,
        )
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reescrever_itens_do_aditivo(
                aditivo=aditivo, itens=[dict(linha) for linha in entrada.validated_data],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"itens": erro.messages})
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def submeter(self, request, pk=None):
        """Rascunho → escada (ou aprovação em um passo, sem fluxo configurado).

        Sem escada, submeter **aprova e aplica** — e por isso exige
        `pdca.aditivo.aprovar`, não o `edit` que montou o documento. É a mesma
        conferência que a medição faz, pela mesma razão.
        """
        from nucleo import aprovacao as motor

        aditivo = self.get_object()
        if motor.fluxo_para(aditivo, tenant_id=aditivo.tenant_id) is None:
            _exige(request, "pdca.aditivo.aprovar", (
                "Esta empresa não tem escada de aprovação configurada para "
                "aditivo, então submeter aprovaria em um passo — e aprovar exige "
                "'pdca.aditivo.aprovar', que você não tem. Peça ao administrador "
                "do tenant que monte o fluxo em /api/aprovacao/fluxos/ (alvo "
                "'modulopdca.aditivocontrato')."
            ))
        try:
            resultado = services.submeter_aditivo(
                aditivo=aditivo, solicitante=request.user,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        aditivo.refresh_from_db()
        return Response(_str_decimais({
            "estado": resultado["estado"],
            "escada": resultado["escada"],
            "avisos": resultado["avisos"],
            "aditivo": self.get_serializer(aditivo).data,
        }))

    @action(detail=True, methods=["post"])
    def atestar(self, request, pk=None):
        """Um degrau da escada, decidido de dentro da tela do aditivo."""
        from nucleo import aprovacao as motor

        aditivo = self.get_object()
        entrada = AtestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        pedido = motor.pedido_de(aditivo)
        if pedido is None:
            raise ValidationError({
                "detail": (
                    "Este aditivo não está em nenhuma escada de aprovação "
                    f"(status: {aditivo.get_status_display().lower()})."
                ),
            })
        try:
            pedido = motor.decidir(
                pedido=pedido, usuario=request.user,
                aprovar=entrada.validated_data["aprovar"],
                observacao=entrada.validated_data.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        aditivo.refresh_from_db()
        return Response({
            "estado_do_pedido": pedido.estado,
            "nivel_atual": getattr(pedido.nivel_atual, "nome", None),
            "aditivo": self.get_serializer(aditivo).data,
        })

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Retira o aditivo sem decidir o mérito."""
        from nucleo import aprovacao as motor

        aditivo = self.get_object()
        if aditivo.esta_congelado:
            raise ValidationError({
                "detail": (
                    f"O aditivo já está {aditivo.get_status_display().lower()} e "
                    f"não se cancela."
                ),
            })
        pedido = motor.pedido_de(aditivo)
        if pedido is not None:
            try:
                motor.cancelar(
                    pedido=pedido, usuario=request.user,
                    motivo=request.data.get("motivo", ""),
                )
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        aditivo.status = AditivoContrato.Status.CANCELADO
        aditivo.save(update_fields=["status"])
        return Response(self.get_serializer(aditivo).data)

    def perform_destroy(self, instance):
        if instance.status != AditivoContrato.Status.RASCUNHO:
            raise ValidationError({
                "detail": (
                    f"O aditivo está {instance.get_status_display().lower()} e não "
                    f"vai para a lixeira — documento com decisão registrada fica."
                ),
            })
        super().perform_destroy(instance)


class LiberacaoRetencaoViewSet(TenantScopedViewSetMixin,
                               mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    """Leitura das liberações. **Criar é pelo contrato** (`liberar-retencao/`),
    porque o teto é o saldo retido daquele contrato — e um `POST` solto aqui
    convidaria a criar a linha sem passar pela conferência do saldo."""

    queryset = LiberacaoRetencao.objects.select_related(
        "contrato", "contrato__fornecedor",
    )
    serializer_class = LiberacaoRetencaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.medicao.atestar"}
    filterset_fields = ["contrato", "status"]
    search_fields = ["condicao_atendida", "solicitada_por"]
    ordering_fields = ["data", "valor"]


def _str_decimais(dados):
    """`Decimal` vira string no JSON, recursivamente.

    O `float` do JSON tem 53 bits de mantissa e **não representa centavo
    exatamente** — é a razão de o DRF serializar `DecimalField` como string por
    padrão. Estes endpoints devolvem dicionários montados à mão, fora de um
    serializer, e sem esta passada o dinheiro sairia como float: R$ 1.234,57
    viraria 1234.5699999999999 na tela do gestor.
    """
    from decimal import Decimal as _D

    if isinstance(dados, _D):
        return str(dados)
    if isinstance(dados, dict):
        return {chave: _str_decimais(valor) for chave, valor in dados.items()}
    if isinstance(dados, (list, tuple)):
        return [_str_decimais(valor) for valor in dados]
    return dados
