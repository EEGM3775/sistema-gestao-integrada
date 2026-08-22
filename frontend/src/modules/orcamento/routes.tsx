import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const HubPage = lazy(() => import('./pages/HubPage'))
const ObrasOrcamentosPage = lazy(() => import('./pages/ObrasOrcamentosPage'))
const OrcarPage = lazy(() => import('./pages/OrcarPage'))
const EncargosPage = lazy(() => import('./pages/EncargosPage'))
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
    {/* Orçar tem três níveis, cada um com endereço próprio: as obras, os
        orçamentos de uma obra e a planilha. É o que dá voltar, link colável e
        trilha — um `?orcamento=` no meio de uma tela de lista não dá nenhum
        dos três. */}
    <Route path="orcamento/orcar" element={w(<ObrasOrcamentosPage />)} />
    <Route path="orcamento/orcar/obra/:obraId" element={w(<ObrasOrcamentosPage />)} />
    <Route path="orcamento/orcar/orcamento/:orcamentoId" element={w(<OrcarPage />)} />
    <Route path="orcamento/encargos" element={w(<EncargosPage />)} />
    <Route path="orcamento/controlar" element={w(<ControlarPage />)} />
    <Route path="orcamento/cronograma" element={w(<CronogramaPage />)} />
    <Route path="orcamento/bases" element={w(<BasesPage />)} />
    <Route path="orcamento/incorporacao" element={w(<IncorporacaoPage />)} />
  </Route>
)
