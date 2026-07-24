import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

// Suprimentos — página única com abas (réplica do protótipo Malha), self-contained.
const SuprimentosPage = lazy(() => import('./pages/SuprimentosPage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando Suprimentos…</div>}>
      {element}
    </Suspense>
  )
}

/** Rota do SCM sob `/app/scm`, atrás do entitlement `scm`. */
export const scmRoutes = (
  <Route element={<ModuleRoute module="scm" />}>
    <Route path="scm" element={w(<SuprimentosPage />)} />
  </Route>
)
