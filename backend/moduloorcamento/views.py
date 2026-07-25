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
from rest_framework import filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogo.models import Item
from nucleo.permissions import RequireModule, RequirePermission

from . import services
from .models import BaseReferencial, ComposicaoReferenciaItem, InsumoReferencia
from .pagination import OrcamentoPageNumberPagination
from .serializers import (
    BaseReferencialSerializer,
    ComposicaoReferenciaItemSerializer,
    InsumoReferenciaSerializer,
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
