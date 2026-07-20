import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const CrmDashboardPage = lazy(() => import('./pages/CrmDashboardPage'))
const LeadsPage = lazy(() => import('./pages/LeadsPage'))
const AccountsPage = lazy(() => import('./pages/AccountsPage'))
const ContactsPage = lazy(() => import('./pages/ContactsPage'))
const OpportunitiesPage = lazy(() => import('./pages/OpportunitiesPage'))

function CrmFallback() {
  return (
    <div className="px-6 py-8" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
      Carregando módulo CRM…
    </div>
  )
}

function withCrmFallback(element: ReactNode) {
  return <Suspense fallback={<CrmFallback />}>{element}</Suspense>
}

/**
 * Sub-rotas do CRM, registradas sob `/app/crm` em `App.tsx`. Todas sob um
 * `ModuleRoute` (F4): sem o entitlement `crm`, a navegação direta por URL cai
 * numa tela amigável em vez de um 403 cru da API.
 */
export const crmRoutes = (
  <Route element={<ModuleRoute module="crm" />}>
    <Route path="crm" element={withCrmFallback(<CrmDashboardPage />)} />
    <Route path="crm/leads" element={withCrmFallback(<LeadsPage />)} />
    <Route path="crm/accounts" element={withCrmFallback(<AccountsPage />)} />
    <Route path="crm/contacts" element={withCrmFallback(<ContactsPage />)} />
    <Route path="crm/opportunities" element={withCrmFallback(<OpportunitiesPage />)} />
  </Route>
)
