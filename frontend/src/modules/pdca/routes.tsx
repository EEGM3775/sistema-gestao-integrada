import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const ObrasPage = lazy(() => import('./pages/ObrasPage'))
const CronogramaPage = lazy(() => import('./pages/CronogramaPage'))
const ExpedientePage = lazy(() => import('./pages/ExpedientePage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando o Planejamento…</div>}>
      {element}
    </Suspense>
  )
}

/**
 * Rotas do PDCA sob `/app/pdca`, atrás do entitlement `pdca`.
 *
 * O endereço carrega a **obra** e o **cronograma**, nesta ordem, porque a
 * unidade de trabalho deste módulo é a obra (planta §5.1): o link colado no
 * grupo da obra abre o plano daquela obra, e não uma tela que pede para
 * escolher de novo. A atividade viaja em `?atividade=` — ela é um recorte
 * dentro do plano, não um lugar.
 */
export const pdcaRoutes = (
  <Route element={<ModuleRoute module="pdca" />}>
    <Route path="pdca" element={w(<ObrasPage />)} />
    <Route path="pdca/obra/:obraId/cronograma/:cronogramaId" element={w(<CronogramaPage />)} />
    {/* O expediente é da **empresa**, não de uma obra — por isso fica fora do
        endereço com obra. Um calendário de obra é caso particular dele. */}
    <Route path="pdca/expediente" element={w(<ExpedientePage />)} />
  </Route>
)
