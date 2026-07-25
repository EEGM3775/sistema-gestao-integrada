import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

// Estoque & Logística — página única com abas (régua do SCM), self-contained.
const LogisticaPage = lazy(() => import('./pages/LogisticaPage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando Estoque &amp; Logística…</div>}>
      {element}
    </Suspense>
  )
}

/** Rota do SIL sob `/app/sil`, atrás do entitlement `sil`. */
export const silRoutes = (
  <Route element={<ModuleRoute module="sil" />}>
    <Route path="sil" element={w(<LogisticaPage />)} />
  </Route>
)
