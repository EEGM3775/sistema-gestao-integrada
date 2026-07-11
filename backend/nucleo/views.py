# backend/nucleo/views.py
# Define a lógica da API para o app 'nucleo'.
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .models import Usuario, LogAtividadeUsuario, ConfiguracaoArquivos
from .permissions import IsDataAdminOrStaff
from .tenancy import TenantScopedViewSetMixin
from .serializers import UsuarioSerializer

class UsuarioViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar usuários.
    A segurança aqui é crucial e deve ser reforçada com permissões.
    """
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False) or getattr(user, 'is_data_admin', False):
            return Usuario.objects.all()
        return Usuario.objects.filter(pk=user.pk)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Retorna os dados do usuário logado
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

# Perfil/Permissao saíram do ERP (Fase 6): a IAM é a autoridade de papéis e
# permissões; o ERP os lê das claims do JWT (`request.user.iam_roles`). Os
# modelos locais nucleo.Perfil/Permissao ficam só como espelho legado.

# LogAtividadeUsuarioViewSet removido na Fase 9.E: a trilha de auditoria sensível
# é o AuditLog (GET /api/auditoria/, fail-closed). O LogAtividadeUsuario ficou
# como telemetria operacional (Celery/microsserviços) — ver docstring do modelo.

_DEFAULT_TIPOS = [
    'application/pdf', 'image/jpeg', 'image/png',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]

class ConfiguracaoUploadView(APIView):
    """Retorna a configuração de upload de arquivos para o tenant do usuário."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tid = getattr(getattr(request, 'user', None), 'tenant_id', None)
        obj = None
        if tid:
            obj = ConfiguracaoArquivos.objects.filter(tenant_id=tid).first()
        if obj is None:
            obj = ConfiguracaoArquivos.objects.filter(tenant__isnull=True).first()
        if obj is None:
            return Response({'max_tamanho_mb': 10, 'tipos_aceitos': _DEFAULT_TIPOS})
        return Response({
            'max_tamanho_mb': obj.max_tamanho_mb,
            'tipos_aceitos': obj.tipos_aceitos or _DEFAULT_TIPOS,
        })


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
