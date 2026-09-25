# backend/modulosil/views.py
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.busca import BuscaSemAcento
from rest_framework import filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogo.models import Item
from nucleo import autorizacao
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from . import services
from .models import (
    Devolucao,
    EmprestimoFerramenta,
    EntregaEPI,
    Ferramenta,
    Inventario,
    ItemDevolucao,
    ItemInventario,
    ItemRequisicao,
    ItemTransferencia,
    LocalEstoque,
    Lote,
    MovimentacaoEstoque,
    Requisicao,
    SaldoEstoque,
    Transferencia,
)
from .pagination import SilPageNumberPagination
from .serializers import (
    DevolucaoSerializer,
    EmprestimoFerramentaSerializer,
    EntregaEPISerializer,
    FerramentaSerializer,
    InventarioSerializer,
    ItemDevolucaoSerializer,
    ItemInventarioSerializer,
    ItemRequisicaoSerializer,
    ItemTransferenciaSerializer,
    LocalEstoqueSerializer,
    LoteSerializer,
    MovimentacaoEstoqueSerializer,
    RequisicaoSerializer,
    SaldoEstoqueSerializer,
    TransferenciaSerializer,
)


class SilStatusView(views.APIView):
    """Status do módulo SIL. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "sil"

    def get(self, request):
        return Response({"modulo": "sil", "status": "ativo"})


class _SilPermsMixin:
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "sil"
    pagination_class = SilPageNumberPagination

    def _tenant_id(self):
        return getattr(getattr(self.request, "user", None), "tenant_id", None)

    def _pertence(self, model, pk):
        return model.objects.filter(tenant_id=self._tenant_id(), pk=pk).exists()


class BaseSilViewSet(TenantScopedViewSetMixin, _SilPermsMixin, viewsets.ModelViewSet):
    pass


class BaseSilReadOnlyViewSet(TenantScopedViewSetMixin, _SilPermsMixin, viewsets.ReadOnlyModelViewSet):
    pass


class LocalEstoqueViewSet(BaseSilViewSet):
    queryset = LocalEstoque.objects.all().order_by("nome")
    serializer_class = LocalEstoqueSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["tipo", "ativo", "obra", "empreendimento"]
    search_fields = ["nome", "endereco"]
    ordering_fields = ["nome"]
    required_resource = "sil.local"


class LoteViewSet(BaseSilViewSet):
    queryset = Lote.objects.all().order_by("item", "validade")
    serializer_class = LoteSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["item", "fornecedor"]
    search_fields = ["numero_lote"]
    ordering_fields = ["validade", "numero_lote"]
    required_resource = "sil.lote"


class SaldoEstoqueViewSet(BaseSilReadOnlyViewSet):
    """Saldo é read-only na API (só o ledger o altera). `definir_minimo` edita o
    ponto de reposição; `gerar_demanda` dispara a reposição no SCM."""

    queryset = SaldoEstoque.objects.select_related("item", "local").all().order_by("item")
    serializer_class = SaldoEstoqueSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["item", "local"]
    search_fields = ["item__descricao", "item__codigo_interno"]
    ordering_fields = ["quantidade"]
    required_resource = "sil.saldo"
    action_permission_map = {"definir_minimo": "sil.saldo.edit", "gerar_demanda": "sil.saldo.edit"}

    def get_queryset(self):
        qs = super().get_queryset()
        if str(self.request.query_params.get("abaixo_minimo")).lower() in ("1", "true"):
            qs = qs.filter(ponto_reposicao__gt=0, quantidade__lte=F("ponto_reposicao"))
        return qs

    @action(detail=True, methods=["post"])
    def definir_minimo(self, request, pk=None):
        saldo = self.get_object()
        try:
            saldo.ponto_reposicao = Decimal(str(request.data.get("ponto_reposicao")))
        except (InvalidOperation, TypeError):
            return Response({"detail": "Ponto de reposição inválido."}, status=status.HTTP_400_BAD_REQUEST)
        saldo.save(update_fields=["ponto_reposicao"])
        return Response(self.get_serializer(saldo).data)

    @action(detail=True, methods=["post"])
    def gerar_demanda(self, request, pk=None):
        """Cria uma Demanda (origem=estoque) no SCM para repor o item."""
        saldo = self.get_object()
        raw = request.data.get("quantidade")
        try:
            quantidade = Decimal(str(raw)) if raw is not None else (saldo.ponto_reposicao or Decimal("1"))
        except (InvalidOperation, TypeError):
            return Response({"detail": "Quantidade inválida."}, status=status.HTTP_400_BAD_REQUEST)
        if quantidade <= 0:
            quantidade = saldo.ponto_reposicao or Decimal("1")
        demanda = services.gerar_demanda_de_saldo(saldo, quantidade, request.user)
        return Response(
            {"demanda_id": demanda.demanda_id, "status": demanda.status, "quantidade": str(quantidade)},
            status=status.HTTP_201_CREATED,
        )


class MovimentacaoEstoqueViewSet(BaseSilReadOnlyViewSet):
    """Ledger read-only. Movimentos manuais entram por `registrar/` (via services,
    que atualizam o saldo) — nunca por POST direto ao modelo."""

    queryset = MovimentacaoEstoque.objects.select_related("item", "local").all()
    serializer_class = MovimentacaoEstoqueSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["item", "local", "tipo", "obra", "etapa", "recebimento_scm_ref"]
    ordering_fields = ["criado_em"]
    required_resource = "sil.movimentacao"
    action_permission_map = {"registrar": "sil.movimentacao.edit"}

    @action(detail=False, methods=["post"])
    def registrar(self, request):
        tid = self._tenant_id()
        d = request.data
        item, local, tipo = d.get("item"), d.get("local"), d.get("tipo")
        if not (item and local and tipo):
            return Response({"detail": "item, local e tipo são obrigatórios."}, status=status.HTTP_400_BAD_REQUEST)
        if not self._pertence(Item, item) or not self._pertence(LocalEstoque, local):
            return Response({"detail": "Item ou local inexistente."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            quantidade = Decimal(str(d.get("quantidade")))
        except (InvalidOperation, TypeError):
            return Response({"detail": "Quantidade inválida."}, status=status.HTTP_400_BAD_REQUEST)
        if quantidade <= 0 and tipo != MovimentacaoEstoque.Tipo.AJUSTE:
            return Response({"detail": "Quantidade deve ser positiva."}, status=status.HTTP_400_BAD_REQUEST)

        obra_id = d.get("obra") or None
        etapa_id = d.get("etapa") or None
        lote_id = d.get("lote") or None
        observacao = d.get("observacao", "")
        custo = d.get("custo_unitario") or 0
        try:
            if tipo == MovimentacaoEstoque.Tipo.ENTRADA:
                mov = services.aplicar_entrada(tid, item, local, quantidade, custo, usuario=request.user, obra_id=obra_id, etapa_id=etapa_id, lote_id=lote_id, observacao=observacao)
            elif tipo == MovimentacaoEstoque.Tipo.SAIDA:
                mov = services.aplicar_saida(tid, item, local, quantidade, usuario=request.user, obra_id=obra_id, etapa_id=etapa_id, lote_id=lote_id, observacao=observacao)
            elif tipo == MovimentacaoEstoque.Tipo.AJUSTE:
                mov = services.aplicar_ajuste(tid, item, local, quantidade, custo_unitario=(custo or None), usuario=request.user, obra_id=obra_id, etapa_id=etapa_id, lote_id=lote_id, observacao=observacao)
            else:
                return Response({"detail": "Tipo inválido (use entrada/saida/ajuste)."}, status=status.HTTP_400_BAD_REQUEST)
        except services.EstoqueInsuficiente as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if mov is None:
            return Response({"detail": "Sem alteração de saldo."}, status=status.HTTP_200_OK)
        return Response(self.get_serializer(mov).data, status=status.HTTP_201_CREATED)


class RequisicaoViewSet(BaseSilViewSet):
    queryset = Requisicao.objects.all().order_by("-criado_em")
    serializer_class = RequisicaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "obra", "local", "solicitante"]
    ordering_fields = ["criado_em", "status"]
    required_resource = "sil.requisicao"
    action_permission_map = {"aprovar": "sil.requisicao.aprovar", "atender": "sil.requisicao.atender"}

    def perform_create(self, serializer):
        user = getattr(self.request, "user", None)
        extra = {}
        if not serializer.validated_data.get("solicitante"):
            extra["solicitante"] = user
        serializer.save(tenant_id=getattr(user, "tenant_id", None), **extra)

    @action(detail=True, methods=["post"])
    def aprovar(self, request, pk=None):
        req = self.get_object()
        if req.status not in (Requisicao.Status.RASCUNHO, Requisicao.Status.PENDENTE):
            return Response({"detail": "Só requisições em rascunho/pendentes podem ser aprovadas."}, status=status.HTTP_400_BAD_REQUEST)
        services.aprovar_requisicao(req, request.user)
        return Response(self.get_serializer(req).data)

    @action(detail=True, methods=["post"])
    def atender(self, request, pk=None):
        req = self.get_object()
        if req.status not in (Requisicao.Status.APROVADA, Requisicao.Status.PARCIAL):
            return Response({"detail": "Aprove a requisição antes de atender."}, status=status.HTTP_400_BAD_REQUEST)
        services.atender_requisicao(req)
        return Response(self.get_serializer(req).data)


class ItemRequisicaoViewSet(BaseSilViewSet):
    queryset = ItemRequisicao.objects.all().order_by("item_requisicao_id")
    serializer_class = ItemRequisicaoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["requisicao", "item"]
    required_resource = "sil.requisicao"
    pagination_class = None


class TransferenciaViewSet(BaseSilViewSet):
    queryset = Transferencia.objects.all().order_by("-criado_em")
    serializer_class = TransferenciaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["origem", "destino", "status"]
    ordering_fields = ["criado_em"]
    required_resource = "sil.transferencia"
    action_permission_map = {"executar": "sil.transferencia.executar"}

    @action(detail=True, methods=["post"])
    def executar(self, request, pk=None):
        transf = self.get_object()
        if transf.status != Transferencia.Status.RASCUNHO:
            return Response({"detail": "Transferência já executada/cancelada."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            services.executar_transferencia(transf)
        except services.EstoqueInsuficiente as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(transf).data)


class ItemTransferenciaViewSet(BaseSilViewSet):
    queryset = ItemTransferencia.objects.all().order_by("item_transferencia_id")
    serializer_class = ItemTransferenciaSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["transferencia", "item"]
    required_resource = "sil.transferencia"
    pagination_class = None


class DevolucaoViewSet(BaseSilViewSet):
    queryset = Devolucao.objects.all().order_by("-criado_em")
    serializer_class = DevolucaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["tipo", "status", "fornecedor", "local"]
    ordering_fields = ["criado_em"]
    required_resource = "sil.devolucao"
    action_permission_map = {"executar": "sil.devolucao.executar"}

    @action(detail=True, methods=["post"])
    def executar(self, request, pk=None):
        dev = self.get_object()
        if dev.status != Devolucao.Status.RASCUNHO:
            return Response({"detail": "Devolução já executada/cancelada."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            services.executar_devolucao(dev)
        except services.EstoqueInsuficiente as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(dev).data)


class ItemDevolucaoViewSet(BaseSilViewSet):
    queryset = ItemDevolucao.objects.all().order_by("item_devolucao_id")
    serializer_class = ItemDevolucaoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["devolucao", "item"]
    required_resource = "sil.devolucao"
    pagination_class = None


class InventarioViewSet(BaseSilViewSet):
    queryset = Inventario.objects.all().order_by("-criado_em")
    serializer_class = InventarioSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["local", "status", "tipo"]
    ordering_fields = ["criado_em"]
    required_resource = "sil.inventario"
    action_permission_map = {"fechar": "sil.inventario.fechar"}

    def perform_create(self, serializer):
        user = getattr(self.request, "user", None)
        serializer.save(tenant_id=getattr(user, "tenant_id", None), usuario=user if getattr(user, "pk", None) else None)

    @action(detail=True, methods=["post"])
    def fechar(self, request, pk=None):
        inv = self.get_object()
        if inv.status == Inventario.Status.FECHADO:
            return Response({"detail": "Inventário já fechado."}, status=status.HTTP_400_BAD_REQUEST)
        services.fechar_inventario(inv)
        return Response(self.get_serializer(inv).data)


class ItemInventarioViewSet(BaseSilViewSet):
    queryset = ItemInventario.objects.all().order_by("item_inventario_id")
    serializer_class = ItemInventarioSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["inventario", "item"]
    required_resource = "sil.inventario"
    pagination_class = None


class EntregaEPIViewSet(BaseSilViewSet):
    """Entrega de EPI (NR-6). Ao entregar, opcionalmente baixa do estoque
    (`baixar_estoque`). `devolver` encerra a entrega."""

    queryset = EntregaEPI.objects.select_related("item", "colaborador", "local", "obra").all().order_by("-data_entrega", "-entrega_epi_id")
    serializer_class = EntregaEPISerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["item", "colaborador", "status", "obra", "local"]
    search_fields = ["colaborador_nome", "ca_numero", "item__descricao"]
    ordering_fields = ["data_entrega", "ca_validade"]
    required_resource = "sil.epi"
    action_permission_map = {"devolver": "sil.epi.edit"}

    def perform_create(self, serializer):
        user = getattr(self.request, "user", None)
        entrega = serializer.save(tenant_id=getattr(user, "tenant_id", None))
        if str(self.request.data.get("baixar_estoque")).lower() in ("1", "true") and entrega.local_id:
            try:
                services.aplicar_saida(
                    entrega.tenant_id, entrega.item_id, entrega.local_id, entrega.quantidade,
                    usuario=user if getattr(user, "pk", None) else None, obra_id=entrega.obra_id,
                    observacao=f"Entrega de EPI #{entrega.entrega_epi_id}",
                )
                entrega.baixou_estoque = True
                entrega.save(update_fields=["baixou_estoque"])
            except services.EstoqueInsuficiente:
                pass

    @action(detail=True, methods=["post"])
    def devolver(self, request, pk=None):
        entrega = self.get_object()
        entrega.status = EntregaEPI.Status.DEVOLVIDO
        entrega.data_devolucao = timezone.localdate()
        entrega.save(update_fields=["status", "data_devolucao"])
        return Response(self.get_serializer(entrega).data)


class FerramentaViewSet(BaseSilViewSet):
    queryset = Ferramenta.objects.select_related("item", "local").all().order_by("nome")
    serializer_class = FerramentaSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["estado", "local", "calibravel", "item"]
    search_fields = ["nome", "patrimonio"]
    ordering_fields = ["nome", "proxima_calibracao", "proxima_manutencao"]
    required_resource = "sil.ferramenta"
    action_permission_map = {"alterar_estado": "sil.ferramenta.edit"}

    @action(detail=True, methods=["post"])
    def alterar_estado(self, request, pk=None):
        """Manutenção/calibração/baixa: muda o estado e atualiza as próximas datas."""
        ferr = self.get_object()
        novo = request.data.get("estado")
        if novo not in Ferramenta.Estado.values:
            return Response({"detail": "Estado inválido."}, status=status.HTTP_400_BAD_REQUEST)
        ferr.estado = novo
        for campo in ("proxima_calibracao", "proxima_manutencao"):
            if campo in request.data:
                setattr(ferr, campo, request.data.get(campo) or None)
        ferr.save()
        return Response(self.get_serializer(ferr).data)


class EmprestimoFerramentaViewSet(BaseSilViewSet):
    """Comodato: emprestar (marca a ferramenta EMPRESTADA) e `devolver`
    (DISPONÍVEL). Gateado pela mesma permissão da ferramentaria."""

    queryset = EmprestimoFerramenta.objects.select_related("ferramenta", "colaborador", "obra").all().order_by("-data_emprestimo", "-emprestimo_id")
    serializer_class = EmprestimoFerramentaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["ferramenta", "colaborador", "status", "obra"]
    ordering_fields = ["data_emprestimo", "data_prevista_devolucao"]
    required_resource = "sil.ferramenta"
    action_permission_map = {"devolver": "sil.ferramenta.edit"}

    def perform_create(self, serializer):
        user = getattr(self.request, "user", None)
        emp = serializer.save(tenant_id=getattr(user, "tenant_id", None))
        Ferramenta.objects.filter(pk=emp.ferramenta_id).update(estado=Ferramenta.Estado.EMPRESTADA)

    @action(detail=True, methods=["post"])
    def devolver(self, request, pk=None):
        emp = self.get_object()
        if emp.status == EmprestimoFerramenta.Status.DEVOLVIDA:
            return Response({"detail": "Empréstimo já devolvido."}, status=status.HTTP_400_BAD_REQUEST)
        emp.status = EmprestimoFerramenta.Status.DEVOLVIDA
        emp.data_devolucao = timezone.localdate()
        emp.save(update_fields=["status", "data_devolucao"])
        Ferramenta.objects.filter(pk=emp.ferramenta_id).update(estado=Ferramenta.Estado.DISPONIVEL)
        return Response(self.get_serializer(emp).data)


class CurvaABCView(views.APIView):
    """Curva ABC de materiais: classifica os itens em A/B/C pelo peso no valor
    total em estoque (A ≈ 80% do valor, B ≈ 15%, C ≈ 5%). Analítico de gestão."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "sil"
    required_permission = "sil.relatorio.view"

    def get(self, request):
        tid = getattr(request.user, "tenant_id", None)
        dec = DecimalField(max_digits=20, decimal_places=4)
        linhas = list(
            SaldoEstoque.objects.filter(tenant_id=tid, quantidade__gt=0)
            .values("item_id", "item__descricao", "item__codigo_interno", "item__unidade")
            .annotate(
                qtd_total=Coalesce(Sum("quantidade", output_field=dec), Decimal("0"), output_field=dec),
                valor=Coalesce(Sum(F("quantidade") * F("custo_medio"), output_field=dec), Decimal("0"), output_field=dec),
            )
            .order_by("-valor")
        )
        total = sum((l["valor"] for l in linhas), Decimal("0"))
        acum = Decimal("0")
        itens = []
        for l in linhas:
            valor = l["valor"]
            # Classe pela acumulada ANTES do item: o item que cruza 80% ainda é A
            # (convenção da curva ABC — o de maior valor é sempre A).
            pct_before = (acum / total * 100) if total > 0 else Decimal("0")
            classe = "A" if pct_before < 80 else ("B" if pct_before < 95 else "C")
            acum += valor
            pct_acum = (acum / total * 100) if total > 0 else Decimal("0")
            itens.append({
                "item": l["item_id"], "descricao": l["item__descricao"], "codigo": l["item__codigo_interno"],
                "unidade": l["item__unidade"], "quantidade": str(l["qtd_total"]), "valor": str(valor),
                "pct": str((valor / total * 100).quantize(Decimal("0.01"))) if total > 0 else "0",
                "pct_acumulado": str(pct_acum.quantize(Decimal("0.01"))), "classe": classe,
            })
        resumo = {c: {"itens": 0, "valor": Decimal("0")} for c in ("A", "B", "C")}
        for it in itens:
            resumo[it["classe"]]["itens"] += 1
            resumo[it["classe"]]["valor"] += Decimal(it["valor"])
        return Response({
            "total": str(total),
            "resumo": {c: {"itens": v["itens"], "valor": str(v["valor"])} for c, v in resumo.items()},
            "itens": itens,
        })


class AplicadoView(views.APIView):
    """Físico-financeiro: material **aplicado** (consumido) por obra e etapa,
    valorizado pelo custo da saída, confrontado com o **orçado**.

    O lado orçado vem do módulo Orçamento (ORC.1), pelo orçamento **aprovado**
    vigente da obra, agregado na mesma chave `(obra, etapa)` que o SIL usa para
    apropriar movimentação. Duas escolhas conscientes:

    - **Confronta custo direto, não preço.** Material sai do estoque a custo; o
      valor com BDI é preço de venda. Comparar consumo contra preço faria toda
      obra parecer economia.
    - **`orcado` continua `None` quando não há régua** — obra sem orçamento
      aprovado, ou tenant que não assina o módulo. Melhor um campo vazio e
      honesto do que um zero que se lê como "orçamento estourado em 100%".
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "sil"
    required_permission = "sil.relatorio.view"

    def get(self, request):
        tid = getattr(request.user, "tenant_id", None)
        dec = DecimalField(max_digits=20, decimal_places=4)
        qs = MovimentacaoEstoque.objects.filter(tenant_id=tid, tipo=MovimentacaoEstoque.Tipo.SAIDA, obra__isnull=False)
        obra = request.query_params.get("obra")
        if obra:
            qs = qs.filter(obra_id=obra)
        linhas = list(
            qs.values("obra_id", "obra__nome_obra", "etapa_id", "etapa__nome_etapa")
            .annotate(aplicado=Coalesce(Sum(F("quantidade") * F("custo_unitario"), output_field=dec), Decimal("0"), output_field=dec))
            .order_by("obra__nome_obra", "etapa__nome_etapa")
        )
        orcado = self._orcado_por_etapa(request, tid, obra)
        resposta = []
        for l in linhas:
            chave = (l["obra_id"], l["etapa_id"])
            previsto = orcado.get(chave, {}).get("orcado")
            aplicado = l["aplicado"]
            resposta.append({
                "obra": l["obra_id"], "obra_nome": l["obra__nome_obra"],
                "etapa": l["etapa_id"], "etapa_nome": l["etapa__nome_etapa"] or "— sem etapa —",
                "aplicado": str(aplicado),
                "orcado": str(previsto) if previsto is not None else None,
                "saldo": str(previsto - aplicado) if previsto is not None else None,
                "estourado": bool(previsto is not None and aplicado > previsto),
            })
        return Response(resposta)

    @staticmethod
    def _orcado_por_etapa(request, tenant_id, obra_id):
        """Seam com o Orçamento — import tardio e tolerante.

        Tardio para o SIL não depender do Orçamento em tempo de import (os dois
        módulos são vendidos separados); tolerante porque um tenant que não
        assina `orcamento` simplesmente não tem régua, e isso não é erro."""
        if not autorizacao.usa_modulo(request.user, "orcamento"):
            return {}
        from moduloorcamento.planilha import orcado_por_etapa

        return orcado_por_etapa(tenant_id, obra_id or None)


class SilDashboardView(views.APIView):
    """Cockpit do SIL numa resposta: valor em estoque, fila de decisão (abaixo do
    mínimo, requisições a aprovar/atender, inventários abertos, lotes vencendo) e
    atividade recente. Gateado pelo módulo; escopado por `tenant_id`."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "sil"

    def get(self, request):
        tid = getattr(request.user, "tenant_id", None)
        hoje = timezone.localdate()
        dec = DecimalField(max_digits=20, decimal_places=4)

        saldos = SaldoEstoque.objects.filter(tenant_id=tid)
        valor_estoque = saldos.aggregate(
            v=Coalesce(Sum(F("quantidade") * F("custo_medio"), output_field=dec), Decimal("0"), output_field=dec)
        )["v"]
        abaixo_minimo = saldos.filter(ponto_reposicao__gt=0, quantidade__lte=F("ponto_reposicao")).count()
        itens_em_estoque = saldos.filter(quantidade__gt=0).values("item_id").distinct().count()

        prazo = hoje + timedelta(days=30)
        epi_vencendo = EntregaEPI.objects.filter(
            tenant_id=tid, status=EntregaEPI.Status.ENTREGUE,
        ).filter(Q(ca_validade__lte=prazo) | Q(data_prevista_troca__lte=prazo)).count()
        ferramentas_atrasadas = EmprestimoFerramenta.objects.filter(
            tenant_id=tid, status=EmprestimoFerramenta.Status.EMPRESTADA, data_prevista_devolucao__lt=hoje,
        ).count()
        ferramentas_manutencao = Ferramenta.objects.filter(tenant_id=tid).filter(
            Q(proxima_calibracao__lte=prazo) | Q(proxima_manutencao__lte=prazo)
        ).exclude(estado=Ferramenta.Estado.BAIXADA).count()
        # Recebimentos do SCM a dar entrada no estoque (o laço vivo com o SCM).
        try:
            from moduloscm.models import PedidoCompra
            recebimentos_a_conferir = PedidoCompra.objects.filter(
                tenant_id=tid, status__in=["enviado", "recebido_parcial"],
            ).count()
        except Exception:
            recebimentos_a_conferir = 0

        atividade = []
        for m in MovimentacaoEstoque.objects.filter(tenant_id=tid).select_related("item", "local").order_by("-criado_em", "-mov_id")[:8]:
            atividade.append({
                "tipo": m.tipo,
                "titulo": f"{m.get_tipo_display()} · {m.item.descricao if m.item_id else ''}",
                "meta": f"{m.quantidade} {m.item.unidade if m.item_id else ''} · {m.local.nome if m.local_id else ''}",
                "quando": m.criado_em.isoformat(),
            })

        return Response({
            "valorEstoque": str(valor_estoque),
            "locais": LocalEstoque.objects.filter(tenant_id=tid, ativo=True).count(),
            "itensEmEstoque": itens_em_estoque,
            "abaixoMinimo": abaixo_minimo,
            "requisicoesPendentes": Requisicao.objects.filter(tenant_id=tid, status=Requisicao.Status.PENDENTE).count(),
            "requisicoesAprovadas": Requisicao.objects.filter(tenant_id=tid, status=Requisicao.Status.APROVADA).count(),
            "inventariosAbertos": Inventario.objects.filter(tenant_id=tid, status=Inventario.Status.ABERTO).count(),
            "lotesVencendo": Lote.objects.filter(tenant_id=tid, validade__isnull=False, validade__lte=prazo).count(),
            "epiVencendo": epi_vencendo,
            "ferramentasAtrasadas": ferramentas_atrasadas,
            "ferramentasManutencao": ferramentas_manutencao,
            "recebimentosAConferir": recebimentos_a_conferir,
            "atividade": atividade,
        })
