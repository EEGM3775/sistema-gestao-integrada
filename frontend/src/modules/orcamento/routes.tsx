import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const HubPage = lazy(() => import('./pages/HubPage'))
const OrcarPage = lazy(() => import('./pages/OrcarPage'))
const ControlarPage = lazy(() => import('./pages/ControlarPage'))
const CronogramaPage = lazy(() => import('./pages/CronogramaPage'))
const BasesPage = lazy(() => import('./pages/BasesPage'))
const IncorporacaoPage = lazy(() => import('./pages/IncorporacaoPage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando Orçamento…</div>}>
      {element}
    </Suspense>
  )
}

/** Rotas do Orçamento sob `/app/orcamento`, atrás do entitlement `orcamento`.
 *  O hub é a raiz; cada página tem rota própria para ser endereçável. */
export const orcamentoRoutes = (
  <Route element={<ModuleRoute module="orcamento" />}>
    <Route path="orcamento" element={w(<HubPage />)} />
    <Route path="orcamento/orcar" element={w(<OrcarPage />)} />
    <Route path="orcamento/controlar" element={w(<ControlarPage />)} />
    <Route path="orcamento/cronograma" element={w(<CronogramaPage />)} />
    <Route path="orcamento/bases" element={w(<BasesPage />)} />
    <Route path="orcamento/incorporacao" element={w(<IncorporacaoPage />)} />
  </Route>
)
