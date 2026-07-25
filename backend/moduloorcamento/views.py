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
from rest_framework import exceptions, filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogo.models import Item
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from . import planilha, services
from .models import (
    BaseReferencial,
    ComposicaoReferenciaItem,
    InsumoReferencia,
    ItemOrcado,
    Orcamento,
    RevisaoOrcamento,
)
from .pagination import OrcamentoPageNumberPagination
from .serializers import (
    BaseReferencialSerializer,
    ComposicaoReferenciaItemSerializer,
    InsumoReferenciaSerializer,
    ItemOrcadoSerializer,
    OrcamentoSerializer,
    RevisaoOrcamentoSerializer,
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
