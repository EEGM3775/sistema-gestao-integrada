import type { ReactElement } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

interface PlatformRouteProps {
  children?: ReactElement
}

/**
 * Guarda das telas de **plataforma** — as que operam o que vale para todos os
 * tenants (a base-mãe da ORC.8, e o que vier depois).
 *
 * Irmão do `AdminRoute` e do `ModuleRoute`, com **uma diferença deliberada**: os
 * dois primeiros explicam a recusa (`AccessNotice`: "peça a quem administra",
 * "seu plano não inclui"), porque descrevem caminhos que existem para aquele
 * usuário — ele pode pedir acesso ou contratar o módulo.
 *
 * Aqui não. Operação de plataforma não é vendável nem contratável por tenant
 * nenhum, e explicar a recusa anunciaria uma porta que não é para o lado de cá —
 * a mesma razão de a seção sumir da sidebar em vez de aparecer trancada
 * *(decisão do dono, 22/08/2026: "não pode de modo nenhum aparecer para tenant,
 * nem mesmo como trancado")*. Quem chegar pela URL é levado de volta ao início,
 * como se a rota não existisse — que, para ele, é a verdade.
 */
export default function PlatformRoute({ children }: PlatformRouteProps) {
  const { loading, isPlatformAdmin } = useAuth()

  if (loading) {
    return (
      <div
        className="px-6 py-8"
        style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}
      >
        Carregando…
      </div>
    )
  }

  if (!isPlatformAdmin) return <Navigate to="/app/dashboard" replace />

  return children ?? <Outlet />
}
