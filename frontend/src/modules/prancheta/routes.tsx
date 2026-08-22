import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'

const PranchetaPage = lazy(() => import('./pages/PranchetaPage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando a Prancheta…</div>}>
      {element}
    </Suspense>
  )
}

/**
 * `/app/prancheta` **sem** `ModuleRoute`, pelo mesmo motivo do Maps: a tela que
 * explica o módulo é justamente a que quem ainda não o contratou precisa ver, e
 * um guard de rota lhe daria "acesso negado" no lugar dela. O gate real continua
 * onde sempre esteve — no backend, que responde 403 a qualquer chamada sem o
 * entitlement `prancheta`; a página só decide entre o acervo e o convite.
 */
export const pranchetaRoutes = <Route path="prancheta" element={w(<PranchetaPage />)} />
