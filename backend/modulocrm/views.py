# backend/modulocrm/views.py
from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import Lead, Account, Contact, Opportunity, Interaction
from .serializers import (
    LeadSerializer,
    AccountSerializer,
    ContactSerializer,
    OpportunitySerializer,
    InteractionSerializer
)
from .permissions import IsOwnerOrReadOnly

class BaseCrmViewSet(viewsets.ModelViewSet):
    """ViewSet base para o CRM que filtra objetos por usuário atribuído."""
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

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
        """Atribui o usuário logado como o responsável ao criar um novo objeto."""
        if self.request.user.is_authenticated:
            serializer.save(assigned_to=self.request.user)
        else:
            serializer.save()

class LeadViewSet(BaseCrmViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer

class AccountViewSet(BaseCrmViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

class ContactViewSet(BaseCrmViewSet):
    queryset = Contact.objects.all()
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

class InteractionViewSet(BaseCrmViewSet):
    queryset = Interaction.objects.all()
    serializer_class = InteractionSerializer
