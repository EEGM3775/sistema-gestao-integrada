# backend/nucleo/aprovacao_views.py
"""API da escada de atesto — `/api/aprovacao/`.

Endereço no `nucleo` e não no `pdca` pelo mesmo motivo que a frota: a medição de
obra é a primeira cliente, não a dona. Quando o ERP levar pagamento acima de
alçada para a escada, ele entra por esta mesma rota, com outro `alvo`.

**Quem pode o quê**, e a divisão não é arbitrária:

- **configurar** a escada (`FluxoAprovacao`/`NivelAprovacao`) é ato de
  administração — quantas assinaturas o dinheiro precisa é decisão da empresa,
  não de quem opera o documento. Exige `plataforma.fluxo_aprovacao.*`;
- **atestar** não tem permissão própria de API: quem manda é o **degrau**, e a
  conferência é do motor. Uma permissão de view por cima diria "você pode
  atestar" para quem o degrau vai recusar depois.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .aprovacao import cancelar, decidir, pendentes_para, validar_fluxo
from .models import Atesto, FluxoAprovacao, NivelAprovacao, PedidoAprovacao
from .permissions import RequirePermission
from .tenancy import TenantScopedViewSetMixin
from .tenant_validators import TenantScopedModelSerializer


class NivelAprovacaoSerializer(TenantScopedModelSerializer):
    class Meta:
        model = NivelAprovacao
        fields = "__all__"
        read_only_fields = ["tenant"]


class FluxoAprovacaoSerializer(TenantScopedModelSerializer):
    niveis = NivelAprovacaoSerializer(many=True, read_only=True)
    alvo_rotulo = serializers.SerializerMethodField()

    class Meta:
        model = FluxoAprovacao
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em", "atualizado_em"]

    def get_alvo_rotulo(self, obj) -> str:
        return f"{obj.alvo.app_label}.{obj.alvo.model}"


class AtestoSerializer(TenantScopedModelSerializer):
    decisao_rotulo = serializers.CharField(source="get_decisao_display", read_only=True)

    class Meta:
        model = Atesto
        fields = "__all__"
        read_only_fields = ["tenant"]


class PedidoAprovacaoSerializer(TenantScopedModelSerializer):
    atestos = AtestoSerializer(many=True, read_only=True)
    estado_rotulo = serializers.CharField(source="get_estado_display", read_only=True)
    fluxo_nome = serializers.CharField(source="fluxo.nome", read_only=True)
    nivel_atual_nome = serializers.CharField(source="nivel_atual.nome", read_only=True)
    alvo_rotulo = serializers.SerializerMethodField()
    #: Quantos degraus faltam. A fila de decisão mostra isto porque "falta você e
    #: mais dois" e "falta só você" são situações diferentes para quem assina.
    degraus_restantes = serializers.SerializerMethodField()

    class Meta:
        model = PedidoAprovacao
        fields = "__all__"
        read_only_fields = [
            "tenant", "estado", "nivel_atual", "solicitado_por", "solicitante_nome",
            "solicitado_em", "concluido_em",
        ]

    def get_alvo_rotulo(self, obj) -> str:
        return f"{obj.alvo_tipo.app_label}.{obj.alvo_tipo.model}#{obj.alvo_id}"

    def get_degraus_restantes(self, obj) -> int:
        if obj.nivel_atual_id is None:
            return 0
        return obj.fluxo.niveis.filter(ordem__gte=obj.nivel_atual.ordem).count()


class FluxoAprovacaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Configuração das escadas do tenant."""

    queryset = FluxoAprovacao.objects.select_related("alvo").prefetch_related("niveis")
    serializer_class = FluxoAprovacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "plataforma.fluxo_aprovacao"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["alvo", "ativo", "padrao"]

    @action(detail=True, methods=["get"])
    def validar(self, request, pk=None):
        """Diz se a escada está utilizável **antes** de alguém depender dela.

        Existe porque a validação natural aconteceria no `abrir()` — ou seja, na
        hora em que o gestor submete a medição, que é o pior momento possível
        para descobrir que o fluxo tem um buraco na numeração.
        """
        fluxo = self.get_object()
        try:
            validar_fluxo(fluxo)
        except DjangoValidationError as erro:
            return Response({"valido": False, "problemas": erro.messages})
        return Response({"valido": True, "problemas": []})


class NivelAprovacaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = NivelAprovacao.objects.select_related("fluxo")
    serializer_class = NivelAprovacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "plataforma.fluxo_aprovacao"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["fluxo"]


class PedidoAprovacaoViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Os pedidos e a decisão sobre eles.

    **Somente leitura no CRUD, de propósito.** Ninguém cria um pedido por esta
    rota: quem o abre é o módulo dono do documento, no verbo de domínio dele
    ("submeter medição"), porque só ele sabe o que é um documento pronto para
    subir a escada. Um `POST /pedidos/` genérico deixaria qualquer objeto entrar
    em aprovação sem passar pela regra do módulo que o governa.
    """

    queryset = PedidoAprovacao.objects.select_related(
        "fluxo", "nivel_atual", "alvo_tipo", "solicitado_por"
    ).prefetch_related("atestos")
    serializer_class = PedidoAprovacaoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["estado", "fluxo", "alvo_tipo", "alvo_id"]

    @action(detail=False, methods=["get"])
    def pendentes(self, request):
        """A fila de decisão de quem está pedindo — só o que esta pessoa pode
        atestar agora. É a consulta que a tela "requer sua decisão" faz."""
        qs = pendentes_para(request.user)
        pagina = self.paginate_queryset(qs)
        dados = self.get_serializer(pagina if pagina is not None else qs, many=True).data
        if pagina is not None:
            return self.get_paginated_response(dados)
        return Response(dados)

    @action(detail=True, methods=["post"])
    def decidir(self, request, pk=None):
        """`{"aprovar": true|false, "observacao": "..."}` — um degrau da escada.

        Aprovar no último degrau encerra o pedido e dispara o sinal que o módulo
        dono do alvo escuta; reprovar encerra em qualquer degrau.
        """
        pedido = self.get_object()
        aprovar = request.data.get("aprovar")
        if not isinstance(aprovar, bool):
            raise ValidationError({"aprovar": "Informe `true` ou `false`."})
        try:
            pedido = decidir(
                pedido=pedido, usuario=request.user, aprovar=aprovar,
                observacao=str(request.data.get("observacao") or ""),
            )
        except DjangoPermissionDenied as erro:
            raise PermissionDenied(str(erro))
        except DjangoValidationError as erro:
            raise ValidationError({"pedido": erro.messages})
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Retira o documento da escada sem decidir o mérito."""
        pedido = self.get_object()
        try:
            pedido = cancelar(
                pedido=pedido, usuario=request.user,
                motivo=str(request.data.get("motivo") or ""),
            )
        except DjangoPermissionDenied as erro:
            raise PermissionDenied(str(erro))
        except DjangoValidationError as erro:
            raise ValidationError({"pedido": erro.messages})
        return Response(self.get_serializer(pedido).data)
