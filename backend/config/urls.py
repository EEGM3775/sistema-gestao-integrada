# backend/config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .auth_views import (
    api_login,
    api_logout,
    api_user_info,
    session_login,
    session_logout,
    refresh_token
)

# Importa as views dos apps
from clientes.views import (
    ClienteViewSet,
    ClienteEmpreendimentoViewSet,
    ContratoClienteViewSet,
    DocumentoClienteViewSet,
    DadoBancarioClienteViewSet
)
from empreendimentos.views import (
    EmpreendimentoViewSet,
    ContaBancariaEmpreendimentoViewSet,
    CustoEmpreendimentoViewSet
)
from fornecedores.views import (
    FornecedorViewSet,
    DadoBancarioFornecedorViewSet,
    ProdutoServicoFornecedorViewSet
)
from nucleo.views import (
    UsuarioViewSet,
    PerfilViewSet,
    PermissaoViewSet,
    LogAtividadeUsuarioViewSet,
    LogInternoView
)
from obras.views import (
    ObraViewSet,
    EtapaObraViewSet,
    DocumentoObraViewSet
)
from rh.views import (
    CargoViewSet,
    FuncionarioViewSet,
    DadoMedicoFuncionarioViewSet,
    DocumentoFuncionarioViewSet,
    DadoBancarioFuncionarioViewSet,
    PagamentoFuncionarioViewSet,
    FolhaPagamentoViewSet
)
from . import views
from .auth_views import (
    api_login,
    api_logout,
    api_user_info,
    session_login,
    session_logout,
    refresh_token
)

# Cria o roteador da API, que gera as rotas automaticamente
router = DefaultRouter()

# --- Rotas do App 'clientes' ---
router.register(r'clientes', ClienteViewSet, basename='cliente')
router.register(r'clientes-empreendimentos', ClienteEmpreendimentoViewSet, basename='clienteempreendimento')
router.register(r'contratos-clientes', ContratoClienteViewSet, basename='contratocliente')
router.register(r'documentos-clientes', DocumentoClienteViewSet, basename='documentocliente')
router.register(r'dados-bancarios-clientes', DadoBancarioClienteViewSet, basename='dadobancariocliente')

# --- Rotas do App 'empreendimentos' ---
router.register(r'empreendimentos', EmpreendimentoViewSet, basename='empreendimento')
router.register(r'contas-bancarias-empreendimentos', ContaBancariaEmpreendimentoViewSet, basename='contabancariaempreendimento')
router.register(r'custos-empreendimentos', CustoEmpreendimentoViewSet, basename='custoempreendimento')

# --- Rotas do App 'fornecedores' ---
router.register(r'fornecedores', FornecedorViewSet, basename='fornecedor')
router.register(r'dados-bancarios-fornecedores', DadoBancarioFornecedorViewSet, basename='dadobancariofornecedor')
router.register(r'produtos-servicos-fornecedores', ProdutoServicoFornecedorViewSet, basename='produtoservicofornecedor')

# --- Rotas do App 'nucleo' ---
router.register(r'usuarios', UsuarioViewSet, basename='usuario')
router.register(r'perfis', PerfilViewSet, basename='perfil')
router.register(r'permissoes', PermissaoViewSet, basename='permissao')
router.register(r'logs-atividade', LogAtividadeUsuarioViewSet, basename='logatividade')

# --- Rotas do App 'obras' ---
router.register(r'obras', ObraViewSet, basename='obra')
router.register(r'etapas-obras', EtapaObraViewSet, basename='etapaobra')
router.register(r'documentos-obras', DocumentoObraViewSet, basename='documentoobra')

# --- Rotas do App 'rh' ---
router.register(r'cargos', CargoViewSet, basename='cargo')
router.register(r'funcionarios', FuncionarioViewSet, basename='funcionario')
router.register(r'dados-medicos-funcionarios', DadoMedicoFuncionarioViewSet, basename='dadomedicofuncionario')
router.register(r'documentos-funcionarios', DocumentoFuncionarioViewSet, basename='documentofuncionario')
router.register(r'dados-bancarios-funcionarios', DadoBancarioFuncionarioViewSet, basename='dadobancariofuncionario')
router.register(r'pagamentos-funcionarios', PagamentoFuncionarioViewSet, basename='pagamentofuncionario')
router.register(r'folhas-pagamento', FolhaPagamentoViewSet, basename='folhapagamento')


# Define as URLs principais do projeto
urlpatterns = [
    path('', views.home, name='home'),
    path('admin/', admin.site.urls),
    
    # Endpoints JWT (API)
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Endpoints de autenticação personalizados
    path('api/auth/login/', api_login, name='api_login'),
    path('api/auth/logout/', api_logout, name='api_logout'),
    path('api/auth/user/', api_user_info, name='api_user_info'),
    path('api/auth/refresh/', refresh_token, name='refresh_token'),
    
    # Endpoints de sessão para frontend HTML
    path('auth/login/', session_login, name='session_login'),
    path('auth/logout/', session_logout, name='session_logout'),
    path('login.html', views.login_page, name='login_page'),
    
    # Adiciona todas as URLs da API geradas pelo roteador sob o prefixo /api/
    path('api/', include(router.urls)),
    
    # Endpoint para log interno
    path('api/log-interno/', LogInternoView.as_view(), name='log_interno'),

    # --- Rotas dos Módulos (sem roteador principal) ---
    path('api/diario/', include('modulodiario.urls')),
    path('api/ia/', include('funcoesia.urls')),
    path('api/erp/', include('moduloerp.urls')),
    path('api/crm/', include('modulocrm.urls')),
    path('calendar/', include(('modulocalendar.urls', 'modulocalendar'), namespace='calendar')),
    
    # Página de informações da API
    path('api/', views.api_info, name='api_info'),
    
    # Frontend NFS-e
    path('nfse/', views.nfse_frontend, name='nfse_frontend'),
    
    # Frontend Análises de IA
    path('analises-ia.html', views.analises_ia_frontend, name='analises_ia_frontend'),
    
    # Servir arquivos do frontend (deve ficar por último para não interceptar outras rotas)
    path('<str:file_name>', views.serve_frontend_file, name='frontend_files'),
    
]

# Adiciona URLs para servir arquivos de mídia e estáticos em modo de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
