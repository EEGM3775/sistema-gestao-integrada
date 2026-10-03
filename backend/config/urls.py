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
    DadoBancarioClienteViewSet,
    CarteiraView,
    CarteiraGruposView,
    CarteiraOpcoesView,
    IndicesEconomicosView,
)
from empreendimentos.views import (
    EmpreendimentoViewSet,
    ContaBancariaEmpreendimentoViewSet,
    CustoEmpreendimentoViewSet,
    UnidadeViewSet
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
from nucleo.frota_views import TarefaNaFilaViewSet
from nucleo.aprovacao_views import (
    FluxoAprovacaoViewSet,
    NivelAprovacaoViewSet,
    PedidoAprovacaoViewSet,
)
from nucleo.lixo_views import LixoViewSet
from nucleo.notificacoes_views import NotificacaoViewSet

# Plano contratado + medidores de quota (D24)
from nucleo.plano_views import PlanoView

# Observabilidade (Fase 10.1): liveness/readiness/métricas
from nucleo.health_views import HealthzView, ReadyzView, MetricsView

# Importação/exportação de plataforma (IE.0 + IE.0b)
from funcoesimpexp.views import (
    ArquivosView as ImpExpArquivosView,
    EntregarArquivoView as ImpExpEntregarView,
    ExportacaoDetalheView as ImpExpExportacaoView,
    ExportarView as ImpExpExportarView,
    ImportacaoDecisaoView as ImpExpDecisaoView,
    ImportacaoDetalheView as ImpExpDetalheView,
    ImportacaoRecusadasView as ImpExpRecusadasView,
    ImportacoesDoRecursoView as ImpExpHistoricoView,
    ImportarArquivosView as ImpExpImportarArquivosView,
    ImportarView as ImpExpImportarView,
    MapaDetalheView as ImpExpMapaView,
    MapasView as ImpExpMapasView,
    ModeloView as ImpExpModeloView,
    RecursosView as ImpExpRecursosView,
)

# Cria o roteador da API, que gera as rotas automaticamente
router = DefaultRouter()

# --- LGPD (Fase 9.D) ---
router.register(r'lgpd/incidentes', IncidenteLGPDViewSet, basename='incidentelgpd')

# --- Trilha de auditoria (Fase 9.E) ---
router.register(r'auditoria', AuditLogViewSet, basename='auditlog')

# --- Centro de notificações in-app (Calendário, Fatia C) ---
router.register(r'notificacoes', NotificacaoViewSet, basename='notificacao')

# --- A fila da frota de trabalho pesado (D98) ---
# Endereço no `nucleo` e não em `prancheta/` porque a frota é da plataforma: a
# Prancheta é a primeira cliente, não a dona. Importação de acervo, exportação
# grande e ortofoto do Maps entram pela mesma rota, com outra `frota`.
router.register(r'frota/tarefas', TarefaNaFilaViewSet, basename='frota-tarefa')

# --- A escada de atesto (PDCA.0) ---
# Endereço no `nucleo` pela mesma razão da frota: aprovar em mais de um nível é
# da plataforma. A medição de obra é a primeira cliente; o pagamento acima de
# alçada do ERP entra aqui depois, com outro `alvo`.
router.register(r'aprovacao/fluxos', FluxoAprovacaoViewSet, basename='aprovacao-fluxo')
router.register(r'aprovacao/niveis', NivelAprovacaoViewSet, basename='aprovacao-nivel')
router.register(r'aprovacao/pedidos', PedidoAprovacaoViewSet, basename='aprovacao-pedido')

# A lixeira da plataforma (D116). No `nucleo` porque a lápide é da tenancy: 16
# modelos de 7 apps entram por ela, e nenhum deles importa este arquivo.
router.register(r'lixo', LixoViewSet, basename='lixo')

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
# As unidades à venda — cadastro do empreendimento, consumido pela aba Unidades
# e pelo seletor da aquisição.
router.register(r'unidades', UnidadeViewSet, basename='unidade')

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

    # Carteira de clientes (a grade tipo planilha da tela de Clientes).
    # ATENÇÃO À ORDEM: precisa vir ANTES do router, senão a rota de detalhe
    # `clientes/<pk>/` do ClienteViewSet captura `clientes/carteira/` e devolve
    # 404 de cliente inexistente.
    path('api/clientes/carteira/', CarteiraView.as_view(), name='clientes_carteira'),
    path('api/clientes/carteira/grupos/', CarteiraGruposView.as_view(), name='clientes_carteira_grupos'),
    path('api/clientes/carteira/opcoes/', CarteiraOpcoesView.as_view(), name='clientes_carteira_opcoes'),
    # Série pública de índices (IPCA/INCC/IGP-M) — alimenta o seletor de
    # correção monetária da venda. Sem tenant: o índice é o mesmo para todos.
    path('api/indices-economicos/', IndicesEconomicosView.as_view(), name='indices_economicos'),

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

    # Importação/exportação (IE.0): um conjunto de endpoints para TODO recurso de
    # todo módulo — o `recurso` vem na URL e o registry resolve. Módulo novo
    # ganha import/export sem rota nova. Planta: docs/modulos/funcoesimpexp.md
    path('api/impexp/recursos/', ImpExpRecursosView.as_view(), name='impexp_recursos'),
    # DMS: o registro de todo arquivo, dentro e fora (funcoesimpexp/arquivos.py).
    path('api/impexp/arquivos/', ImpExpArquivosView.as_view(), name='impexp_arquivos'),
    # Coleções fixas antes das genéricas: `<str:recurso_id>` casa qualquer coisa,
    # e um recurso chamado "mapas" passaria a servir de rota de mapa.
    path('api/impexp/importacoes/<int:importacao_id>/', ImpExpDetalheView.as_view(), name='impexp_detalhe'),
    path('api/impexp/importacoes/<int:importacao_id>/recusadas/', ImpExpRecusadasView.as_view(), name='impexp_recusadas'),
    path('api/impexp/importacoes/<int:importacao_id>/<str:acao>/', ImpExpDecisaoView.as_view(), name='impexp_decisao'),
    # IE.0b — acompanhamento/baixa do job (`?baixar=1`) e de-para salvo
    path('api/impexp/exportacoes/<int:exportacao_id>/', ImpExpExportacaoView.as_view(), name='impexp_exportacao'),
    path('api/impexp/mapas/<int:mapa_id>/', ImpExpMapaView.as_view(), name='impexp_mapa'),
    path('api/impexp/<str:recurso_id>/exportar/', ImpExpExportarView.as_view(), name='impexp_exportar'),
    path('api/impexp/<str:recurso_id>/modelo/', ImpExpModeloView.as_view(), name='impexp_modelo'),
    path('api/impexp/<str:recurso_id>/importar/', ImpExpImportarView.as_view(), name='impexp_importar'),
    # IE.3 — lote de ARQUIVO (a pasta do projetista, a foto do diário, o ASO).
    # Rota própria e não um ramo do `importar/`: o corpo, as recusas e o resumo
    # são outros, e um endpoint com dois corpos costurados é o que o registry
    # existe para evitar.
    path('api/impexp/<str:recurso_id>/importar-arquivos/', ImpExpImportarArquivosView.as_view(), name='impexp_importar_arquivos'),
    path('api/impexp/<str:recurso_id>/mapas/', ImpExpMapasView.as_view(), name='impexp_mapas'),
    path('api/impexp/<str:recurso_id>/importacoes/', ImpExpHistoricoView.as_view(), name='impexp_historico'),
    # IE.3b — a SAÍDA de um arquivo do acervo. A porta única é de entrada e de
    # saída (decisão do dono, 08/08/2026), então o download do binário sai dos
    # módulos e vem para cá: `nosniff`, `attachment`, tipo declarado por nós e
    # trilha, numa implementação só. `especie`/`chave` são opacas ao motor.
    path('api/impexp/<str:recurso_id>/arquivo/<str:especie>/<str:chave>/', ImpExpEntregarView.as_view(), name='impexp_entregar'),

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
    path('api/prancheta/', include('moduloprancheta.urls')),
    path('api/pdca/', include('modulopdca.urls')),
    path('api/catalogo/', include('catalogo.urls')),
    path('api/scm/', include('moduloscm.urls')),
    path('api/sil/', include('modulosil.urls')),
    path('api/orcamento/', include('moduloorcamento.urls')),
    path('api/maps/', include('modulomaps.urls')),
]

# Adiciona URLs para servir arquivos de mídia e estáticos em modo de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
