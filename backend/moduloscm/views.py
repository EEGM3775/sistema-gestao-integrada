# backend/moduloscm/views.py
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nucleo.permissions import RequireModule, RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from .pagination import ScmPageNumberPagination

from .models import (
    AvaliacaoFornecedor,
    CentroCusto,
    Cotacao,
    Demanda,
    FaixaPrecoOferta,
    ItemDemanda,
    ItemPedido,
    ItemProposta,
    ItemRecebimento,
    OfertaFornecedor,
    PedidoCompra,
    Produto,
    Proposta,
    Recebimento,
)
from .serializers import (
    AvaliacaoFornecedorSerializer,
    CentroCustoSerializer,
    CotacaoSerializer,
    DemandaSerializer,
    FaixaPrecoOfertaSerializer,
    ItemDemandaSerializer,
    ItemPedidoSerializer,
    ItemPropostaSerializer,
    ItemRecebimentoSerializer,
    OfertaFornecedorSerializer,
    PedidoCompraSerializer,
    ProdutoSerializer,
    PropostaSerializer,
    RecebimentoSerializer,
)


class ScmStatusView(views.APIView):
    """Endpoint de status do módulo SCM. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "scm"

    def get(self, request):
        return Response({"modulo": "scm", "status": "ativo"})


class BaseScmViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Base dos ViewSets do SCM: isolamento por tenant + entitlement `scm` +
    checagem por permissão (camada 2). Cada ViewSet declara `required_resource`."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "scm"
    # Listas paginadas server-side (busca + página) — os selects do frontend
    # buscam por `?search=&page_size=`; as tabelas-filhas desligam abaixo.
    pagination_class = ScmPageNumberPagination


class CentroCustoViewSet(BaseScmViewSet):
    queryset = CentroCusto.objects.all().order_by("nome")
    serializer_class = CentroCustoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["tipo", "ativo", "empreendimento", "obra"]
    search_fields = ["nome", "codigo"]
    ordering_fields = ["nome", "codigo"]
    required_resource = "scm.centro_custo"


class ProdutoViewSet(BaseScmViewSet):
    queryset = Produto.objects.all().order_by("descricao")
    serializer_class = ProdutoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["tipo_item", "categoria", "ativo"]
    search_fields = ["codigo_interno", "descricao", "categoria", "gtin"]
    ordering_fields = ["descricao", "codigo_interno"]
    required_resource = "scm.produto"


class OfertaFornecedorViewSet(BaseScmViewSet):
    queryset = OfertaFornecedor.objects.all().order_by("produto", "preco_direto")
    serializer_class = OfertaFornecedorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["produto", "fornecedor", "compra_direta", "visibilidade", "ativo"]
    search_fields = ["produto__descricao", "produto__codigo_interno", "codigo_no_fornecedor"]
    ordering_fields = ["preco_direto", "prazo_entrega_dias"]
    required_resource = "scm.oferta"


class FaixaPrecoOfertaViewSet(BaseScmViewSet):
    queryset = FaixaPrecoOferta.objects.all().order_by("oferta", "quantidade_min")
    serializer_class = FaixaPrecoOfertaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["oferta"]
    ordering_fields = ["quantidade_min", "preco_unitario"]
    # A faixa é parte da precificação da oferta → gateada pela mesma permissão.
    required_resource = "scm.oferta"
    pagination_class = None  # lida por oferta (todas as faixas de uma vez)


# --- Fatia 2 — Demanda (pivô) e Cotação → Proposta ---
class DemandaViewSet(BaseScmViewSet):
    queryset = Demanda.objects.all().order_by("-criado_em")
    serializer_class = DemandaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["tipo", "status", "visibilidade", "origem", "centro_custo"]
    search_fields = ["categoria", "regiao", "observacao"]
    ordering_fields = ["criado_em", "status"]
    required_resource = "scm.demanda"
    action_permission_map = {"publicar": "scm.demanda.publicar"}

    def perform_create(self, serializer):
        # Solicitante default = usuário do request (se não veio no payload).
        user = getattr(self.request, "user", None)
        extra = {}
        if not serializer.validated_data.get("solicitante"):
            extra["solicitante"] = user
        serializer.save(tenant_id=getattr(user, "tenant_id", None), **extra)

    @action(detail=True, methods=["post"])
    def publicar(self, request, pk=None):
        """Publica a demanda na rede (marketplace reverso) — opt-in. O gêmeo
        espelhado e a distribuição aos fornecedores externos são da Esfera de
        Rede; aqui só marca a visibilidade e abre a demanda."""
        demanda = self.get_object()
        demanda.visibilidade = Demanda.Visibilidade.REDE
        if demanda.status == Demanda.Status.RASCUNHO:
            demanda.status = Demanda.Status.ABERTA
        demanda.save(update_fields=["visibilidade", "status"])
        return Response(self.get_serializer(demanda).data)


class ItemDemandaViewSet(BaseScmViewSet):
    queryset = ItemDemanda.objects.all().order_by("item_demanda_id")
    serializer_class = ItemDemandaSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["demanda", "produto"]
    required_resource = "scm.demanda"
    pagination_class = None  # itens lidos por demanda


class CotacaoViewSet(BaseScmViewSet):
    queryset = Cotacao.objects.all().order_by("-criado_em")
    serializer_class = CotacaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["demanda", "status", "visibilidade"]
    ordering_fields = ["criado_em", "status"]
    required_resource = "scm.cotacao"
    action_permission_map = {"adjudicar": "scm.cotacao.adjudicar"}

    @action(detail=True, methods=["post"])
    def adjudicar(self, request, pk=None):
        """Adjudica a cotação a uma proposta vencedora: marca as demais como
        recusadas e encerra a cotação. A geração do Pedido é da fatia 3."""
        cotacao = self.get_object()
        proposta_id = request.data.get("proposta_id")
        try:
            vencedora = cotacao.propostas.get(pk=proposta_id)
        except Proposta.DoesNotExist:
            return Response(
                {"detail": "Proposta não encontrada nesta cotação."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cotacao.propostas.update(status=Proposta.Status.RECUSADA)
        vencedora.status = Proposta.Status.VENCEDORA
        vencedora.save(update_fields=["status"])
        cotacao.status = Cotacao.Status.ADJUDICADA
        cotacao.save(update_fields=["status"])
        return Response(self.get_serializer(cotacao).data)


class PropostaViewSet(BaseScmViewSet):
    queryset = Proposta.objects.all().order_by("cotacao", "valor_total")
    serializer_class = PropostaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["cotacao", "fornecedor", "status"]
    ordering_fields = ["valor_total", "prazo_entrega_dias"]
    # A proposta é registrada no fluxo da cotação → gateada pela permissão dela.
    required_resource = "scm.cotacao"


class ItemPropostaViewSet(BaseScmViewSet):
    queryset = ItemProposta.objects.all().order_by("item_proposta_id")
    serializer_class = ItemPropostaSerializer
    filter_backends = [DjangoFilterBackend]
    # `proposta__cotacao` monta o mapa comparativo (itens × propostas) numa chamada.
    filterset_fields = ["proposta", "item_demanda", "proposta__cotacao"]
    required_resource = "scm.cotacao"
    pagination_class = None  # itens lidos por proposta


# --- Fatia 3 — Pedido (duas vias) → Recebimento + Avaliação ---
class PedidoCompraViewSet(BaseScmViewSet):
    queryset = PedidoCompra.objects.all().order_by("-criado_em")
    serializer_class = PedidoCompraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["origem", "status", "fornecedor", "centro_custo", "demanda"]
    ordering_fields = ["criado_em", "data_pedido", "valor_total"]
    required_resource = "scm.pedido"
    action_permission_map = {
        "comprar_direto": "scm.pedido.criar",
        "gerar_de_cotacao": "scm.pedido.criar",
    }

    def _tenant_id(self):
        return getattr(getattr(self.request, "user", None), "tenant_id", None)

    @action(detail=False, methods=["post"])
    def comprar_direto(self, request):
        """Via de compra direta: gera um pedido a partir de uma `OfertaFornecedor`
        publicada p/ compra direta, a preço fixo, **sem cotação**."""
        tid = self._tenant_id()
        try:
            oferta = OfertaFornecedor.objects.get(pk=request.data.get("oferta"), tenant_id=tid)
        except OfertaFornecedor.DoesNotExist:
            return Response({"detail": "Oferta não encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        if not oferta.compra_direta:
            return Response(
                {"detail": "Esta oferta não está disponível para compra direta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            quantidade = Decimal(str(request.data.get("quantidade")))
        except (InvalidOperation, TypeError):
            return Response({"detail": "Quantidade inválida."}, status=status.HTTP_400_BAD_REQUEST)
        if quantidade <= 0:
            return Response({"detail": "Quantidade deve ser positiva."}, status=status.HTTP_400_BAD_REQUEST)

        centro_custo = None
        cc_id = request.data.get("centro_custo")
        if cc_id:
            centro_custo = CentroCusto.objects.filter(pk=cc_id, tenant_id=tid).first()

        with transaction.atomic():
            pedido = PedidoCompra.objects.create(
                tenant_id=tid, origem=PedidoCompra.Origem.COMPRA_DIRETA,
                oferta_origem=oferta, fornecedor=oferta.fornecedor, centro_custo=centro_custo,
                status=PedidoCompra.Status.APROVADO,
                valor_total=(oferta.preco_direto * quantidade),
            )
            ItemPedido.objects.create(
                tenant_id=tid, pedido=pedido, produto=oferta.produto,
                quantidade=quantidade, preco_unitario=oferta.preco_direto,
            )
        return Response(self.get_serializer(pedido).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def gerar_de_cotacao(self, request):
        """Via de cotação: gera o pedido da proposta vencedora de uma cotação
        adjudicada (copiando seus itens)."""
        tid = self._tenant_id()
        try:
            cotacao = Cotacao.objects.get(pk=request.data.get("cotacao"), tenant_id=tid)
        except Cotacao.DoesNotExist:
            return Response({"detail": "Cotação não encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        vencedora = cotacao.propostas.filter(status=Proposta.Status.VENCEDORA).first()
        if vencedora is None:
            return Response(
                {"detail": "Cotação sem proposta vencedora — adjudique antes de gerar o pedido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            pedido = PedidoCompra.objects.create(
                tenant_id=tid, origem=PedidoCompra.Origem.COTACAO,
                demanda=cotacao.demanda, proposta_vencedora=vencedora,
                fornecedor=vencedora.fornecedor, centro_custo=getattr(cotacao.demanda, "centro_custo", None),
                status=PedidoCompra.Status.APROVADO, valor_total=vencedora.valor_total,
            )
            for ip in vencedora.itens.all():
                ItemPedido.objects.create(
                    tenant_id=tid, pedido=pedido, produto=ip.item_demanda.produto,
                    descricao=ip.item_demanda.descricao_servico,
                    quantidade=ip.quantidade, preco_unitario=ip.preco_unitario,
                )
            if cotacao.demanda_id:
                Demanda.objects.filter(pk=cotacao.demanda_id).update(status=Demanda.Status.ATENDIDA)
        return Response(self.get_serializer(pedido).data, status=status.HTTP_201_CREATED)


class ItemPedidoViewSet(BaseScmViewSet):
    queryset = ItemPedido.objects.all().order_by("item_pedido_id")
    serializer_class = ItemPedidoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["pedido", "produto"]
    required_resource = "scm.pedido"
    pagination_class = None  # itens lidos por pedido


class RecebimentoViewSet(BaseScmViewSet):
    queryset = Recebimento.objects.all().order_by("-criado_em")
    serializer_class = RecebimentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["pedido", "tipo"]
    ordering_fields = ["data", "criado_em"]
    required_resource = "scm.recebimento"

    def perform_create(self, serializer):
        """Cria o recebimento e propaga o status ao pedido. A entrada no estoque
        (SIL) é o seam futuro — aqui só o registro + o status do pedido."""
        tid = getattr(getattr(self.request, "user", None), "tenant_id", None)
        recebimento = serializer.save(tenant_id=tid)
        novo = (
            PedidoCompra.Status.RECEBIDO_TOTAL
            if recebimento.tipo == Recebimento.Tipo.TOTAL
            else PedidoCompra.Status.RECEBIDO_PARCIAL
        )
        PedidoCompra.objects.filter(pk=recebimento.pedido_id).update(status=novo)


class ItemRecebimentoViewSet(BaseScmViewSet):
    queryset = ItemRecebimento.objects.all().order_by("item_recebimento_id")
    serializer_class = ItemRecebimentoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["recebimento", "item_pedido"]
    required_resource = "scm.recebimento"
    pagination_class = None  # itens lidos por recebimento


class AvaliacaoFornecedorViewSet(BaseScmViewSet):
    queryset = AvaliacaoFornecedor.objects.all().order_by("-data")
    serializer_class = AvaliacaoFornecedorSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["fornecedor", "pedido"]
    ordering_fields = ["data", "nota_qualidade"]
    required_resource = "scm.avaliacao"
