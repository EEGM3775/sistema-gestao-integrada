import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const ScmDashboardPage = lazy(() => import('./pages/ScmDashboardPage'))
const ProdutosPage = lazy(() => import('./pages/ProdutosPage'))
const OfertasPage = lazy(() => import('./pages/OfertasPage'))
const CentrosCustoPage = lazy(() => import('./pages/CentrosCustoPage'))
const DemandasPage = lazy(() => import('./pages/DemandasPage'))
const DemandaDetailPage = lazy(() => import('./pages/DemandaDetailPage'))
const CotacaoDetailPage = lazy(() => import('./pages/CotacaoDetailPage'))
const PedidosPage = lazy(() => import('./pages/PedidosPage'))
const PedidoDetailPage = lazy(() => import('./pages/PedidoDetailPage'))

function ScmFallback() {
  return <div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando Suprimentos…</div>
}
function w(element: ReactNode) {
  return <Suspense fallback={<ScmFallback />}>{element}</Suspense>
}

/**
 * Sub-rotas do SCM sob `/app/scm`, todas atrás do entitlement `scm` (ModuleRoute).
 * Primeiro módulo sobre a fundação Malha (docs/identidade-visual.md §10).
 */
export const scmRoutes = (
  <Route element={<ModuleRoute module="scm" />}>
    <Route path="scm" element={w(<ScmDashboardPage />)} />
    <Route path="scm/produtos" element={w(<ProdutosPage />)} />
    <Route path="scm/ofertas" element={w(<OfertasPage />)} />
    <Route path="scm/centros-custo" element={w(<CentrosCustoPage />)} />
    <Route path="scm/demandas" element={w(<DemandasPage />)} />
    <Route path="scm/demandas/:id" element={w(<DemandaDetailPage />)} />
    <Route path="scm/cotacoes/:id" element={w(<CotacaoDetailPage />)} />
    <Route path="scm/pedidos" element={w(<PedidosPage />)} />
    <Route path="scm/pedidos/:id" element={w(<PedidoDetailPage />)} />
  </Route>
)
