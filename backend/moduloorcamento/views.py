# backend/moduloorcamento/views.py
"""API da base referencial — **read-only** por desenho.

A base é catálogo público de plataforma, gravado só por
`manage.py importar_base_referencial` (ver `models.py`). Então aqui não existe
`ModelViewSet`: quem tenta `POST`/`PUT`/`DELETE` numa publicação recebe 405, não
403 — a operação não existe, não é questão de permissão.

O único verbo de escrita do módulo nesta fatia é **adotar**, e ele não escreve na
base: escreve no `catalogo.Item` **do tenant**. Por isso exige permissão própria
(`orcamento.base.adotar`) e não o `.edit` do recurso.
"""
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import (
    exceptions,
    filters,
    permissions,
    serializers,
    status,
    views,
    viewsets,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogo.models import Item
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.quotas import QuotaEnforcedMixin
from nucleo.tenancy import TenantScopedViewSetMixin

from . import (
    bancos as servico_bancos,
    controle,
    duplicacao,
    exportacao,
    nbr12721,
    planilha,
    precificacao,
    reprecificacao as servico_reprecificacao,
    services,
)
from .models import (
    BancoPreco,
    BaseReferencial,
    ComponenteBancoPreco,
    ComposicaoBDI,
    ComposicaoReferenciaItem,
    InsumoReferencia,
    ItemBancoPreco,
    ItemOrcado,
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
from .pagination import OrcamentoPageNumberPagination
from .serializers import (
    BancoPrecoSerializer,
    BaseReferencialSerializer,
    ComponenteBancoPrecoSerializer,
    ComposicaoBDISerializer,
    ComposicaoReferenciaItemSerializer,
    InsumoReferenciaSerializer,
    ItemBancoPrecoSerializer,
    ItemOrcadoSerializer,
    LinhaReprecificacaoSerializer,
    MemorialNBRSerializer,
    OrcamentoSerializer,
    ParametroObraSerializer,
    ParcelaEtapaSerializer,
    PastaComposicaoSerializer,
    PavimentoObraSerializer,
    ReprecificacaoSerializer,
    RevisaoOrcamentoSerializer,
    UnidadeAutonomaSerializer,
)

MODULO = "orcamento"


class OrcamentoStatusView(views.APIView):
    """Status do módulo. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = MODULO

    def get(self, request):
        publicacoes = BaseReferencial.objects.filter(ativa=True).count()
        return Response({"modulo": MODULO, "status": "ativo", "bases_referenciais": publicacoes})


class _OrcamentoPermsMixin:
    """Entitlement do módulo + permissão de campo, na mesma ordem dos outros
    módulos pagos (SCM/SIL): sem assinar → 403; assinando sem permissão → 403."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    pagination_class = OrcamentoPageNumberPagination

    def _tenant_id(self):
        return getattr(getattr(self.request, "user", None), "tenant_id", None)


class BaseReferencialViewSet(_OrcamentoPermsMixin, viewsets.ReadOnlyModelViewSet):
    """As publicações disponíveis (SINAPI SP 07/2026 desonerado, ORSE SE 07/2026…)."""

    queryset = BaseReferencial.objects.all()
    serializer_class = BaseReferencialSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["fonte", "uf", "regime_encargos", "ativa"]
    ordering_fields = ["mes_referencia", "fonte", "uf"]
    # `required_permission` (fixa), NÃO `required_resource`: o atalho do recurso
    # derivaria `orcamento.base.edit` no método de escrita — uma permissão que
    # **não existe no catálogo**, porque a base não é editável por ninguém. O
    # efeito seria um 403 mentiroso ("falta permissão") no lugar do 405 correto
    # ("esta operação não existe aqui").
    required_permission = "orcamento.base.view"


class InsumoReferenciaViewSet(_OrcamentoPermsMixin, viewsets.ReadOnlyModelViewSet):
    """Insumos e composições de uma publicação, com busca server-side.

    A busca é o modo de uso real: ninguém navega 80 mil linhas — digita "concreto
    fck 25" e adota o que serve.
    """

    queryset = InsumoReferencia.objects.select_related("base").all()
    serializer_class = InsumoReferenciaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["base", "tipo", "unidade"]
    search_fields = ["codigo", "descricao", "grupo"]
    ordering_fields = ["codigo", "descricao", "custo_unitario"]
    required_permission = "orcamento.base.view"  # ver nota em BaseReferencialViewSet
    action_permission_map = {
        "adotar": "orcamento.base.adotar",
        "adotar_lote": "orcamento.base.adotar",
    }

    def get_serializer_context(self):
        """Marca o que já está adotado no catálogo da empresa — um SELECT por
        página, para a lista não perguntar linha por linha."""
        contexto = super().get_serializer_context()
        pagina = getattr(self, "_pagina_atual", None)
        if not pagina:
            return contexto
        codigos = {obj.codigo for obj in pagina}
        fontes = {obj.base.fonte for obj in pagina}
        adotados = Item.objects.filter(
            tenant_id=self._tenant_id(),
            fonte_referencia__in=fontes,
            codigo_referencia__in=codigos,
        ).values_list("fonte_referencia", "codigo_referencia", "item_id")
        contexto["adotados"] = {(f, c): i for f, c, i in adotados}
        return contexto

    def paginate_queryset(self, queryset):
        pagina = super().paginate_queryset(queryset)
        self._pagina_atual = pagina
        return pagina

    def retrieve(self, request, *args, **kwargs):
        self._pagina_atual = [self.get_object()]
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="composicao")
    def composicao(self, request, pk=None):
        """A analítica da composição: insumos, coeficientes e a parcela de cada um."""
        referencia = self.get_object()
        componentes = (
            ComposicaoReferenciaItem.objects.filter(composicao=referencia)
            .select_related("filho")
            .order_by("componente_id")
        )
        return Response({
            "composicao": InsumoReferenciaSerializer(referencia, context=self.get_serializer_context()).data,
            "componentes": ComposicaoReferenciaItemSerializer(componentes, many=True).data,
        })

    @action(detail=True, methods=["post"], url_path="adotar")
    def adotar(self, request, pk=None):
        """Traz o item da base para o catálogo da empresa (idempotente)."""
        referencia = self.get_object()
        recursivo = request.data.get("recursivo", True) not in (False, "false", "0", 0)
        try:
            item = services.adotar_no_catalogo(referencia, self._tenant_id(), recursivo=recursivo)
        except services.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "item_id": item.item_id,
                "codigo_interno": item.codigo_interno,
                "descricao": item.descricao,
                "tipo": item.tipo,
                "componentes": item.componentes.count(),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="adotar-lote")
    def adotar_lote(self, request):
        """Adota a seleção da busca de uma vez (`{"referencias": [1, 2, 3]}`)."""
        ids = request.data.get("referencias") or []
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "Informe 'referencias' com ao menos um id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referencias = list(
            InsumoReferencia.objects.filter(pk__in=ids).select_related("base")
        )
        if not referencias:
            return Response({"detail": "Nenhuma referência encontrada."}, status=status.HTTP_404_NOT_FOUND)
        try:
            itens = services.adotar_muitos(referencias, self._tenant_id())
        except services.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "adotados": len(itens),
                "itens": [
                    {"item_id": i.item_id, "codigo_interno": i.codigo_interno, "descricao": i.descricao}
                    for i in itens
                ],
            },
            status=status.HTTP_201_CREATED,
        )


class BaseReferencialResumoView(views.APIView):
    """Resumo por publicação para o seletor de base-de-preço da planilha:
    o que existe, de quando é e quanto a empresa já adotou de cada uma."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    required_permission = "orcamento.base.view"

    def get(self, request):
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        bases = (
            BaseReferencial.objects.filter(ativa=True)
            .annotate(
                insumos=Count("itens", filter=Q(itens__tipo=InsumoReferencia.Tipo.INSUMO)),
                composicoes=Count("itens", filter=Q(itens__tipo=InsumoReferencia.Tipo.COMPOSICAO)),
            )
            .order_by("-mes_referencia", "fonte")
        )
        adotados_por_fonte = dict(
            Item.objects.filter(tenant_id=tenant_id)
            .exclude(codigo_referencia="")
            .values_list("fonte_referencia")
            .annotate(total=Count("item_id"))
        )
        return Response([
            {
                "base_id": b.base_id,
                "rotulo": b.rotulo or b.rotulo_automatico(),
                "fonte": b.fonte,
                "uf": b.uf,
                "mes_referencia": b.mes_referencia,
                "regime_encargos": b.regime_encargos,
                "insumos": b.insumos,
                "composicoes": b.composicoes,
                "adotados_no_catalogo": adotados_por_fonte.get(b.fonte, 0),
            }
            for b in bases
        ])


# ---------------------------------------------------------------------------
# ORC.1 — planilha orçamentária
# ---------------------------------------------------------------------------


class _PeriodoSerializer(serializers.Serializer):
    """Entrada da distribuição do cronograma. Serializer em vez de leitura crua
    do `request.data` para a data inválida virar 400 com mensagem de campo."""

    inicio = serializers.DateField()
    fim = serializers.DateField()
    etapa = serializers.IntegerField(required=False, allow_null=True)


class DocumentoFechado(exceptions.APIException):
    """**409**, não 403: não falta permissão, o documento é que não está aberto.

    A distinção importa para a tela — 403 manda o usuário procurar o admin, 409
    manda ele criar uma revisão, que é o caminho real.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Orçamento não editável."
    default_code = "documento_fechado"


def _exigir_editavel(orcamento) -> None:
    """Ponte entre a exceção de domínio e o vocabulário HTTP."""
    try:
        planilha.exigir_editavel(orcamento)
    except planilha.OrcamentoNaoEditavel as exc:
        raise DocumentoFechado(str(exc)) from exc


class OrcamentoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """A planilha: CRUD + os verbos que mudam o **estado** da régua de custo.

    `aprovar` e `revisar` são permissões próprias (`orcamento.orcamento.aprovar`
    /`.revisar`), não o `.edit` do recurso: congelar o custo de uma obra é
    decisão de quem responde por ela, e quem digita a planilha (persona
    `orcamentista`) não é necessariamente quem assina embaixo.
    """

    queryset = Orcamento.objects.select_related("obra", "base_referencial").all()
    serializer_class = OrcamentoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["obra", "status", "versao", "base_referencial"]
    search_fields = ["descricao", "obra__nome_obra"]
    ordering_fields = ["criado_em", "valor_total", "versao"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {
        "aprovar": "orcamento.orcamento.aprovar",
        "revisar": "orcamento.orcamento.revisar",
        "recalcular": "orcamento.orcamento.edit",
        "arvore": "orcamento.orcamento.view",
        # Relatórios de controle sob `relatorio.view`; mexer no cronograma é
        # editar o orçamento. Os dois reusam as 9 permissões do catálogo em vez
        # de criar `orcamento.cronograma.*` — permissão nova exige rebuild da
        # imagem da IAM + re-seed, e o recorte aqui não pedia granularidade nova.
        "curva_abc": "orcamento.relatorio.view",
        "por_categoria": "orcamento.relatorio.view",
        "cronograma": "orcamento.relatorio.view",
        "curva_s": "orcamento.relatorio.view",
        "distribuir_cronograma": "orcamento.orcamento.edit",
        # ORC.5b. Duplicar cria planilha nova → `.edit`; reprecificar mexe no
        # preço da régua, também `.edit`. Exportar é leitura de relatório.
        # Nenhuma permissão nova: ver §12.1 da planta — permissão nova exige
        # rebuild da imagem da IAM + re-seed, e o recorte aqui não pediu.
        "duplicar": "orcamento.orcamento.edit",
        "copiar_itens": "orcamento.orcamento.edit",
        "reprecificar": "orcamento.orcamento.edit",
        "reprecificacoes": "orcamento.orcamento.view",
        "exportar": "orcamento.relatorio.view",
    }

    def perform_update(self, serializer):
        _exigir_editavel(self.get_object())
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        """Aprovado não se apaga — é a régua contra a qual medições já foram
        feitas. Cancele (ou revise) em vez de apagar."""
        _exigir_editavel(instance)
        instance.delete()

    @action(detail=True, methods=["get"], url_path="arvore")
    def arvore(self, request, pk=None):
        """A planilha inteira numa resposta, já ordenada pela EAP.

        A tela de orçamento é uma árvore que se lê de cima a baixo; paginar
        linha a linha quebraria a hierarquia (um filho poderia cair numa página
        sem o pai). Quem precisa de fatia usa o `itens/` filtrado.
        """
        orcamento = self.get_object()
        itens = (
            ItemOrcado.objects.filter(orcamento=orcamento)
            .select_related("etapa", "item")
            .order_by("codigo_eap", "ordem", "item_orcado_id")
        )
        return Response({
            "orcamento": self.get_serializer(orcamento).data,
            "itens": ItemOrcadoSerializer(itens, many=True).data,
        })

    @action(detail=True, methods=["post"], url_path="recalcular")
    def recalcular(self, request, pk=None):
        """Renumera a EAP e refaz os totais de baixo para cima."""
        orcamento = self.get_object()
        planilha.recalcular_orcamento(orcamento)
        orcamento.refresh_from_db()
        return Response(self.get_serializer(orcamento).data)

    @action(detail=True, methods=["post"], url_path="aprovar")
    def aprovar(self, request, pk=None):
        orcamento = self.get_object()
        try:
            planilha.aprovar_orcamento(
                orcamento, usuario_nome=self._nome_do_usuario(request)
            )
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        orcamento.refresh_from_db()
        return Response(self.get_serializer(orcamento).data)

    @action(detail=True, methods=["get"], url_path="por-categoria")
    def por_categoria(self, request, pk=None):
        """Custo direto por natureza de insumo (material × mão de obra × equipamento).

        Só vê linha explodida, então a resposta carrega a `cobertura_pct` — a
        tela mostra o gráfico e diz de quanto da planilha ele fala.
        """
        return Response(precificacao.custo_por_categoria(self.get_object()))

    @action(detail=True, methods=["get"], url_path="curva-abc")
    def curva_abc(self, request, pk=None):
        """Onde está o dinheiro do orçamento — ~20% dos itens, ~80% do custo.

        Mesma leitura que o SIL faz do estoque, agora do lado do planejado: as
        duas telas usam a mesma convenção de classe, então A no orçado e A no
        aplicado querem dizer a mesma coisa.
        """
        return Response(precificacao.curva_abc(self.get_object()))

    # --- ORC.3: cronograma e curva S ---

    @action(detail=True, methods=["get"], url_path="cronograma")
    def cronograma(self, request, pk=None):
        """A grade do cronograma físico-financeiro + conferência dos 100%."""
        orcamento = self.get_object()
        dados = controle.cronograma(orcamento)
        dados["validacao"] = controle.validar_cronograma(orcamento)
        return Response(dados)

    @action(detail=True, methods=["post"], url_path="distribuir-cronograma")
    def distribuir_cronograma(self, request, pk=None):
        """Gera o cronograma linear de partida entre duas competências.

        Ponto de partida editável, não verdade — é assim que as ferramentas do
        mercado funcionam: gera-se o linear e o planejador ajusta.
        """
        orcamento = self.get_object()
        _exigir_editavel(orcamento)
        serializer = _PeriodoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        etapa_id = serializer.validated_data.get("etapa")

        etapa = None
        if etapa_id:
            etapa = ParcelaEtapa.etapa.field.related_model.objects.filter(
                tenant_id=self._tenant_id(), pk=etapa_id, obra_id=orcamento.obra_id
            ).first()
            if etapa is None:
                return Response(
                    {"etapa": "Etapa não encontrada nesta obra."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        try:
            controle.distribuir_linear(
                orcamento, inicio=serializer.validated_data["inicio"],
                fim=serializer.validated_data["fim"], etapa=etapa,
            )
        except controle.CronogramaInvalido as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(controle.cronograma(orcamento), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="curva-s")
    def curva_s(self, request, pk=None):
        """Previsto acumulado × realizado acumulado, mês a mês."""
        return Response(controle.curva_s(self.get_object()))

    @action(detail=True, methods=["post"], url_path="revisar")
    def revisar(self, request, pk=None):
        """Gera a versão seguinte a partir da aprovada (aditivo/supressão)."""
        orcamento = self.get_object()
        tipo = request.data.get("tipo") or RevisaoOrcamento.Tipo.ADITIVO
        motivo = (request.data.get("motivo") or "").strip()
        if not motivo:
            return Response(
                {"motivo": "Informe o motivo da revisão — é o que justifica o aditivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tipo not in RevisaoOrcamento.Tipo.values:
            return Response({"tipo": f"Tipo inválido. Use um de {RevisaoOrcamento.Tipo.values}."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            nova = planilha.revisar_orcamento(
                orcamento, tipo=tipo, motivo=motivo,
                usuario_nome=self._nome_do_usuario(request),
            )
        except planilha.RevisaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(nova).data, status=status.HTTP_201_CREATED)

    # --- ORC.5b: duplicar, copiar, reprecificar, exportar ---

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, pk=None):
        """Clona a planilha para outra obra (ou a mesma), em rascunho v-nova.

        Não é `revisar`: não rebaixa a origem nem registra aditivo. Reaproveitar
        obra parecida é o caso mais comum de partida numa construtora.
        """
        origem = self.get_object()
        obra_id = request.data.get("obra")
        obra = None
        if obra_id:
            obra = origem.obra.__class__.objects.filter(
                tenant_id=self._tenant_id(), pk=obra_id
            ).first()
            if obra is None:
                return Response({"obra": "Obra não encontrada."}, status=status.HTTP_404_NOT_FOUND)

        novo, sem_etapa = duplicacao.duplicar_orcamento(
            origem, obra_destino=obra,
            descricao=(request.data.get("descricao") or "").strip(),
            usuario_nome=self._nome_do_usuario(request),
        )
        return Response(
            duplicacao.resumo_da_duplicata(novo, sem_etapa), status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="copiar-itens")
    def copiar_itens(self, request, pk=None):
        """Traz um bloco de linhas de outro orçamento para dentro deste."""
        destino = self.get_object()
        ids = request.data.get("itens") or []
        if not isinstance(ids, list) or not ids:
            return Response(
                {"itens": "Informe a lista de linhas a copiar."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        itens = list(
            ItemOrcado.objects.filter(tenant_id=self._tenant_id(), pk__in=ids)
            .select_related("orcamento")
        )
        if not itens:
            return Response({"itens": "Nenhuma linha encontrada."}, status=status.HTTP_404_NOT_FOUND)

        pai = None
        if request.data.get("pai"):
            pai = ItemOrcado.objects.filter(
                tenant_id=self._tenant_id(), pk=request.data["pai"], orcamento=destino
            ).first()

        try:
            copiadas, sem_etapa = duplicacao.copiar_itens(destino=destino, itens=itens, pai=pai)
        except duplicacao.CopiaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        destino.refresh_from_db()
        return Response({
            "copiadas": copiadas,
            "linhas_sem_etapa": sem_etapa,
            "valor_total": str(destino.valor_total),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="reprecificar")
    def reprecificar(self, request, pk=None):
        """Monta a **prévia** de troca de data-base. Não altera nada ainda."""
        orcamento = self.get_object()
        base = banco = None
        if request.data.get("base_destino"):
            base = BaseReferencial.objects.filter(pk=request.data["base_destino"]).first()
            if base is None:
                return Response({"base_destino": "Publicação não encontrada."}, status=404)
        if request.data.get("banco_destino"):
            banco = BancoPreco.objects.filter(
                tenant_id=self._tenant_id(), pk=request.data["banco_destino"]
            ).first()
            if banco is None:
                return Response({"banco_destino": "Banco não encontrado."}, status=404)

        try:
            lote = servico_reprecificacao.gerar_previa(
                orcamento, base_destino=base, banco_destino=banco,
                somente_ate=request.data.get("somente_ate") or None,
                usuario_nome=self._nome_do_usuario(request),
            )
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except servico_reprecificacao.ReprecificacaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(servico_reprecificacao.serializar_previa(lote))

    @action(detail=True, methods=["get"], url_path="reprecificacoes")
    def reprecificacoes(self, request, pk=None):
        """Histórico de lotes deste orçamento — é aqui que mora o desfazer."""
        lotes = Reprecificacao.objects.filter(orcamento=self.get_object()).order_by("-criado_em")
        return Response(ReprecificacaoSerializer(lotes, many=True).data)

    @action(detail=True, methods=["get"], url_path="exportar")
    def exportar(self, request, pk=None):
        """XLSX ou PDF da planilha, sintética ou analítica.

        `?formato=xlsx|pdf&nivel=analitico|sintetico&peca=planilha|curva-abc|cronograma`
        """
        orcamento = self.get_object()
        formato = (request.query_params.get("formato") or "xlsx").lower()
        analitico = (request.query_params.get("nivel") or "analitico").lower() != "sintetico"
        peca = (request.query_params.get("peca") or "planilha").lower()

        try:
            if peca == "curva-abc":
                conteudo = exportacao.curva_abc_xlsx(orcamento, precificacao.curva_abc(orcamento))
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="curva-abc", extensao="xlsx")
                tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif peca == "cronograma":
                dados = controle.cronograma(orcamento)
                conteudo = exportacao.cronograma_xlsx(orcamento, dados)
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="cronograma", extensao="xlsx")
                tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif formato == "pdf":
                conteudo = exportacao.planilha_pdf(orcamento, analitico=analitico)
                nome = exportacao.nome_do_arquivo(
                    orcamento, sufixo="analitica" if analitico else "sintetica", extensao="pdf",
                )
                tipo = "application/pdf"
            else:
                conteudo = exportacao.planilha_xlsx(orcamento, analitico=analitico)
                nome = exportacao.nome_do_arquivo(
                    orcamento, sufixo="analitica" if analitico else "sintetica", extensao="xlsx",
                )
                tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except exportacao.ExportacaoIndisponivel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_501_NOT_IMPLEMENTED)

        from django.http import HttpResponse

        resposta = HttpResponse(conteudo, content_type=tipo)
        resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return resposta

    @staticmethod
    def _nome_do_usuario(request) -> str:
        user = getattr(request, "user", None)
        return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""


class ItemOrcadoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As linhas da planilha.

    Toda escrita recalcula o orçamento — a alternativa (recalcular só quando o
    usuário pedir) deixaria a planilha exibindo um total que não corresponde às
    linhas, que é o pior defeito possível num sistema de orçamento.
    """

    queryset = ItemOrcado.objects.select_related("orcamento", "etapa", "item").all()
    serializer_class = ItemOrcadoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["orcamento", "pai", "etapa", "item", "tipo_linha"]
    search_fields = ["descricao", "codigo_referencia", "codigo_eap"]
    ordering_fields = ["codigo_eap", "ordem", "total_custo_direto"]
    required_resource = "orcamento.item"
    action_permission_map = {
        "memoria": "orcamento.item.view",
        "preco_real": "orcamento.item.view",
        "explodir": "orcamento.item.edit",
        "aplicar_preco_real": "orcamento.item.edit",
        "do_catalogo": "orcamento.item.edit",
    }

    def perform_create(self, serializer):
        # `super()` é quem injeta o `tenant_id` (TenantScopedViewSetMixin) —
        # salvar direto aqui gravaria a linha sem tenant e a RLS a rejeitaria.
        _exigir_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        planilha.recalcular_orcamento(serializer.instance.orcamento)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        planilha.recalcular_orcamento(serializer.instance.orcamento)

    def perform_destroy(self, instance):
        orcamento = instance.orcamento
        _exigir_editavel(orcamento)
        instance.delete()
        planilha.recalcular_orcamento(orcamento)

    @action(detail=False, methods=["post"], url_path="do-catalogo")
    def do_catalogo(self, request):
        """Cria a linha a partir de um `catalogo.Item`, **tirando o snapshot**.

        É o caminho normal de montar planilha: escolher o item do catálogo (que
        veio da SINAPI pela adoção, ou é próprio da empresa) e informar a
        quantidade. Descrição, unidade e código de referência são copiados
        agora e congelam aqui — mudar o item no catálogo depois não mexe neste
        orçamento.

        O preço vem da base referencial quando o item foi adotado dela; senão o
        cliente informa. Nunca inventamos preço: sem preço conhecido a linha
        nasce zerada e visível como pendência, em vez de com um número plausível.
        """
        orcamento_id = request.data.get("orcamento")
        item_id = request.data.get("item")
        orcamento = Orcamento.objects.filter(
            tenant_id=self._tenant_id(), pk=orcamento_id
        ).select_related("base_referencial").first()
        if orcamento is None:
            return Response({"orcamento": "Orçamento não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        _exigir_editavel(orcamento)

        item = Item.objects.filter(tenant_id=self._tenant_id(), pk=item_id).first()
        if item is None:
            return Response({"item": "Item não encontrado no catálogo."}, status=status.HTTP_404_NOT_FOUND)

        linha = services.linha_a_partir_do_item(
            orcamento=orcamento,
            item=item,
            quantidade=request.data.get("quantidade") or 0,
            custo_unitario=request.data.get("custo_unitario"),
            pai_id=request.data.get("pai"),
            etapa_id=request.data.get("etapa"),
            ordem=request.data.get("ordem") or 0,
        )
        planilha.recalcular_orcamento(orcamento)
        linha.refresh_from_db()
        return Response(ItemOrcadoSerializer(linha).data, status=status.HTTP_201_CREATED)

    # --- ORC.2: composição analítica ---

    @action(detail=True, methods=["post"], url_path="explodir")
    def explodir(self, request, pk=None):
        """Abre a composição do item em insumos e refaz o custo unitário.

        Depois disto o preço da linha deixa de ser digitado e passa a ser a
        soma dos insumos — é o que torna o orçamento auditável.
        """
        linha = self.get_object()
        _exigir_editavel(linha.orcamento)
        atualizar = request.data.get("atualizar_custo", True) not in (False, "false", "0", 0)
        try:
            precificacao.explodir_item(linha, atualizar_custo=atualizar)
        except precificacao.ComposicaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        planilha.recalcular_orcamento(linha.orcamento)
        linha.refresh_from_db()
        return Response(precificacao.memoria_de_calculo(linha))

    @action(detail=True, methods=["get"], url_path="memoria")
    def memoria(self, request, pk=None):
        """A memória de cálculo da linha: insumos, pesos e resumo por categoria."""
        return Response(precificacao.memoria_de_calculo(self.get_object()))

    @action(detail=True, methods=["get"], url_path="preco-real")
    def preco_real(self, request, pk=None):
        """Preço de tabela × o que a empresa pagou (SCM) × o que carrega (SIL).

        A integração fica visível aqui: a mesma tela que orça mostra o histórico
        real dos outros dois módulos, porque o item é o mesmo `catalogo.Item`.
        """
        linha = self.get_object()
        if linha.item_id is None:
            return Response(
                {"detail": "A linha não aponta item do catálogo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dados = precificacao.preco_real_do_item(self._tenant_id(), linha.item_id)
        dados["orcado"] = {
            "custo_unitario": str(linha.custo_unitario),
            "fonte": linha.fonte_referencia or "propria",
            "data_base": linha.data_base_preco,
        }
        return Response(dados)

    @action(detail=True, methods=["post"], url_path="aplicar-preco-real")
    def aplicar_preco_real(self, request, pk=None):
        """Troca o preço de tabela pelo histórico real (`origem`: scm | sil)."""
        linha = self.get_object()
        _exigir_editavel(linha.orcamento)
        origem = request.data.get("origem") or "scm"
        if origem not in ("scm", "sil"):
            return Response({"origem": "Use 'scm' ou 'sil'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            precificacao.aplicar_preco_real(linha, origem=origem)
        except precificacao.ComposicaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        planilha.recalcular_orcamento(linha.orcamento)
        linha.refresh_from_db()
        return Response(ItemOrcadoSerializer(linha).data)


class ComposicaoBDIViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """BDI analítico (Acórdão 2622/2013-TCU).

    Toda escrita passa por `precificacao.salvar_bdi`, que recalcula o
    percentual, garante um único `padrao` por orçamento e propaga o número para
    o cabeçalho — o percentual jamais é aceito do cliente.
    """

    queryset = ComposicaoBDI.objects.select_related("orcamento").all()
    serializer_class = ComposicaoBDISerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "padrao"]
    required_resource = "orcamento.orcamento"

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        self._salvar(serializer.instance)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        self._salvar(serializer.instance)

    @staticmethod
    def _salvar(composicao):
        try:
            precificacao.salvar_bdi(composicao)
        except precificacao.ComposicaoInvalida as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        planilha.recalcular_orcamento(composicao.orcamento)


class ParcelaEtapaViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Células do cronograma — edição fina depois da distribuição linear.

    Cada escrita reconverte percentuais em dinheiro. Não travamos a soma em
    100%: um cronograma em construção passa por estados inconsistentes, e a
    conferência é informada em `cronograma/`, não imposta na digitação.
    """

    queryset = ParcelaEtapa.objects.select_related("orcamento", "etapa").all()
    serializer_class = ParcelaEtapaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "etapa", "competencia"]
    ordering_fields = ["competencia", "percentual"]
    required_resource = "orcamento.item"

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        controle.recalcular_parcelas(serializer.instance.orcamento)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        controle.recalcular_parcelas(serializer.instance.orcamento)

    def perform_destroy(self, instance):
        orcamento = instance.orcamento
        _exigir_editavel(orcamento)
        instance.delete()
        controle.recalcular_parcelas(orcamento)


class ControleDeCustoView(views.APIView):
    """As quatro colunas: orçado × comprometido × aplicado × realizado.

    O cockpit do módulo — e o lugar onde a integração entre SCM, SIL, ERP e
    Orçamento aparece num número só. `?obra=` filtra uma obra.
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    required_permission = "orcamento.relatorio.view"

    def get(self, request):
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        obra = request.query_params.get("obra")
        linhas = controle.quatro_colunas(tenant_id, obra or None)
        return Response({
            "obras": linhas,
            # A tela precisa saber o que a coluna cobre para não apresentar um
            # número parcial como total — ver a nota em controle.py.
            "nota_realizado": (
                "Realizado cobre despesa originada de pedido de compra (SCM → ERP). "
                "Lançamento feito direto no ERP ainda não tem dimensão de obra."
            ),
        })


# ---------------------------------------------------------------------------
# ORC.4 — paramétrico e NBR 12721
# ---------------------------------------------------------------------------


class ParametroObraViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Orçamento paramétrico da viabilidade (área equivalente × CUB)."""

    queryset = ParametroObra.objects.select_related("obra").all()
    serializer_class = ParametroObraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["obra", "projeto_padrao"]
    ordering_fields = ["criado_em", "custo_estimado"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {"comparar": "orcamento.relatorio.view"}

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._calcular(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._calcular(serializer.instance)

    def _calcular(self, parametro):
        sincronizar = self.request.data.get("sincronizar_area", False) in (True, "true", "1", 1)
        nbr12721.calcular_parametrico(parametro, sincronizar_area=sincronizar)

    @action(detail=True, methods=["get"], url_path="comparar")
    def comparar(self, request, pk=None):
        """Paramétrico × analítico aprovado — o que calibra a próxima estimativa."""
        return Response(nbr12721.comparar_parametrico_com_analitico(self.get_object()))


class PavimentoObraViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Pavimentos e suas áreas — a base do Quadro I."""

    queryset = PavimentoObra.objects.select_related("obra").all()
    serializer_class = PavimentoObraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["obra"]
    ordering_fields = ["ordem", "nome"]
    required_resource = "orcamento.item"


class UnidadeAutonomaViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Unidades autônomas — base dos Quadros II e IV."""

    queryset = UnidadeAutonoma.objects.select_related("obra", "pavimento").all()
    serializer_class = UnidadeAutonomaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["obra", "pavimento", "tipo"]
    search_fields = ["designacao", "tipo"]
    ordering_fields = ["designacao", "coeficiente_proporcionalidade"]
    required_resource = "orcamento.item"


class MemorialNBRViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Linhas dos quadros descritivos V a VIII."""

    queryset = MemorialNBR.objects.select_related("obra").all()
    serializer_class = MemorialNBRSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["obra", "quadro"]
    search_fields = ["dependencia", "descricao"]
    ordering_fields = ["quadro", "ordem"]
    required_resource = "orcamento.item"


class QuadrosNBRView(views.APIView):
    """Os oito quadros da NBR 12721 de uma obra — o dossiê de incorporação.

    `GET /api/orcamento/nbr12721/?obra=<id>[&quadro=I|II|III|IV|v|vi|vii|viii]`
    `POST …/?obra=<id>` com `{"acao": "coeficientes"|"ratear"}` recalcula.

    Uma `APIView` e não um ViewSet porque isto não é um recurso CRUD: é uma
    **leitura composta** sobre pavimentos, unidades e a base de custo. Os
    recursos que a alimentam têm seus próprios endpoints.
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    # Chaves do contrato do `RequirePermission`: "view" p/ métodos seguros,
    # "write" para os demais.
    permission_map = {"view": "orcamento.relatorio.view", "write": "orcamento.item.edit"}

    def _obra(self, request):
        obra = request.query_params.get("obra") or request.data.get("obra")
        if not obra:
            raise exceptions.ValidationError({"obra": "Informe a obra."})
        return obra

    @staticmethod
    def _tenant(request):
        return getattr(getattr(request, "user", None), "tenant_id", None)

    def _parametro(self, tenant_id, obra_id):
        """Paramétrico mais recente da obra — base de custo quando não há
        planilha analítica aprovada."""
        return (
            ParametroObra.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
            .order_by("-criado_em").first()
        )

    def get(self, request):
        tenant_id, obra_id = self._tenant(request), self._obra(request)
        parametro = self._parametro(tenant_id, obra_id)
        quadro = (request.query_params.get("quadro") or "").strip()

        try:
            if not quadro:
                return Response(nbr12721.dossie(tenant_id, obra_id, parametro=parametro))
            if quadro == "I":
                return Response(nbr12721.quadro_i(tenant_id, obra_id))
            if quadro == "II":
                return Response(nbr12721.quadro_ii(tenant_id, obra_id))
            if quadro == "III":
                return Response(nbr12721.quadro_iii(tenant_id, obra_id, parametro=parametro))
            if quadro == "IV":
                return Response(
                    nbr12721.quadro_iv(tenant_id, obra_id, parametro=parametro, gravar=False)
                )
            if quadro.lower() in MemorialNBR.Quadro.values:
                return Response(
                    nbr12721.quadros_descritivos(tenant_id, obra_id, quadro.lower())
                )
        except nbr12721.DadosInsuficientes as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {"quadro": f"Use I, II, III, IV ou {MemorialNBR.Quadro.values}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def post(self, request):
        tenant_id, obra_id = self._tenant(request), self._obra(request)
        acao = request.data.get("acao")
        try:
            if acao == "coeficientes":
                replicar = request.data.get("replicar_na_fracao_ideal", False) in (True, "true", "1", 1)
                nbr12721.calcular_coeficientes(
                    tenant_id, obra_id, replicar_na_fracao_ideal=replicar
                )
                return Response(nbr12721.quadro_ii(tenant_id, obra_id))
            if acao == "ratear":
                parametro = self._parametro(tenant_id, obra_id)
                return Response(nbr12721.quadro_iv(tenant_id, obra_id, parametro=parametro))
        except nbr12721.DadosInsuficientes as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {"acao": "Use 'coeficientes' ou 'ratear'."}, status=status.HTTP_400_BAD_REQUEST
        )


class RevisaoOrcamentoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Histórico de aditivos/supressões — read-only.

    A revisão nasce como **efeito** de `orcamentos/{id}/revisar/`, nunca por
    POST direto: um registro de revisão sem a versão nova correspondente seria
    rastro falso.
    """

    queryset = RevisaoOrcamento.objects.select_related("orcamento", "orcamento_anterior").all()
    serializer_class = RevisaoOrcamentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "tipo", "orcamento__obra"]
    ordering_fields = ["criado_em", "numero"]
    required_permission = "orcamento.orcamento.view"


# ---------------------------------------------------------------------------
# ORC.5b — bancos da empresa, importação e reprecificação
# ---------------------------------------------------------------------------
#
# Nenhuma permissão nova (§12.1 da planta): manter o banco de preço da empresa é
# a mesma mão que monta a planilha (`orcamento.orcamento.edit`), trazer preço de
# fora é da família de adotar (`orcamento.base.adotar`) e ler é
# `orcamento.base.view`. Permissão nova custa rebuild da imagem da IAM +
# re-seed; se na prática "quem cuida do banco de preço" virar um papel distinto
# de "quem orça", aí sim vale criar `orcamento.banco.*`.


class BancoPrecoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Bancos de preço **da empresa** — o espelho tenant-scoped da base pública."""

    queryset = BancoPreco.objects.select_related("obra").all()
    serializer_class = BancoPrecoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["fonte", "uf", "obra", "travado", "ativo", "origem"]
    search_fields = ["nome", "descricao"]
    ordering_fields = ["nome", "mes_referencia", "total_itens", "criado_em"]
    required_resource = "orcamento.base"
    action_permission_map = {
        "create": "orcamento.orcamento.edit",
        "update": "orcamento.orcamento.edit",
        "partial_update": "orcamento.orcamento.edit",
        "destroy": "orcamento.orcamento.edit",
        "travar": "orcamento.orcamento.edit",
        "destravar": "orcamento.orcamento.edit",
        "adotar_lote": "orcamento.base.adotar",
        "copiar_da_base": "orcamento.base.adotar",
        "resumo": "orcamento.base.view",
    }

    def perform_update(self, serializer):
        banco = self.get_object()
        if banco.travado:
            raise exceptions.ValidationError(
                {"detail": f'O banco "{banco.nome}" está travado. Destrave para editar.'}
            )
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.travado:
            raise exceptions.ValidationError(
                {"detail": "Banco travado não é excluído — destrave primeiro, de propósito."}
            )
        instance.delete()

    @action(detail=False, methods=["get"], url_path="resumo")
    def resumo(self, request):
        return Response(servico_bancos.resumo(self._tenant_id()))

    @action(detail=True, methods=["post"], url_path="travar")
    def travar(self, request, pk=None):
        banco = servico_bancos.travar(
            self.get_object(), usuario_nome=self._usuario(request)
        )
        return Response(self.get_serializer(banco).data)

    @action(detail=True, methods=["post"], url_path="destravar")
    def destravar(self, request, pk=None):
        banco = servico_bancos.destravar(
            self.get_object(), usuario_nome=self._usuario(request)
        )
        return Response(self.get_serializer(banco).data)

    @action(detail=True, methods=["post"], url_path="adotar-lote")
    def adotar_lote(self, request, pk=None):
        """Adota itens deste banco no catálogo da empresa."""
        banco = self.get_object()
        ids = request.data.get("itens") or []
        itens = list(ItemBancoPreco.objects.filter(
            tenant_id=self._tenant_id(), banco=banco, pk__in=ids
        ).select_related("banco"))
        if not itens:
            return Response({"itens": "Nenhum item encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            adotados = servico_bancos.adotar_muitos(itens, self._tenant_id())
        except servico_bancos.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"adotados": [i.pk for i in adotados], "criados": len(adotados)})

    @action(detail=True, methods=["post"], url_path="copiar-da-base")
    def copiar_da_base(self, request, pk=None):
        """Copia itens da SINAPI/ORSE para dentro deste banco, **editáveis**.

        O caminho pedido pelo dono do produto: ajustar coeficiente sem tocar na
        base oficial, que segue read-only.
        """
        banco = self.get_object()
        ids = request.data.get("referencias") or []
        referencias = list(
            InsumoReferencia.objects.filter(pk__in=ids).select_related("base")
        )
        if not referencias:
            return Response(
                {"referencias": "Nenhuma referência encontrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            criados = servico_bancos.copiar_da_base_publica(
                referencias, banco_destino=banco,
                com_composicao=request.data.get("com_composicao", True) is not False,
            )
        except servico_bancos.BancoTravado as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        banco.refresh_from_db()
        return Response({"criados": criados, "total_itens": banco.total_itens})

    @staticmethod
    def _usuario(request) -> str:
        user = getattr(request, "user", None)
        return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""


class PastaComposicaoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Pastas dentro de um banco — organização por obra/tipo."""

    queryset = PastaComposicao.objects.select_related("banco", "obra").all()
    serializer_class = PastaComposicaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["banco", "obra"]
    ordering_fields = ["ordem", "nome"]
    required_resource = "orcamento.base"
    action_permission_map = {
        "create": "orcamento.orcamento.edit",
        "update": "orcamento.orcamento.edit",
        "partial_update": "orcamento.orcamento.edit",
        "destroy": "orcamento.orcamento.edit",
    }


class ItemBancoPrecoViewSet(
    _OrcamentoPermsMixin, QuotaEnforcedMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet
):
    """Itens de um banco da empresa. Busca server-side, como a base pública.

    A quota `banco_preco_linhas` vale aqui também, não só na importação: sem
    isto, o teto do plano seria contornável criando item a item pela API — o
    caminho é mais lento, mas o limite é comercial, e limite que se contorna com
    paciência não é limite.
    """

    quota_recurso = "banco_preco_linhas"
    queryset = ItemBancoPreco.objects.select_related("banco", "pasta").all()
    serializer_class = ItemBancoPrecoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["banco", "pasta", "tipo"]
    search_fields = ["codigo", "descricao", "grupo"]
    ordering_fields = ["codigo", "descricao", "custo_unitario"]
    required_resource = "orcamento.base"
    action_permission_map = {
        "create": "orcamento.orcamento.edit",
        "update": "orcamento.orcamento.edit",
        "partial_update": "orcamento.orcamento.edit",
        "destroy": "orcamento.orcamento.edit",
        "adotar": "orcamento.base.adotar",
        "duplicar": "orcamento.orcamento.edit",
        "composicao": "orcamento.base.view",
    }

    def get_serializer_context(self):
        """Marca o que já foi adotado — um SELECT por página, não um por linha."""
        contexto = super().get_serializer_context()
        if self.action != "list":
            return contexto
        pagina = getattr(self, "_pagina_atual", None) or []
        codigos = [(i.banco.fonte, i.codigo) for i in pagina]
        if codigos:
            adotados = Item.objects.filter(
                tenant_id=self._tenant_id(),
                codigo_referencia__in=[c for _, c in codigos],
            ).values_list("fonte_referencia", "codigo_referencia", "item_id")
            contexto["adotados"] = {(f, c): i for f, c, i in adotados}
        return contexto

    def paginate_queryset(self, queryset):
        pagina = super().paginate_queryset(queryset)
        self._pagina_atual = pagina
        return pagina

    def perform_destroy(self, instance):
        if instance.banco.travado:
            raise exceptions.ValidationError({"detail": "Banco travado — destrave primeiro."})
        banco = instance.banco
        instance.delete()
        servico_bancos.recontar(banco)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        servico_bancos.recontar(serializer.instance.banco)

    @action(detail=True, methods=["get"], url_path="composicao")
    def composicao(self, request, pk=None):
        componentes = ComponenteBancoPreco.objects.filter(
            composicao=self.get_object()
        ).select_related("filho")
        return Response(ComponenteBancoPrecoSerializer(componentes, many=True).data)

    @action(detail=True, methods=["post"], url_path="adotar")
    def adotar(self, request, pk=None):
        try:
            item = servico_bancos.adotar_no_catalogo(self.get_object(), self._tenant_id())
        except servico_bancos.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"item": item.pk, "criado": True})

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, pk=None):
        """Copia o item (com a composição) para outro banco, para editar lá."""
        destino_id = request.data.get("banco_destino")
        destino = BancoPreco.objects.filter(
            tenant_id=self._tenant_id(), pk=destino_id
        ).first()
        if destino is None:
            return Response(
                {"banco_destino": "Banco de destino não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            clone = servico_bancos.duplicar_item(
                self.get_object(), banco_destino=destino,
                novo_codigo=(request.data.get("codigo") or "").strip(),
            )
        except servico_bancos.BancoTravado as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(clone).data, status=status.HTTP_201_CREATED)


class ComponenteBancoPrecoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Coeficientes das composições próprias — a memória de cálculo da empresa."""

    queryset = ComponenteBancoPreco.objects.select_related("composicao", "filho").all()
    serializer_class = ComponenteBancoPrecoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["composicao", "filho"]
    required_resource = "orcamento.base"
    action_permission_map = {
        "create": "orcamento.orcamento.edit",
        "update": "orcamento.orcamento.edit",
        "partial_update": "orcamento.orcamento.edit",
        "destroy": "orcamento.orcamento.edit",
    }


class ReprecificacaoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Lotes de troca de data-base — o histórico com o desfazer."""

    queryset = Reprecificacao.objects.select_related(
        "orcamento", "base_destino", "banco_destino"
    ).all()
    serializer_class = ReprecificacaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "status", "orcamento__obra"]
    ordering_fields = ["criado_em", "aplicada_em"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {
        "aplicar": "orcamento.orcamento.edit",
        "desfazer": "orcamento.orcamento.edit",
        "linhas": "orcamento.orcamento.view",
    }

    @action(detail=True, methods=["get"], url_path="linhas")
    def linhas(self, request, pk=None):
        return Response(servico_reprecificacao.serializar_previa(self.get_object()))

    @action(detail=True, methods=["post"], url_path="aplicar")
    def aplicar(self, request, pk=None):
        try:
            lote = servico_reprecificacao.aplicar(
                self.get_object(),
                selecionadas=request.data.get("linhas"),
                usuario_nome=self._usuario(request),
            )
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except servico_reprecificacao.ReprecificacaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(servico_reprecificacao.serializar_previa(lote))

    @action(detail=True, methods=["post"], url_path="desfazer")
    def desfazer(self, request, pk=None):
        try:
            lote = servico_reprecificacao.desfazer(self.get_object())
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except servico_reprecificacao.ReprecificacaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(lote).data)

    @staticmethod
    def _usuario(request) -> str:
        user = getattr(request, "user", None)
        return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""
