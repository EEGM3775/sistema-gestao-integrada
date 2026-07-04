# backend/moduloerp/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TransacaoViewSet,
    NotaFiscalServicoViewSet,
    NotaFiscalProdutoViewSet,
    ERPDashboardView,
    NotaFiscalViewSet,
    ContaPagarViewSet,
    ContaReceberViewSet,
    RevisaoBaixaViewSet,
    CobrancaClienteViewSet,
    BoletoViewSet,
    CentroCustoViewSet,
    LoteRemessaViewSet,
    AtualizarStatusNFView,
    ConsultarStatusNFView
)

router = DefaultRouter()
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
    path('atualizar-status-nf/', AtualizarStatusNFView.as_view(), name='atualizar-status-nf'),
    path('nf/<int:nf_id>/consultar/', ConsultarStatusNFView.as_view(), name='consultar-status-nf'),
]
