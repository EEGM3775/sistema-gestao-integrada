# backend/nucleo/views.py
# Define a lógica da API para o app 'nucleo'.
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
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
    # permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Retorna os dados do usuário logado
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

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

class LogInternoView(APIView):
    """
    Endpoint para receber logs de microserviços internos.
    Não requer autenticação de usuário padrão, mas deve ser
    protegido na infraestrutura (ex: acessível apenas pela rede interna).
    """
    permission_classes = [IsAuthenticated] # ATENÇÃO: Mude para uma permissão mais restritiva em produção

    def post(self, request, *args, **kwargs):
        data = request.data
        
        # Validação básica dos dados recebidos
        acao = data.get('acao')
        entidade_alvo = data.get('entidade_alvo')
        detalhes = data.get('detalhes')

        if not acao:
            return Response(
                {"error": "O campo 'acao' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Opcional: buscar usuário se um 'user_id' for fornecido
        usuario = None
        user_id = data.get('user_id')
        if user_id:
            try:
                usuario = Usuario.objects.get(id=user_id)
            except Usuario.DoesNotExist:
                pass

        try:
            LogAtividadeUsuario.objects.create(
                usuario=usuario,
                acao=acao,
                entidade_alvo=entidade_alvo,
                alvo_id=data.get('alvo_id'),
                detalhes=detalhes
            )
            return Response(
                {"message": "Log registrado com sucesso."},
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": "Erro interno ao salvar o log."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
