# backend/moduloerp/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FaturaViewSet,
    TransacaoViewSet,
    NotaFiscalServicoViewSet,
    NotaFiscalProdutoViewSet,
    ERPDashboardView,
    NotaFiscalViewSet,
    ContaPagarViewSet,
    ContaReceberViewSet,
    CobrancaClienteViewSet,
    BoletoViewSet,
    AtualizarStatusNFView,
    ConsultarStatusNFView
)

router = DefaultRouter()
router.register(r'faturas', FaturaViewSet)
router.register(r'transacoes', TransacaoViewSet)
router.register(r'notas-fiscais-servico', NotaFiscalServicoViewSet)
router.register(r'notas-fiscais-produto', NotaFiscalProdutoViewSet)
router.register(r'notas-fiscais', NotaFiscalViewSet)
router.register(r'contas-a-pagar', ContaPagarViewSet)
router.register(r'contas-a-receber', ContaReceberViewSet)
router.register(r'cobrancas-cliente', CobrancaClienteViewSet)
router.register(r'boletos', BoletoViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', ERPDashboardView.as_view(), name='erp-dashboard'),
    path('atualizar-status-nf/', AtualizarStatusNFView.as_view(), name='atualizar-status-nf'),
    path('nf/<int:nf_id>/consultar/', ConsultarStatusNFView.as_view(), name='consultar-status-nf'),
]