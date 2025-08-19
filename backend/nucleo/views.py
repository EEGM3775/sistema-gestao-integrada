# backend/nucleo/views.py
# Define a lógica da API para o app 'nucleo'.
from rest_framework import viewsets
from .models import Usuario, Perfil, Permissao, LogAtividadeUsuario
from .serializers import (
    UsuarioSerializer,
    PerfilSerializer,
    PermissaoSerializer,
    LogAtividadeUsuarioSerializer
)

class UsuarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar usuários.
    A segurança aqui é crucial e deve ser reforçada com permissões.
    """
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class PerfilViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar perfis de usuário.
    """
    queryset = Perfil.objects.all()
    serializer_class = PerfilSerializer
    # permission_classes = [permissions.IsAuthenticated]

class PermissaoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar permissões do sistema.
    """
    queryset = Permissao.objects.all()
    serializer_class = PermissaoSerializer
    # permission_classes = [permissions.IsAuthenticated]

class LogAtividadeUsuarioViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint da API apenas para visualização dos logs de atividade.
    Não deve permitir criação, edição ou exclusão via API.
    """
    queryset = LogAtividadeUsuario.objects.all()
    serializer_class = LogAtividadeUsuarioSerializer
    # permission_classes = [permissions.IsAuthenticated]
