# backend/modulocrm/views.py
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from nucleo.busca import BuscaSemAcento
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.permissions import RequireModule, RequirePermission
from . import services
from .models import Lead, Account, Contact, Opportunity, Interaction, OpportunityProduct
from .serializers import (
    LeadSerializer,
    AccountSerializer,
    ContactSerializer,
    OpportunitySerializer,
    InteractionSerializer,
    OpportunityProductSerializer
)
from .permissions import IsOwnerOrReadOnly

class BaseCrmViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """ViewSet base para o CRM: entitlement de módulo (camada 1) + permissão
    (camada 2, Fase 9.B). Cada subclasse declara ``required_resource``."""
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly, RequireModule, RequirePermission]
    required_module = "crm"

    def get_queryset(self):
        """
        Filtra o queryset para que usuários não-staff vejam apenas os seus itens.
        Administradores veem tudo.
        """
        user = self.request.user
        if user.is_staff:
            return self.queryset
        
        # Filtra por 'assigned_to' ou se o usuário é o criador (se aplicável)
        return self.queryset.filter(assigned_to=user)

    def perform_create(self, serializer):
        """Atribui o usuário logado como responsável e o tenant ao criar um novo objeto.

        O contato não tem responsável (é de quem gerencia a conta); passar
        `assigned_to` a ele derrubava a criação com 500.
        """
        tid = getattr(self.request.user, "tenant_id", None)
        if self.request.user.is_authenticated and hasattr(serializer.Meta.model, "assigned_to"):
            serializer.save(assigned_to=self.request.user, tenant_id=tid)
        else:
            serializer.save(tenant_id=tid)

class LeadViewSet(BaseCrmViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    required_resource = "crm.lead"
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ['status', 'source', 'campaign']
    # Os mesmos campos que o `crm.lead` do impexp percorre (R7: o arquivo é o recorte da tela).
    search_fields = ["first_name", "last_name", "email", "company"]

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """Converte o lead em Account + Contact + Opportunity (portado do funcoeslead — Fase 11.2)."""
        lead = self.get_object()
        try:
            resultado = services.converter_lead(lead, usuario=request.user)
        except services.LeadNaoConversivel as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)

    @action(detail=True, methods=['post'])
    def score(self, request, pk=None):
        """Recalcula a pontuação do lead pelas regras de scoring."""
        lead = services.pontuar_lead(self.get_object())
        return Response(LeadSerializer(lead).data)

class AccountViewSet(BaseCrmViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    required_resource = "crm.conta"
    filter_backends = [BuscaSemAcento]
    search_fields = ["name", "email"]

class ContactViewSet(BaseCrmViewSet):
    queryset = Contact.objects.all()
    required_resource = "crm.contato"
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["account"]
    search_fields = ["first_name", "last_name", "email", "account__name"]
    # A lógica de permissão para contatos pode precisar ser mais complexa
    # (ex: permitir ver contatos da mesma conta)
    # Por enquanto, segue o padrão do assigned_to.

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Contact.objects.all()
        
        # Permite ver contatos de contas que o usuário gerencia
        return Contact.objects.filter(account__assigned_to=user)

    serializer_class = ContactSerializer

class OpportunityViewSet(BaseCrmViewSet):
    queryset = Opportunity.objects.all()
    serializer_class = OpportunitySerializer
    required_resource = "crm.oportunidade"
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["stage", "account"]
    search_fields = ["name", "account__name"]


class OpportunityProductViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = OpportunityProduct.objects.all()
    serializer_class = OpportunityProductSerializer
    # S5 corrigido: exigia só IsAuthenticated → tenant sem o módulo `crm` acessava.
    # Agora entitlement de módulo (camada 1) + permissão (camada 2).
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "crm"
    required_resource = "crm.oportunidade_produto"

    def get_queryset(self):
        """
        Optionally filters the products for a specific opportunity
        """
        queryset = super().get_queryset()
        opportunity_id = self.request.query_params.get('opportunity_id')
        if opportunity_id:
            queryset = queryset.filter(opportunity_id=opportunity_id)
        return queryset


class InteractionViewSet(BaseCrmViewSet):
    queryset = Interaction.objects.all()
    serializer_class = InteractionSerializer
    # `crm.interacao` tem só view+create no catálogo (sem edit) → mapa explícito.
    permission_map = {"view": "crm.interacao.view", "write": "crm.interacao.create"}
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        'type': ['exact', 'in'],
        'completed': ['exact'],
        'due_date': ['gte', 'lte'],
        'lead': ['exact', 'isnull'],
        'opportunity': ['exact'],
        'contact': ['exact'],
    }

    def get_queryset(self):
        """`assigned_to` aqui é GenericFK — o filtro do BaseCrmViewSet
        (`assigned_to=user`) levantaria FieldError. Não-staff vê o que está
        atribuído a ele (direto ou via lead sob sua responsabilidade)."""
        user = self.request.user
        if user.is_staff:
            return self.queryset
        return self.queryset.filter(
            Q(assigned_to_content_type=ContentType.objects.get_for_model(user),
              assigned_to_object_id=user.pk)
            | Q(lead__assigned_to=user)
        ).distinct()
