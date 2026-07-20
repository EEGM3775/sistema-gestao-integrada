# backend/config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

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
    LogInternoView,
    ConfiguracaoUploadView,
)
from nucleo.geo_views import ResolverEnderecoView, MunicipiosView
from obras.views import (
    ObraViewSet,
    EtapaObraViewSet,
    DocumentoObraViewSet
)
from rh.views import (
    CargoViewSet,
    FuncionarioViewSet,
    DadoMedicoFuncionarioViewSet,
    ASOFuncionarioViewSet,
    DocumentoFuncionarioViewSet,
    DadoBancarioFuncionarioViewSet,
    PagamentoFuncionarioViewSet,
    FolhaPagamentoViewSet
)

# Views LGPD (Fase 9.D)
from nucleo.lgpd_views import (
    LgpdExportarView, LgpdEsquecerView, IncidenteLGPDViewSet,
)

# Trilha de auditoria (Fase 9.E)
from nucleo.auditoria_views import AuditLogViewSet

# Centro de notificações in-app (Calendário, Fase 9 — Fatia C)
from nucleo.notificacoes_views import NotificacaoViewSet

# Plano contratado + medidores de quota (D24)
from nucleo.plano_views import PlanoView

# Observabilidade (Fase 10.1): liveness/readiness/métricas
from nucleo.health_views import HealthzView, ReadyzView, MetricsView

# Cria o roteador da API, que gera as rotas automaticamente
router = DefaultRouter()

# --- LGPD (Fase 9.D) ---
router.register(r'lgpd/incidentes', IncidenteLGPDViewSet, basename='incidentelgpd')

# --- Trilha de auditoria (Fase 9.E) ---
router.register(r'auditoria', AuditLogViewSet, basename='auditlog')

# --- Centro de notificações in-app (Calendário, Fatia C) ---
router.register(r'notificacoes', NotificacaoViewSet, basename='notificacao')

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
# (perfis/permissoes saíram: a IAM é a autoridade de papéis/permissões — Fase 6)
router.register(r'usuarios', UsuarioViewSet, basename='usuario')

# --- Rotas do App 'obras' ---
router.register(r'obras', ObraViewSet, basename='obra')
router.register(r'etapas-obras', EtapaObraViewSet, basename='etapaobra')
router.register(r'documentos-obras', DocumentoObraViewSet, basename='documentoobra')

# --- Rotas do App 'rh' ---
router.register(r'cargos', CargoViewSet, basename='cargo')
router.register(r'funcionarios', FuncionarioViewSet, basename='funcionario')
router.register(r'dados-medicos-funcionarios', DadoMedicoFuncionarioViewSet, basename='dadomedicofuncionario')
router.register(r'asos-funcionarios', ASOFuncionarioViewSet, basename='asofuncionario')
router.register(r'documentos-funcionarios', DocumentoFuncionarioViewSet, basename='documentofuncionario')
router.register(r'dados-bancarios-funcionarios', DadoBancarioFuncionarioViewSet, basename='dadobancariofuncionario')
router.register(r'pagamentos-funcionarios', PagamentoFuncionarioViewSet, basename='pagamentofuncionario')
router.register(r'folhas-pagamento', FolhaPagamentoViewSet, basename='folhapagamento')


# Define as URLs principais do projeto
urlpatterns = [
    path('admin/', admin.site.urls),

    # Observabilidade (Fase 10.1) — sondas de infra e métricas. Não roteadas
    # publicamente pelo gateway (só alcançáveis dentro da rede do compose).
    path('healthz', HealthzView.as_view(), name='healthz'),
    path('readyz', ReadyzView.as_view(), name='readyz'),
    path('metrics', MetricsView.as_view(), name='metrics'),

    # Login/identidade são da IAM (SSO). O backend é resource server: só valida o
    # JWT da IAM — não há mais emissão de token local (Fase 6). Ver
    # docs/acesso-e-permissoes.md.

    # Adiciona todas as URLs da API geradas pelo roteador sob o prefixo /api/
    path('api/', include(router.urls)),
    
    # Endpoint para log interno
    path('api/log-interno/', LogInternoView.as_view(), name='log_interno'),
    path('api/configuracoes/upload/', ConfiguracaoUploadView.as_view(), name='configuracao_upload'),

    # Geo: resolução compartilhada de endereço → município (CEP ViaCEP ou nome→IBGE)
    path('api/geo/resolver/', ResolverEnderecoView.as_view(), name='geo_resolver'),
    path('api/geo/municipios/', MunicipiosView.as_view(), name='geo_municipios'),

    # Plano e quotas (D24): medidor da UI e vitrine de upgrade
    path('api/plano/', PlanoView.as_view(), name='plano'),

    # LGPD (Fase 9.D): portabilidade e esquecimento do titular
    path('api/lgpd/<str:tipo>/<int:pk>/exportar/', LgpdExportarView.as_view(), name='lgpd_exportar'),
    path('api/lgpd/<str:tipo>/<int:pk>/esquecer/', LgpdEsquecerView.as_view(), name='lgpd_esquecer'),

    # --- Rotas dos Módulos (sem roteador principal) ---
    path('api/diario/', include('modulodiario.urls')),
    path('api/ia/', include('funcoesia.urls')),
    path('api/erp/', include('moduloerp.urls')),
    path('api/erp/cobrancas/', include('funcoescobrancas.urls')),
    path('api/crm/', include('modulocrm.urls')),
    # Webhook do WhatsApp (Fase C). Público (autentica pela assinatura HMAC da
    # Meta, não por JWT). Ingresso restrito ao path — Cloudflare Tunnel (10.3.2).
    path('webhooks/whatsapp', include('funcoeswhatsapp.urls')),
    path('api/api/', include('moduloapi.urls')),
    path('api/calendar/', include('modulocalendar.urls')),
    # Módulos planejados (stub — entitlement aplicado, endpoints de status disponíveis)
    path('api/aps/', include('moduloaps.urls')),
    path('api/dms/', include('modulodms.urls')),
    path('api/pdca/', include('modulopdca.urls')),
    path('api/scm/', include('moduloscm.urls')),
    path('api/sil/', include('modulosil.urls')),
    path('api/maps/', include('modulomaps.urls')),
]

# Adiciona URLs para servir arquivos de mídia e estáticos em modo de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
