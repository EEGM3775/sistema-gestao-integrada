# backend/moduloscm/views.py
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
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

    def _tenant_id(self):
        return getattr(getattr(self.request, "user", None), "tenant_id", None)


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

    def get_serializer_context(self):
        """Pré-computa a reputação (média/nº) dos fornecedores das propostas
        listadas numa só query, para as estrelas do comparativo (sem N+1)."""
        ctx = super().get_serializer_context()
        try:
            qs = self.filter_queryset(self.get_queryset())
            forn_ids = qs.values_list("fornecedor_id", flat=True)
            ctx["avaliacao_agg"] = AvaliacaoFornecedor.agg_por_fornecedor(self._tenant_id(), forn_ids)
        except Exception:  # pragma: no cover - contexto é otimização, nunca bloqueia
            pass
        return ctx


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


def _mes_bounds(ref):
    """(início, fim) do mês da data `ref` (dia 1 → último dia)."""
    inicio = ref.replace(day=1)
    fim = (date(inicio.year + 1, 1, 1) if inicio.month == 12 else date(inicio.year, inicio.month + 1, 1)) - timedelta(days=1)
    return inicio, fim


class ScmDashboardView(views.APIView):
    """Hub do SCM numa só resposta (substitui as ~8 idas do frontend). Só
    contagens/somas dos dados do próprio tenant — gateado pelo módulo, sem
    permissão nova no catálogo (é o que o usuário já lista). O contexto RLS já
    foi armado na autenticação; filtra-se por `tenant_id` por robustez (e p/ o
    SQLite, onde a RLS é no-op).

    O valor comprado é **por mês escolhido**: `?mes=AAAA-MM` (default: mês
    corrente). Retorna o valor do mês escolhido e o do mês anterior a ele (delta
    real no frontend). As contagens (demandas/pedidos abertos) são estado atual,
    não do mês."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "scm"

    def _ref_mes(self, request, hoje):
        raw = (request.query_params.get("mes") or "").strip()
        if raw:
            try:
                ano, mes = raw.split("-")
                return date(int(ano), int(mes), 1)
            except (ValueError, TypeError):
                pass
        return hoje.replace(day=1)

    def get(self, request):
        tid = getattr(request.user, "tenant_id", None)

        def dcount(**flt):
            return Demanda.objects.filter(tenant_id=tid, **flt).count()

        def pcount(**flt):
            return PedidoCompra.objects.filter(tenant_id=tid, **flt).count()

        hoje = timezone.localdate()
        ref = self._ref_mes(request, hoje)
        inicio_mes, fim_mes = _mes_bounds(ref)
        inicio_mes_ant, fim_mes_ant = _mes_bounds(inicio_mes - timedelta(days=1))
        nao_cancelado = ~Q(status=PedidoCompra.Status.CANCELADO)

        def valor_periodo(ini, fim):
            v = (
                PedidoCompra.objects.filter(tenant_id=tid, data_pedido__gte=ini, data_pedido__lte=fim)
                .filter(nao_cancelado)
                .aggregate(s=Sum("valor_total"))["s"]
            )
            return str(v if v is not None else Decimal("0"))

        fornecedores_avaliados = (
            AvaliacaoFornecedor.objects.filter(tenant_id=tid)
            .values("fornecedor_id")
            .distinct()
            .count()
        )

        # Economia em cotações adjudicadas: Σ (maior proposta − vencedora).
        economia = Decimal("0")
        cotacoes_adjudicadas = 0
        for cot in Cotacao.objects.filter(tenant_id=tid, status=Cotacao.Status.ADJUDICADA).prefetch_related("propostas"):
            propostas = list(cot.propostas.all())
            valores = [p.valor_total for p in propostas if p.valor_total is not None]
            venc = next((p for p in propostas if p.status == Proposta.Status.VENCEDORA), None)
            if valores and venc and venc.valor_total is not None:
                economia += max(valores) - venc.valor_total
                cotacoes_adjudicadas += 1

        # Cotações abertas vencendo hoje ou já vencidas.
        cotacoes_vencem_hoje = Cotacao.objects.filter(
            tenant_id=tid, status=Cotacao.Status.ABERTA, data_limite__lte=hoje
        ).count()

        # Pedidos em trânsito (aprovado/enviado/recebido parcial): valor, nº e fornecedores.
        transito = PedidoCompra.objects.filter(
            tenant_id=tid,
            status__in=[PedidoCompra.Status.APROVADO, PedidoCompra.Status.ENVIADO, PedidoCompra.Status.RECEBIDO_PARCIAL],
        )
        transito_valor = transito.aggregate(s=Sum("valor_total"))["s"] or Decimal("0")
        transito_count = transito.count()
        transito_fornecedores = transito.values("fornecedor_id").distinct().count()

        # Prazo médio de entrega (dias entre o pedido e o recebimento total).
        difs = []
        for ped in PedidoCompra.objects.filter(tenant_id=tid, status=PedidoCompra.Status.RECEBIDO_TOTAL).prefetch_related("recebimentos"):
            rec = ped.recebimentos.filter(tipo=Recebimento.Tipo.TOTAL).order_by("data").first()
            if rec and ped.data_pedido:
                difs.append((rec.data - ped.data_pedido).days)
        prazo_medio = round(sum(difs) / len(difs), 1) if difs else None

        # Atividade recente — fatos variados (recebimento, adjudicação, compra direta, avaliação).
        atividade = []
        for r in Recebimento.objects.filter(tenant_id=tid).select_related("pedido__fornecedor").order_by("-criado_em")[:6]:
            atividade.append({
                "tipo": "recebimento",
                "titulo": f"Recebimento {r.get_tipo_display().lower()} — Pedido #{r.pedido_id}",
                "meta": f"{r.pedido.fornecedor.razao_social} · {r.data.strftime('%d/%m/%Y')}",
                "quando": r.criado_em.isoformat(),
            })
        for c in Cotacao.objects.filter(tenant_id=tid, status=Cotacao.Status.ADJUDICADA).prefetch_related("propostas__fornecedor").order_by("-criado_em")[:4]:
            venc = next((p for p in c.propostas.all() if p.status == Proposta.Status.VENCEDORA), None)
            rotulo = (venc.fornecedor.razao_social if venc and venc.fornecedor_id else (venc.fornecedor_nome if venc else "")) or "fornecedor"
            atividade.append({
                "tipo": "adjudicacao",
                "titulo": f"Cotação adjudicada — #{c.cotacao_id}",
                "meta": f"{rotulo}" + (f" · R$ {venc.valor_total}" if venc and venc.valor_total is not None else ""),
                "quando": c.criado_em.isoformat(),
            })
        for p in PedidoCompra.objects.filter(tenant_id=tid, origem=PedidoCompra.Origem.COMPRA_DIRETA).select_related("fornecedor").order_by("-criado_em")[:4]:
            atividade.append({
                "tipo": "compra_direta",
                "titulo": f"Compra direta — Pedido #{p.pedido_id}",
                "meta": f"{p.fornecedor.razao_social}" + (f" · R$ {p.valor_total}" if p.valor_total is not None else ""),
                "quando": p.criado_em.isoformat(),
            })
        for a in AvaliacaoFornecedor.objects.filter(tenant_id=tid).select_related("fornecedor").order_by("-avaliacao_id")[:4]:
            media = round((a.nota_qualidade + a.nota_pontualidade + a.nota_atendimento) / 3, 1)
            atividade.append({
                "tipo": "avaliacao",
                "titulo": f"Fornecedor avaliado — {a.fornecedor.razao_social}",
                "meta": f"nota {media}",
                "quando": a.data.isoformat() if a.data else "",
            })
        atividade.sort(key=lambda e: e["quando"], reverse=True)
        atividade = atividade[:6]

        return Response(
            {
                "demandasAbertas": dcount(status=Demanda.Status.ABERTA),
                "demandasEmCotacao": dcount(status=Demanda.Status.EM_COTACAO),
                "cotacoesAbertas": Cotacao.objects.filter(tenant_id=tid, status=Cotacao.Status.ABERTA).count(),
                "pedidosAprovados": pcount(status=PedidoCompra.Status.APROVADO),
                "pedidosEnviados": pcount(status=PedidoCompra.Status.ENVIADO),
                "pedidosRecebidosParcial": pcount(status=PedidoCompra.Status.RECEBIDO_PARCIAL),
                "produtosAtivos": Produto.objects.filter(tenant_id=tid, ativo=True).count(),
                "ofertasDiretas": OfertaFornecedor.objects.filter(tenant_id=tid, compra_direta=True, ativo=True).count(),
                "mesReferencia": inicio_mes.strftime("%Y-%m"),
                "valorCompradoMes": valor_periodo(inicio_mes, fim_mes),
                "valorCompradoMesAnterior": valor_periodo(inicio_mes_ant, fim_mes_ant),
                "fornecedoresAvaliados": fornecedores_avaliados,
                "economiaAdjudicadas": str(economia),
                "cotacoesAdjudicadas": cotacoes_adjudicadas,
                "cotacoesVencemHoje": cotacoes_vencem_hoje,
                "pedidosTransitoValor": str(transito_valor),
                "pedidosTransitoCount": transito_count,
                "pedidosTransitoFornecedores": transito_fornecedores,
                "prazoMedioEntregaDias": prazo_medio,
                "atividade": atividade,
            }
        )
