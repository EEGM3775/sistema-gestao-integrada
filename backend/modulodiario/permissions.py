# modulodiario/permissions.py
from rest_framework import permissions
from obras.models import Obra

class IsResponsavelTecnicoDaObra(permissions.BasePermission):
    """
    Permissão customizada para permitir que apenas responsáveis técnicos de uma obra
    possam criar ou editar diários de obra.
    """
    def has_permission(self, request, view):
        # A permissão de criação (POST) é verificada no nível do objeto
        return True

    def has_object_permission(self, request, view, obj):
        # Para leitura (GET), qualquer um pode ver (pode ser ajustado se necessário)
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Para edição (PUT, PATCH, DELETE), verifica se o usuário é responsável
        obra = obj.obra
        return request.user.funcionario in obra.responsaveis_tecnicos.all()

    def has_permission_for_create(self, request, serializer):
        """
        Método customizado para ser chamado durante a criação.
        """
        obra_id = serializer.validated_data.get('obra').obra_id
        try:
            obra = Obra.objects.get(pk=obra_id)
            # O usuário logado (que é um funcionário) deve estar na lista de responsáveis
            return request.user.funcionario in obra.responsaveis_tecnicos.all()
        except Obra.DoesNotExist:
            return False
