# backend/modulocrm/permissions.py
from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permissão personalizada para permitir que apenas os proprietários de um objeto o editem.
    """

    def has_object_permission(self, request, view, obj):
        # Permissões de leitura são permitidas para qualquer solicitação,
        # então sempre permitiremos solicitações GET, HEAD ou OPTIONS.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Permissões de escrita são permitidas apenas para o proprietário do objeto.
        return obj.assigned_to == request.user
