import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'

const TerritorioPage = lazy(() => import('./pages/TerritorioPage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando Mapas…</div>}>
      {element}
    </Suspense>
  )
}

/**
 * `/app/maps` **sem** `ModuleRoute`, de propósito.
 *
 * A metade Operação (`Local`) é fundação e vale para todo tenant; é a página que
 * decide, por aba, o que mostrar atrás do cadeado. Pendurar a rota inteira no
 * entitlement daria 403 na tela que existe justamente para quem ainda não
 * contratou o módulo entender o que ele faz.
 */
export const mapsRoutes = <Route path="maps" element={w(<TerritorioPage />)} />
