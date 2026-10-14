"""Cadastro de entidades, participações e acessos — docs/modulos/entidades.md."""
from django.db import transaction
from django.db.models import ProtectedError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nucleo.busca import BuscaSemAcento
from nucleo.permissions import RequirePermission
from nucleo.tenancy import TenantScopedViewSetMixin

from . import escopo, regras
from .models import ConcessaoEmpreendimento, ConcessaoEntidade, Entidade, ParticipacaoEmpreendimento
from .serializers import (
    ConcessaoEmpreendimentoSerializer, ConcessaoEntidadeSerializer, EntidadeSerializer, ParticipacaoSerializer,
)


class EntidadeViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As entidades do tenant — as do grupo e as externas (contratantes, sócios de fora)."""
    queryset = Entidade.objects.all()
    serializer_class = EntidadeSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.entidade"
    # A barra de entidade do ERP pergunta a todo usuário: só diz o que ele já alcança.
    action_permission_map = {"contexto": None}
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["papel", "externa", "ativa", "tipo_pessoa"]
    search_fields = ["nome", "nome_fantasia", "documento"]

    def get_queryset(self):
        # A conta nova ganha a matriz na primeira vez que alguém olha.
        regras.matriz(self.request.user.tenant_id)
        return super().get_queryset().select_related("matriz", "cliente").prefetch_related(
            "empreendimentos_proprios", "participacoes__empreendimento",
        )

    def perform_create(self, serializer):
        tenant_id = self.request.user.tenant_id
        with transaction.atomic():
            antes = list(regras.do_grupo(tenant_id).values_list("pk", flat=True))
            super().perform_create(serializer)
            nova = serializer.instance
            if nova.externa:
                return
            # Saindo do modo simples: quem já usava o sistema recebe a entidade que
            # via, para ninguém perder o financeiro de ontem (entidades.md §4).
            if len(antes) == 1:
                from nucleo.models import Usuario
                for usuario in Usuario.objects.filter(tenant_id=tenant_id, is_active=True):
                    ConcessaoEntidade.objects.get_or_create(
                        tenant_id=tenant_id, usuario=usuario, entidade_id=antes[0],
                        defaults={"concedido_por": self.request.user},
                    )
            # Quem cria vê o que criou.
            ConcessaoEntidade.objects.get_or_create(
                tenant_id=tenant_id, usuario=self.request.user, entidade=nova,
                defaults={"concedido_por": self.request.user},
            )

    def destroy(self, request, *args, **kwargs):
        entidade = self.get_object()
        if not entidade.externa and not regras.do_grupo(entidade.tenant_id).exclude(pk=entidade.pk).exists():
            return Response(
                {"detail": "A conta precisa de ao menos uma entidade do grupo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            entidade.delete()
        except ProtectedError:
            return Response(
                {"detail": f"{entidade} já tem lançamentos, obras ou empreendimentos. Desative em vez de excluir."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def contexto(self, request):
        """O que a tela precisa saber antes de desenhar a barra de entidade:
        se há recorte (modo simples esconde tudo), a matriz e as entidades que a
        pessoa alcança no ERP."""
        tenant_id = request.user.tenant_id
        matriz = regras.matriz(tenant_id)
        grupo = regras.do_grupo(tenant_id).filter(ativa=True).order_by("entidade_id")
        alcance = escopo.alcance(request.user)
        if alcance is not None:
            grupo = grupo.filter(pk__in=alcance)
        return Response({
            "modo_simples": regras.modo_simples(tenant_id),
            "matriz": matriz.pk,
            "sem_recorte": alcance is None,
            "entidades": [
                {"entidade": e.pk, "nome": str(e), "papel": e.papel, "papel_nome": e.get_papel_display(),
                 "documento": e.documento}
                for e in grupo
            ],
        })


class ParticipacaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Quem é dono do empreendimento e em que cota — parte do cadastro dele."""
    queryset = ParticipacaoEmpreendimento.objects.select_related("entidade", "empreendimento")
    serializer_class = ParticipacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "obra.empreendimento"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["empreendimento", "entidade"]


class _ConcessaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Conceder acesso é ato próprio (`cadastro.entidade.conceder`): quem só edita
    o cadastro não se dá acesso ao financeiro de outra entidade."""
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_permission = "cadastro.entidade.conceder"
    filter_backends = [DjangoFilterBackend]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id, concedido_por=self.request.user)
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="conceder_acesso", instance=serializer.instance, usuario=self.request.user,
            detalhes={"usuario": serializer.instance.usuario_id},
        )

    def perform_destroy(self, instance):
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="revogar_acesso", instance=instance, usuario=self.request.user,
            detalhes={"usuario": instance.usuario_id},
        )
        instance.delete()


class ConcessaoEntidadeViewSet(_ConcessaoViewSet):
    queryset = ConcessaoEntidade.objects.select_related("usuario", "entidade")
    serializer_class = ConcessaoEntidadeSerializer
    filterset_fields = ["entidade", "usuario"]

    @action(detail=False, methods=["get"])
    def usuarios(self, request):
        """Quem pode receber acesso: os usuários ativos da conta que já entraram
        no sistema (o espelho local nasce no primeiro acesso)."""
        from nucleo.models import Usuario

        pessoas = Usuario.objects.filter(tenant_id=request.user.tenant_id, is_active=True).order_by("first_name", "username")
        return Response([
            {"id": u.pk, "nome": u.get_full_name() or u.username, "username": u.username}
            for u in pessoas
        ])


class ConcessaoEmpreendimentoViewSet(_ConcessaoViewSet):
    queryset = ConcessaoEmpreendimento.objects.select_related("usuario", "empreendimento")
    serializer_class = ConcessaoEmpreendimentoSerializer
    filterset_fields = ["empreendimento", "usuario"]
