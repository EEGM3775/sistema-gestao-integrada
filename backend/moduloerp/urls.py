# backend/moduloerp/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TransacaoViewSet,
    NotaFiscalServicoViewSet,
    NotaFiscalProdutoViewSet,
    ERPDashboardView,
    DreObraView,
    FinanceiroObrasView,
    NotaFiscalViewSet,
    ContaPagarViewSet,
    ContaReceberViewSet,
    RevisaoBaixaViewSet,
    CobrancaClienteViewSet,
    BoletoViewSet,
    CentroCustoViewSet,
    LoteRemessaViewSet,
    AtualizarStatusNFView,
    ConsultarStatusNFView,
    ConfiguracaoLotesView,
    IntegracaoFiscalView,
    NotasDasComprasView,
    IntercompanyView,
    EncontroDeContasView,
    DreEntidadesView,
)

from .views_cnab import ContaCobrancaViewSet, LoteCobrancaViewSet, RemessaViewSet, RetornoViewSet

router = DefaultRouter()
router.register(r'carteiras-cobranca', ContaCobrancaViewSet)
router.register(r'remessas-cnab', RemessaViewSet)
router.register(r'retornos-cnab', RetornoViewSet)
router.register(r'lotes-cobranca', LoteCobrancaViewSet)
router.register(r'transacoes', TransacaoViewSet)
router.register(r'notas-fiscais-servico', NotaFiscalServicoViewSet)
router.register(r'notas-fiscais-produto', NotaFiscalProdutoViewSet)
router.register(r'notas-fiscais', NotaFiscalViewSet)
router.register(r'contas-a-pagar', ContaPagarViewSet)
router.register(r'contas-a-receber', ContaReceberViewSet)
router.register(r'revisoes-baixa', RevisaoBaixaViewSet)
router.register(r'cobrancas-cliente', CobrancaClienteViewSet)
router.register(r'boletos', BoletoViewSet)
router.register(r'centros-custo', CentroCustoViewSet)
router.register(r'lotes-remessa', LoteRemessaViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', ERPDashboardView.as_view(), name='erp-dashboard'),
    path('notas-das-compras/', NotasDasComprasView.as_view(), name='erp-notas-das-compras'),
    path('obras/financeiro/', FinanceiroObrasView.as_view(), name='erp-financeiro-obras'),
    path('obras/<int:obra_id>/dre/', DreObraView.as_view(), name='erp-dre-obra'),
    path('configuracao/lotes/', ConfiguracaoLotesView.as_view(), name='erp-configuracao-lotes'),
    path('configuracao/integracao-fiscal/', IntegracaoFiscalView.as_view(), name='erp-integracao-fiscal'),
    path('atualizar-status-nf/', AtualizarStatusNFView.as_view(), name='atualizar-status-nf'),
    path('nf/<int:nf_id>/consultar/', ConsultarStatusNFView.as_view(), name='consultar-status-nf'),
    # Entidades (docs/modulos/entidades.md §3 e §6)
    path('intercompany/', IntercompanyView.as_view(), name='erp-intercompany'),
    path('intercompany/encontro/', EncontroDeContasView.as_view(), name='erp-encontro-de-contas'),
    path('entidades/dre/', DreEntidadesView.as_view(), name='erp-dre-entidades'),
]
