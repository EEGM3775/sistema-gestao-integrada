import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

// Code-splitting por sub-módulo (D.1.0 — o ERP é o maior módulo do app, não
// deve inflar o bundle inicial das telas que a maioria dos usuários nem abre).
const ErpDashboardPage = lazy(() => import('./pages/ErpDashboardPage'))
const ContasAPagarPage = lazy(() => import('./pages/ContasAPagarPage'))
const ContasAReceberPage = lazy(() => import('./pages/ContasAReceberPage'))
const BoletosListPage = lazy(() => import('./pages/BoletosListPage'))
const BoletoDetailPage = lazy(() => import('./pages/BoletoDetailPage'))
const NotasFiscaisPage = lazy(() => import('./pages/NotasFiscaisPage'))
const CobrancaBancariaPage = lazy(() => import('./pages/CobrancaBancariaPage'))
const ConfiguracoesFinanceiroPage = lazy(() => import('./pages/ConfiguracoesFinanceiroPage'))

function ErpFallback() {
  return (
    <div className="px-6 py-8" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
      Carregando módulo financeiro…
    </div>
  )
}

function withErpFallback(element: ReactNode) {
  return <Suspense fallback={<ErpFallback />}>{element}</Suspense>
}

/**
 * Sub-rotas do ERP, registradas sob `/app/erp` em `App.tsx` — rotas-irmãs
 * (mesmo padrão de `empreendimentos`/`empreendimentos/:id` em `App.tsx`),
 * não rotas aninhadas: o hub (`/app/erp`) e os workspaces de Contas a
 * Pagar/Receber (D.1.1) são telas completas, cada uma com sua própria
 * navegação de volta ao hub. Todas ficam sob um `ModuleRoute` (F4): sem o
 * entitlement `erp_financeiro`, a navegação direta por URL cai numa tela
 * amigável em vez de um 403 cru da API.
 */
export const erpRoutes = (
  <Route element={<ModuleRoute module="erp_financeiro" />}>
    <Route path="erp" element={withErpFallback(<ErpDashboardPage />)} />
    <Route path="erp/contas-a-pagar" element={withErpFallback(<ContasAPagarPage />)} />
    <Route path="erp/contas-a-receber" element={withErpFallback(<ContasAReceberPage />)} />
    <Route path="erp/boletos" element={withErpFallback(<BoletosListPage />)} />
    <Route path="erp/boletos/:id" element={withErpFallback(<BoletoDetailPage />)} />
    <Route path="erp/notas-fiscais" element={withErpFallback(<NotasFiscaisPage />)} />
    <Route path="erp/cobranca-bancaria" element={withErpFallback(<CobrancaBancariaPage />)} />
    <Route path="erp/configuracoes" element={withErpFallback(<ConfiguracoesFinanceiroPage />)} />
  </Route>
)
