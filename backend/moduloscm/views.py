# backend/moduloscm/views.py
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.busca import BuscaSemAcento
from rest_framework import filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nucleo.permissions import RequireModule, RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from catalogo.models import Item

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
    NotaFiscalCompra,
    OfertaFornecedor,
    PedidoCompra,
    Proposta,
    Recebimento,
)
from .serializers import (
    AvaliacaoFornecedorSerializer,
    CentroCustoSerializer,
    CotacaoSerializer,
    DemandaSerializer,
    EventoPedidoSerializer,
    FaixaPrecoOfertaSerializer,
    ItemDemandaSerializer,
    ItemPedidoSerializer,
    ItemPropostaSerializer,
    ItemRecebimentoSerializer,
    NotaFiscalCompraSerializer,
    OfertaFornecedorSerializer,
    PedidoCompraSerializer,
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
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["tipo", "ativo", "empreendimento", "obra"]
    search_fields = ["nome", "codigo"]
    ordering_fields = ["nome", "codigo"]
    required_resource = "scm.centro_custo"


class OfertaFornecedorViewSet(BaseScmViewSet):
    queryset = OfertaFornecedor.objects.all().order_by("produto", "preco_direto")
    serializer_class = OfertaFornecedorSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
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
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["tipo", "status", "visibilidade", "origem", "centro_custo"]
    search_fields = ["categoria", "regiao", "observacao"]
    ordering_fields = ["criado_em", "status"]
    required_resource = "scm.demanda"
    # `do_orcamento` cria demanda → é escrita de demanda, reusa a permissão do
    # recurso. Não ganhou permissão própria pelo mesmo motivo de sempre:
    # permissão nova exige rebuild da imagem da IAM + re-seed.
    action_permission_map = {
        "publicar": "scm.demanda.publicar",
        "do_orcamento": "scm.demanda.edit",
        "do_cronograma": "scm.demanda.view",
        "do_cronograma_gerar": "scm.demanda.edit",
        "cotar": "scm.demanda.edit",
        "abrir_cotacao": "scm.demanda.edit",
    }

    def destroy(self, request, *args, **kwargs):
        """Apaga a demanda que não virou nada. Com pedido ou proposta ela já tem
        história de compra: aí só cancela (o histórico fica)."""
        from django.db.models import ProtectedError

        demanda = self.get_object()
        if demanda.pedidos.exists():
            return Response({"detail": f"A demanda #{demanda.pk} já gerou pedido e não pode ser apagada."},
                            status=status.HTTP_409_CONFLICT)
        if Proposta.objects.filter(cotacao__demanda=demanda).exists():
            return Response({"detail": f"A demanda #{demanda.pk} já tem proposta de fornecedor e não pode ser apagada."},
                            status=status.HTTP_409_CONFLICT)
        try:
            with transaction.atomic():
                demanda.delete()  # itens e cotações vazias saem junto
        except ProtectedError:
            return Response({"detail": f"A demanda #{demanda.pk} é usada por outro registro e não pode ser apagada."},
                            status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="abrir-cotacao")
    def abrir_cotacao(self, request, pk=None):
        """A demanda já existe (do cronograma, do orçamento, do estoque…): abre a
        cotação dela. Demanda sem itens não cota; a que já tem cotação aberta devolve a mesma."""
        demanda = self.get_object()
        if demanda.status in (Demanda.Status.ATENDIDA, Demanda.Status.CANCELADA):
            return Response({"detail": "Esta demanda já foi atendida ou cancelada."}, status=status.HTTP_400_BAD_REQUEST)
        if not demanda.itens.exists():
            return Response({"detail": "A demanda não tem itens para cotar."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            cotacao = demanda.cotacoes.filter(status=Cotacao.Status.ABERTA).first()
            if cotacao is None:
                cotacao = Cotacao.objects.create(
                    tenant_id=demanda.tenant_id, demanda=demanda, data_limite=request.data.get("data_limite") or None,
                )
            if demanda.status in (Demanda.Status.RASCUNHO, Demanda.Status.ABERTA):
                demanda.status = Demanda.Status.EM_COTACAO
                demanda.save(update_fields=["status"])
        return Response({"demanda_id": demanda.pk, "cotacao_id": cotacao.pk})

    @action(detail=False, methods=["post"])
    def cotar(self, request):
        """Cotar direto do catálogo: itens e quantidades → demanda aberta + cotação
        aberta, de uma vez. Quem cota já recebe o link da cotação para chamar propostas."""
        tenant_id = getattr(request.user, "tenant_id", None)
        itens = request.data.get("itens")
        if not isinstance(itens, list) or not itens:
            return Response({"itens": "Informe ao menos um item."}, status=status.HTTP_400_BAD_REQUEST)
        linhas = []
        for linha in itens:
            try:
                quantidade = Decimal(str(linha.get("quantidade")))
            except (InvalidOperation, AttributeError):
                quantidade = Decimal("0")
            produto = Item.objects.filter(tenant_id=tenant_id, pk=linha.get("produto")).first() if isinstance(linha, dict) else None
            if produto is None or quantidade <= 0:
                return Response({"itens": "Cada item precisa existir no catálogo e ter quantidade positiva."},
                                status=status.HTTP_400_BAD_REQUEST)
            linhas.append((produto, quantidade))
        centro = None
        if request.data.get("centro_custo"):
            centro = CentroCusto.objects.filter(tenant_id=tenant_id, pk=request.data["centro_custo"]).first()
            if centro is None:
                return Response({"centro_custo": "Centro de custo não encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        data_limite = request.data.get("data_limite") or None
        with transaction.atomic():
            demanda = Demanda.objects.create(
                tenant_id=tenant_id, centro_custo=centro, solicitante=request.user,
                status=Demanda.Status.EM_COTACAO, observacao=(request.data.get("observacao") or "")[:2000],
            )
            for produto, quantidade in linhas:
                ItemDemanda.objects.create(
                    tenant_id=tenant_id, demanda=demanda, produto=produto, quantidade=quantidade,
                    unidade=(produto.unidade or "")[:20],
                )
            cotacao = Cotacao.objects.create(tenant_id=tenant_id, demanda=demanda, data_limite=data_limite)
        return Response({"demanda_id": demanda.pk, "cotacao_id": cotacao.pk}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="do-cronograma")
    def do_cronograma(self, request):
        """A fila "comprar até DD/MM" das obras — a mesma do posto Plano do PDCA,
        aqui por insumo, juntando as obras (`modulopdca.suprimentos`).

        Import tardio e tolerante, como o `do-orcamento`: sem o PDCA, 409."""
        try:
            from modulopdca.suprimentos import fila_de_compras_das_obras
        except ImportError:
            return Response({"detail": "O módulo PDCA não está disponível nesta instalação."},
                            status=status.HTTP_409_CONFLICT)
        return Response(fila_de_compras_das_obras(request.user.tenant_id))

    @action(detail=False, methods=["post"], url_path="do-cronograma/gerar")
    def do_cronograma_gerar(self, request):
        """O que falta de uma obra (ou dos insumos escolhidos) vira demanda em rascunho."""
        try:
            from modulopdca.models import Cronograma
            from modulopdca.suprimentos import gerar_demandas_do_plano
        except ImportError:
            return Response({"detail": "O módulo PDCA não está disponível nesta instalação."},
                            status=status.HTTP_409_CONFLICT)
        plano = Cronograma.objects.filter(
            tenant_id=request.user.tenant_id, pk=request.data.get("cronograma"),
        ).select_related("obra").first()
        if plano is None:
            return Response({"cronograma": "Informe o cronograma da obra."}, status=status.HTTP_400_BAD_REQUEST)
        insumos = request.data.get("insumos") or None
        if insumos is not None and not isinstance(insumos, list):
            return Response({"insumos": "Lista de insumos."}, status=status.HTTP_400_BAD_REQUEST)
        criadas = gerar_demandas_do_plano(plano, insumos=insumos, solicitante=request.user)
        if not criadas:
            return Response({"detail": "Nada a comprar: estoque, pedidos e demandas da obra já cobrem."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"demandas": criadas}, status=status.HTTP_201_CREATED)

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

    @action(detail=False, methods=["post"], url_path="do-orcamento")
    def do_orcamento(self, request):
        """A compra que nasce da planilha: relação de insumos → demanda em rascunho.

        Fecha o primeiro elo do laço `orçado → comprometido → aplicado →
        realizado`, que era o único sem caminho automático. A quantidade é a
        consolidada da obra inteira — o aço que aparece em nove serviços entra
        uma vez, somado, com o mesmo `catalogo.Item` que o orçamento usou.

        **Import tardio e tolerante**, como o SIL faz com o orçado: quem não
        assina o módulo `orcamento` recebe 409 com explicação, não 500.
        """
        orcamento_id = request.data.get("orcamento")
        if not orcamento_id:
            return Response(
                {"orcamento": "Informe o orçamento de origem."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from moduloorcamento.models import Orcamento

            from .do_orcamento import GeracaoInvalida, demanda_do_orcamento
        except ImportError:
            return Response(
                {"detail": "O módulo de orçamento não está disponível nesta instalação."},
                status=status.HTTP_409_CONFLICT,
            )

        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        orcamento = Orcamento.objects.filter(tenant_id=tenant_id, pk=orcamento_id).first()
        if orcamento is None:
            return Response(
                {"orcamento": "Orçamento não encontrado."}, status=status.HTTP_404_NOT_FOUND,
            )

        tipo = request.data.get("tipo") or Demanda.Tipo.MATERIAL
        if tipo not in Demanda.Tipo.values:
            return Response(
                {"tipo": "Use 'material' ou 'servico'."}, status=status.HTTP_400_BAD_REQUEST,
            )

        centro = None
        if request.data.get("centro_custo"):
            centro = CentroCusto.objects.filter(
                tenant_id=tenant_id, pk=request.data["centro_custo"]
            ).first()

        try:
            resultado = demanda_do_orcamento(
                orcamento,
                tipo=tipo,
                centro_custo=centro,
                solicitante=getattr(request, "user", None),
                observacao=request.data.get("observacao") or "",
            )
        except GeracaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(resultado, status=status.HTTP_201_CREATED)


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

    # --- a proposta que o comprador digita (dono, 16/10/2026) ---------------------

    def _dados_da_proposta(self, request) -> dict:
        from rest_framework.exceptions import ValidationError

        from fornecedores.models import Fornecedor

        dados = request.data
        fornecedor = Fornecedor.objects.filter(pk=dados.get("fornecedor") or 0, tenant_id=self._tenant_id()).first()
        recebida = dados.get("recebida_em") or None
        prazo = dados.get("prazo_entrega_dias")
        try:
            recebida = date.fromisoformat(recebida) if recebida else None
            prazo = int(prazo) if prazo not in (None, "") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "Data ou prazo inválido."})
        return {
            "fornecedor": fornecedor, "itens": dados.get("itens") or [], "recebida_em": recebida,
            "prazo_entrega_dias": prazo, "observacao": dados.get("observacao") or "",
        }

    @action(detail=True, methods=["post"], url_path="propostas")
    def registrar_proposta(self, request, pk=None):
        """`{fornecedor, itens: [{item_demanda, preco_unitario}], recebida_em, prazo_entrega_dias, observacao}`."""
        from . import propostas

        cotacao = self.get_object()
        try:
            proposta = propostas.registrar(cotacao, **self._dados_da_proposta(request))
        except propostas.PropostaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PropostaSerializer(proposta, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put", "delete"], url_path=r"propostas/(?P<proposta_id>\d+)")
    def alterar_proposta(self, request, pk=None, proposta_id=None):
        """PUT reescreve a proposta (mesmo corpo do registrar); DELETE a apaga. Só com a cotação aberta."""
        from . import propostas

        cotacao = self.get_object()
        proposta = cotacao.propostas.filter(pk=proposta_id).first()
        if proposta is None:
            return Response({"detail": "Proposta não encontrada nesta cotação."}, status=status.HTTP_404_NOT_FOUND)
        try:
            if request.method == "DELETE":
                propostas.apagar(proposta)
                return Response(status=status.HTTP_204_NO_CONTENT)
            proposta = propostas.registrar(cotacao, proposta=proposta, **self._dados_da_proposta(request))
        except propostas.PropostaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PropostaSerializer(proposta, context=self.get_serializer_context()).data)

    # --- o mapa para a reunião ----------------------------------------------------

    def _mapa(self, cotacoes):
        from django.http import HttpResponse

        from .documento_cotacao import XLSX, nome_do_arquivo, pdf_dos_mapas, xlsx_dos_mapas

        formato = (self.request.query_params.get("formato") or "pdf").lower()
        try:
            if formato == "xlsx":
                conteudo, tipo = xlsx_dos_mapas(cotacoes), XLSX
            else:
                formato = "pdf"
                conteudo, tipo = pdf_dos_mapas(cotacoes), "application/pdf"
        except Exception as exc:  # noqa: BLE001 - motor de PDF fora do ar vira 503 legível
            return Response({"detail": f"Não foi possível gerar o mapa: {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        resposta = HttpResponse(conteudo, content_type=tipo)
        disposicao = "inline" if formato == "pdf" else "attachment"
        resposta["Content-Disposition"] = f'{disposicao}; filename="{nome_do_arquivo(cotacoes, formato)}"'
        return resposta

    @action(detail=True, methods=["get"])
    def mapa(self, request, pk=None):
        """O mapa comparativo desta cotação, `?formato=pdf|xlsx`."""
        return self._mapa([self.get_object()])

    @action(detail=False, methods=["get"])
    def mapas(self, request):
        """Várias cotações num arquivo: `?ids=1,2,3&formato=pdf|xlsx` — capa com o resumo e um mapa por cotação."""
        from payment.planos import SCM_MAPA_TETO_COTACOES

        try:
            ids = [int(x) for x in (request.query_params.get("ids") or "").split(",") if x.strip()]
        except ValueError:
            return Response({"detail": "Lista de cotações inválida."}, status=status.HTTP_400_BAD_REQUEST)
        if not ids:
            return Response({"detail": "Escolha ao menos uma cotação."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > SCM_MAPA_TETO_COTACOES:
            return Response({"detail": f"No máximo {SCM_MAPA_TETO_COTACOES} cotações por arquivo."},
                            status=status.HTTP_400_BAD_REQUEST)
        por_id = {c.pk: c for c in self.get_queryset().filter(pk__in=ids).select_related("demanda")}
        cotacoes = [por_id[i] for i in ids if i in por_id]
        if not cotacoes:
            return Response({"detail": "Nenhuma dessas cotações é da sua empresa."}, status=status.HTTP_404_NOT_FOUND)
        return self._mapa(cotacoes)


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
            ctx["distancia_km"] = self._distancias(qs)
        except Exception:  # pragma: no cover - contexto é otimização, nunca bloqueia
            pass
        return ctx

    def _distancias(self, qs) -> dict:
        """`(cotacao, fornecedor) → km` até o canteiro daquela cotação (MAP.2).

        A obra sai da cadeia `cotação → demanda → centro de custo → obra`: o SCM
        é vertical-agnóstico e não tem FK direta para obra, então a alocação é o
        caminho legítimo. Cotação cujo centro de custo não é de obra fica sem
        distância — o que está certo, porque "distância até o administrativo"
        não quer dizer nada.
        """
        from modulomaps.services import distancias_ate_obra

        tenant_id = self._tenant_id()
        # `list()` porque a tupla é percorrida duas vezes — sem materializar, o
        # `values_list` reexecuta a consulta na segunda passada.
        pares = list(qs.exclude(fornecedor_id=None).values_list(
            "cotacao_id", "fornecedor_id", "cotacao__demanda__centro_custo__obra_id"
        ))
        por_obra: dict[int, set] = {}
        for _cotacao_id, fornecedor_id, obra_id in pares:
            if obra_id:
                por_obra.setdefault(obra_id, set()).add(fornecedor_id)

        distancias = {
            obra_id: distancias_ate_obra(tenant_id, obra_id, fornecedores)
            for obra_id, fornecedores in por_obra.items()
        }
        return {
            (cotacao_id, fornecedor_id): distancias[obra_id][fornecedor_id]
            for cotacao_id, fornecedor_id, obra_id in pares
            if obra_id and fornecedor_id in distancias.get(obra_id, {})
        }


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
    # D284 — os verbos do pedido reusam as permissões que já existem (permissão
    # nova exige rebuild da IAM + re-seed): receber e lançar a nota são do
    # recebimento; cobrança, edição, cancelamento e envio são escrita do pedido;
    # cadastrar o item que se está comprando é parte do gesto de comprar.
    action_permission_map = {
        "comprar_direto": "scm.pedido.criar",
        "gerar_de_cotacao": "scm.pedido.criar",
        "compra_avulsa": "scm.pedido.criar",
        "cadastrar_item": "scm.pedido.criar",
        "receber": "scm.recebimento.edit",
        "lancar_nota": "scm.recebimento.edit",
        "definir_cobranca": "scm.pedido.edit",
        "editar": "scm.pedido.edit",
        "cancelar": "scm.pedido.edit",
        "enviar": "scm.pedido.edit",
        "painel": "scm.pedido.view",
        "pdf": "scm.pedido.view",
    }

    # --- D284: o pedido inteiro numa resposta, e os verbos dele -------------

    @action(detail=True, methods=["get"])
    def painel(self, request, pk=None):
        """Tudo o que a tela do pedido mostra: linhas com saldo, recebimentos,
        notas, cobrança, títulos do ERP, histórico e o que está pendente."""
        from . import cobranca as cobranca_mod
        from . import financeiro
        from .edicao import regime
        from .recebimento import saldos

        pedido = self.get_object()
        linhas = saldos(pedido)
        recebimentos = []
        for r in pedido.recebimentos.prefetch_related("itens__item_pedido__produto", "notas_fiscais").select_related("recebido_por").order_by("-data", "-recebimento_id"):
            recebimentos.append({
                "recebimento_id": r.recebimento_id, "data": r.data.isoformat(), "tipo": r.tipo,
                "encerrou_saldo": r.encerrou_saldo, "local_entrega": r.local_entrega, "observacao": r.observacao,
                "nota_fiscal_ref": r.nota_fiscal_ref,
                "recebido_por": (r.recebido_por.get_full_name() or r.recebido_por.username) if r.recebido_por else "",
                "itens": [{
                    "item_pedido": i.item_pedido_id,
                    "descricao": i.item_pedido.produto.descricao if i.item_pedido.produto_id else i.item_pedido.descricao,
                    "quantidade": str(i.quantidade_recebida),
                } for i in r.itens.all()],
                "notas": [n.nota_id for n in r.notas_fiscais.all()],
            })
        notas = NotaFiscalCompraSerializer(pedido.notas_fiscais.order_by("-criado_em"), many=True).data
        resumo_cobranca = cobranca_mod.resumo(pedido)
        titulos = [{
            "conta_pagar_id": c.pk, "descricao": c.descricao, "valor": str(c.valor), "valor_pago": str(c.valor_pago),
            "status": c.status, "data_vencimento": c.data_vencimento.isoformat(), "nfe_situacao": c.nfe_situacao,
        } for c in financeiro.titulos(pedido, vivos=False)]
        chegou = any(l["recebido"] > 0 for l in linhas)
        situacoes = {n["situacao"] for n in notas}
        pendencias = []
        if chegou and not notas:
            pendencias.append("aguardando_nfe")
        if "aguardando_documento" in situacoes:
            pendencias.append("nfe_aguardando_documento")
        if "divergente" in situacoes:
            pendencias.append("nfe_divergente")
        if pedido.status != PedidoCompra.Status.CANCELADO:
            if not resumo_cobranca["meios"]:
                pendencias.append("sem_cobranca")
            elif not resumo_cobranca["confere"]:
                pendencias.append("cobranca_nao_confere")
        return Response({
            "pedido": self.get_serializer(pedido).data,
            "regime": regime(pedido),
            "linhas": [{**l, **{k: str(l[k]) for k in ("quantidade", "recebido", "encerrado", "pendente", "excedente", "preco_unitario")},
                        "subtotal": str((l["quantidade"] * l["preco_unitario"]).quantize(Decimal("0.01")))} for l in linhas],
            "recebimentos": recebimentos,
            "notas": notas,
            "cobranca": resumo_cobranca,
            "titulos": titulos,
            "eventos": EventoPedidoSerializer(pedido.eventos.select_related("autor")[:100], many=True).data,
            "pendencias": pendencias,
            "fornecedor_contato": {
                "email": pedido.fornecedor.email or "", "telefone": pedido.fornecedor.telefone or "",
            },
        })

    @staticmethod
    def _itens_do_corpo(request):
        """`itens` vem como lista (JSON) ou como texto JSON (multipart, quando a
        nota vem anexada no mesmo envio)."""
        import json

        itens = request.data.get("itens")
        if isinstance(itens, str):
            try:
                itens = json.loads(itens or "[]")
            except ValueError:
                itens = None
        return itens

    @action(detail=True, methods=["post"])
    def receber(self, request, pk=None):
        """Recebe linha por linha — a entrada no estoque sai daqui (D284)."""
        from .notas import NotaInvalida
        from .recebimento import RecebimentoInvalido, receber

        pedido = self.get_object()
        encerrar = str(request.data.get("encerrar") or "").lower() in ("1", "true", "sim", "on")
        nota = {
            "numero": request.data.get("nf_numero") or "", "serie": request.data.get("nf_serie") or "",
            "chave": request.data.get("nf_chave") or "",
            "xml_arquivo": request.FILES.get("nf_xml"), "pdf_arquivo": request.FILES.get("nf_pdf"),
        }
        try:
            resultado = receber(
                pedido, itens=self._itens_do_corpo(request), data=request.data.get("data"),
                local_entrega=request.data.get("local_entrega") or "", observacao=request.data.get("observacao") or "",
                encerrar=encerrar, autor=request.user, nota=nota,
            )
        except (RecebimentoInvalido, NotaInvalida) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="notas")
    def lancar_nota(self, request, pk=None):
        """Lança a NF-e da compra: número, chave e/ou documento (XML, PDF)."""
        from .notas import NotaInvalida, lancar_nota

        pedido = self.get_object()
        recebimento = None
        if request.data.get("recebimento"):
            recebimento = pedido.recebimentos.filter(pk=request.data["recebimento"]).first()
        try:
            nota = lancar_nota(
                pedido, numero=request.data.get("numero") or "", serie=request.data.get("serie") or "",
                chave=request.data.get("chave") or "", recebimento=recebimento,
                xml_arquivo=request.FILES.get("xml"), pdf_arquivo=request.FILES.get("pdf"), autor=request.user,
            )
        except NotaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(NotaFiscalCompraSerializer(nota).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cobranca")
    def definir_cobranca(self, request, pk=None):
        """Define (ou redefine) a cobrança e gera os títulos no ERP."""
        from .cobranca import CobrancaInvalida, definir_cobranca, resumo

        pedido = self.get_object()
        if pedido.status == PedidoCompra.Status.CANCELADO:
            return Response({"detail": "Pedido cancelado não tem cobrança."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            titulos = definir_cobranca(pedido, request.data.get("meios"), autor=request.user)
        except CobrancaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"titulos": titulos, "cobranca": resumo(pedido)}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def editar(self, request, pk=None):
        from .edicao import EdicaoInvalida, editar

        pedido = self.get_object()
        try:
            mudancas = editar(pedido, request.data, autor=request.user)
        except EdicaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        pedido.refresh_from_db()
        return Response({"mudancas": mudancas, "pedido": self.get_serializer(pedido).data})

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        from .edicao import EdicaoInvalida, cancelar

        pedido = self.get_object()
        try:
            resultado = cancelar(pedido, motivo=request.data.get("motivo") or "", autor=request.user)
        except EdicaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """O PDF do pedido para o fornecedor."""
        from django.http import HttpResponse

        from .documento_pedido import nome_do_arquivo, pdf_do_pedido

        pedido = self.get_object()
        try:
            conteudo = pdf_do_pedido(pedido)
        except Exception as exc:  # noqa: BLE001 - motor de PDF fora do ar vira 503 legível
            return Response({"detail": f"Não foi possível gerar o PDF: {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        resposta = HttpResponse(conteudo, content_type="application/pdf")
        resposta["Content-Disposition"] = f'inline; filename="{nome_do_arquivo(pedido)}"'
        return resposta

    @action(detail=True, methods=["post"])
    def enviar(self, request, pk=None):
        """`{canal: email, para}` envia daqui com o PDF; `whatsapp`/`impresso`
        só registram que o pedido saiu (o envio foi pelo navegador)."""
        from .documento_pedido import EnvioIndisponivel, enviar_por_email, marcar_enviado

        pedido = self.get_object()
        canal = request.data.get("canal") or ""
        para = (request.data.get("para") or "").strip()
        if canal == "email":
            if "@" not in para:
                return Response({"detail": "Informe o e-mail do fornecedor."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                enviar_por_email(pedido, para=para, autor=request.user)
            except EnvioIndisponivel as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        elif canal in ("whatsapp", "impresso"):
            marcar_enviado(pedido, canal=canal, para=para, autor=request.user)
        else:
            return Response({"detail": "Canal: email, whatsapp ou impresso."}, status=status.HTTP_400_BAD_REQUEST)
        pedido.refresh_from_db()
        return Response(self.get_serializer(pedido).data)

    @action(detail=False, methods=["post"])
    def cadastrar_item(self, request):
        """O item que é só texto vira item do catálogo — e loja dele (D284).

        `{descricao, unidade, tipo?, fornecedor?, preco?, item_pedido?}`. Com
        `fornecedor` e `preco`, registra também a oferta daquele fornecedor; com
        `item_pedido`, liga a linha do pedido ao item novo.
        """
        from catalogo.models import Item as ItemCatalogo
        from catalogo.registro import TextoInvalido, registrar_item_proprio
        from fornecedores.models import Fornecedor

        tid = self._tenant_id()
        linha = None
        if request.data.get("item_pedido"):
            linha = ItemPedido.objects.filter(tenant_id=tid, pk=request.data["item_pedido"]).select_related("pedido").first()
            if linha is None:
                return Response({"detail": "Linha do pedido não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        descricao = request.data.get("descricao") or (linha.descricao if linha else "")
        unidade = request.data.get("unidade") or (linha.unidade if linha else "")
        tipo = request.data.get("tipo") or ItemCatalogo.Tipo.MATERIAL
        if tipo not in ItemCatalogo.Tipo.values:
            return Response({"detail": "Tipo de item inválido."}, status=status.HTTP_400_BAD_REQUEST)
        fornecedor_id = request.data.get("fornecedor") or (linha.pedido.fornecedor_id if linha else None)
        detalhe = f"Pedido de compra #{linha.pedido_id}" if linha else "Compra (Suprimentos)"
        try:
            item, criado = registrar_item_proprio(
                tenant_id=tid, descricao=descricao, unidade=unidade, tipo=tipo,
                origem=ItemCatalogo.Origem.COMPRA, origem_detalhe=detalhe, usuario=request.user,
            )
        except TextoInvalido as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        oferta = None
        preco = request.data.get("preco")
        if preco in (None, "") and linha is not None:
            preco = linha.preco_unitario
        fornecedor = Fornecedor.objects.filter(tenant_id=tid, pk=fornecedor_id).first() if fornecedor_id else None
        if fornecedor is not None and preco not in (None, ""):
            try:
                valor = Decimal(str(preco).replace(",", ".")).quantize(Decimal("0.01"))
            except (InvalidOperation, TypeError):
                valor = None
            if valor is not None and valor >= 0:
                oferta, _ = OfertaFornecedor.objects.get_or_create(
                    tenant_id=tid, produto=item, fornecedor=fornecedor,
                    defaults={"preco_direto": valor},
                )
        if linha is not None:
            linha.produto = item
            linha.descricao = ""
            linha.unidade = item.unidade
            linha.save(update_fields=["produto", "descricao", "unidade"])
        return Response({
            "item_id": item.item_id, "codigo_interno": item.codigo_interno, "descricao": item.descricao,
            "unidade": item.unidade, "criado": criado, "oferta": oferta.oferta_id if oferta else None,
        }, status=status.HTTP_201_CREATED if criado else status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def compra_avulsa(self, request):
        """**Comprar sem catálogo e sem cotação** — fornecedor, itens, preço.

        *Achado do dono, 10/10/2026:* "continuo sem poder comprar". As duas vias
        que existiam pediam algo prévio: uma oferta publicada no catálogo
        (compra direta) ou uma demanda que virasse cotação. Obra comprando areia
        do depósito da esquina não tem nem um nem outro. Esta via grava o pedido
        como a obra o faz: fornecedor, o que se comprou (item do catálogo ou
        texto), quantidade e preço — e daí segue igual aos outros (recebimento
        entra no estoque, avaliação do fornecedor).
        """
        from fornecedores.models import Fornecedor

        tid = self._tenant_id()
        fornecedor = Fornecedor.objects.filter(pk=request.data.get("fornecedor") or 0, tenant_id=tid).first()
        if fornecedor is None:
            return Response({"detail": "Escolha o fornecedor."}, status=status.HTTP_400_BAD_REQUEST)
        itens = request.data.get("itens") or []
        if not isinstance(itens, list) or not itens:
            return Response({"detail": "Inclua ao menos um item."}, status=status.HTTP_400_BAD_REQUEST)

        linhas, problemas = [], []
        for n, linha in enumerate(itens, start=1):
            produto = None
            if linha.get("produto"):
                produto = Item.objects.filter(pk=linha["produto"], tenant_id=tid).first()
                if produto is None:
                    problemas.append(f"Item {n}: produto não encontrado.")
                    continue
            descricao = (linha.get("descricao") or "").strip()[:255]
            if produto is None and not descricao:
                problemas.append(f"Item {n}: diga o que está sendo comprado.")
                continue
            try:
                quantidade = Decimal(str(linha.get("quantidade")).replace(",", "."))
                preco = Decimal(str(linha.get("preco_unitario") or "0").replace(",", "."))
            except (InvalidOperation, TypeError):
                problemas.append(f"Item {n}: quantidade ou preço inválido.")
                continue
            if quantidade <= 0 or preco < 0:
                problemas.append(f"Item {n}: quantidade precisa ser positiva e preço não pode ser negativo.")
                continue
            unidade = (produto.unidade if produto else (linha.get("unidade") or "").strip())[:20]
            linhas.append((produto, descricao, unidade, quantidade, preco))
        if problemas:
            return Response({"detail": " ".join(problemas)}, status=status.HTTP_400_BAD_REQUEST)

        centro_custo = None
        if request.data.get("centro_custo"):
            centro_custo = CentroCusto.objects.filter(pk=request.data["centro_custo"], tenant_id=tid).first()

        # Compra feita a partir de uma demanda: o pedido a referencia e ela fica atendida.
        demanda = None
        if request.data.get("demanda"):
            demanda = Demanda.objects.filter(pk=request.data["demanda"], tenant_id=tid).first()
            if demanda is None:
                return Response({"detail": "Demanda não encontrada."}, status=status.HTTP_400_BAD_REQUEST)
            centro_custo = centro_custo or demanda.centro_custo

        with transaction.atomic():
            pedido = PedidoCompra.objects.create(
                tenant_id=tid, origem=PedidoCompra.Origem.MANUAL, fornecedor=fornecedor, demanda=demanda,
                centro_custo=centro_custo, status=PedidoCompra.Status.APROVADO,
                data_entrega_prevista=request.data.get("data_entrega_prevista") or None,
                observacao=(request.data.get("observacao") or "")[:2000],
                valor_total=sum((q * p for _, _, _, q, p in linhas), Decimal("0")).quantize(Decimal("0.01")),
            )
            ItemPedido.objects.bulk_create([
                ItemPedido(tenant_id=tid, pedido=pedido, produto=produto, descricao=descricao,
                           unidade=unidade, quantidade=quantidade, preco_unitario=preco)
                for produto, descricao, unidade, quantidade, preco in linhas
            ])
            if demanda is not None:
                # Só fecha a demanda (e a cotação aberta dela) quando os pedidos cobrem
                # todas as linhas; comprou parte, o resto continua na fila.
                from .saldo_demanda import atualizar_status
                atualizar_status(demanda)
        _registrar_criacao(pedido, f"Pedido criado (compra avulsa) — R$ {pedido.valor_total}.", request.user)
        return Response(self.get_serializer(pedido).data, status=status.HTTP_201_CREATED)

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
        _registrar_criacao(pedido, f"Pedido criado por compra direta da oferta #{oferta.pk} — R$ {pedido.valor_total}.", request.user)
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
        _registrar_criacao(pedido, f"Pedido criado da cotação #{cotacao.pk} — R$ {pedido.valor_total}.", request.user)
        return Response(self.get_serializer(pedido).data, status=status.HTTP_201_CREATED)


def _registrar_criacao(pedido, texto, autor):
    from . import financeiro
    from .models import EventoPedido

    financeiro.registrar_evento(pedido, EventoPedido.Tipo.CRIADO, texto, autor=autor)


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


class NotaFiscalCompraViewSet(BaseScmViewSet):
    """As NF-e das compras. Criar é pelo pedido (`pedidos/{id}/notas/`); aqui se
    lista e anexa o documento que faltava. O arquivo sai pela porta única
    (`moduloscm.impexp`, `url_xml`/`url_pdf` no JSON)."""

    queryset = NotaFiscalCompra.objects.all().order_by("-criado_em")
    serializer_class = NotaFiscalCompraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["pedido", "recebimento", "situacao"]
    ordering_fields = ["criado_em", "numero"]
    required_resource = "scm.recebimento"
    http_method_names = ["get", "post", "head", "options"]
    action_permission_map = {"documento": "scm.recebimento.edit", "corrigir": "scm.recebimento.edit",
                             "remover": "scm.recebimento.edit"}

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Lance a nota pelo pedido."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"])
    def documento(self, request, pk=None):
        """Anexa o XML e/ou o PDF (e a chave) e confere de novo."""
        from .notas import NotaInvalida, anexar_documento

        nota = self.get_object()
        try:
            nota = anexar_documento(
                nota, chave=request.data.get("chave") or "", xml_arquivo=request.FILES.get("xml"),
                pdf_arquivo=request.FILES.get("pdf"), autor=request.user,
            )
        except NotaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(nota).data)

    @action(detail=True, methods=["post"])
    def corrigir(self, request, pk=None):
        """Corrige número, série e chave de uma nota lançada errada."""
        from .notas import NotaInvalida, corrigir_nota

        nota = self.get_object()
        try:
            nota = corrigir_nota(
                nota, numero=request.data.get("numero") or "", serie=request.data.get("serie") or "",
                chave=request.data.get("chave") or "", autor=request.user,
            )
        except NotaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(nota).data)

    @action(detail=True, methods=["post"])
    def remover(self, request, pk=None):
        """Tira a nota do pedido (lançada por engano). Fica no histórico e no ERP."""
        from .notas import remover_nota

        remover_nota(self.get_object(), motivo=(request.data.get("motivo") or "")[:300], autor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                "produtosAtivos": Item.objects.filter(tenant_id=tid, ativo=True).count(),
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
