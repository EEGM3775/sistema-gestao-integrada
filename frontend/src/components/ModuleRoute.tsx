import type { ReactElement } from 'react'
import { Outlet } from 'react-router-dom'
import { PackageX } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { AccessNotice } from './AccessNotice'

/** Rótulos legíveis dos módulos pagos, para a tela de acesso negado. */
const MODULE_LABELS: Record<string, string> = {
  erp_financeiro: 'ERP Financeiro',
  crm: 'CRM',
  rh: 'RH',
  drone: 'Drone',
}

interface ModuleRouteProps {
  /** Código do entitlement exigido (ex.: `erp_financeiro`, `crm`). */
  module: string
  /** Uso como wrapper direto; se ausente, funciona como layout route via `<Outlet/>`. */
  children?: ReactElement
}

/**
 * Guarda de rota por entitlement de módulo (achado F4). O menu (AppSidebar) já
 * esconde o item de quem não tem o módulo, mas a navegação direta por URL
 * chegava à página e batia num 403 cru da API. Aqui a falta de entitlement vira
 * uma tela amigável, antes de qualquer chamada ao backend.
 */
export default function ModuleRoute({ module, children }: ModuleRouteProps) {
  const { loading, hasModule } = useAuth()

  if (loading) {
    return (
      <div className="px-6 py-8" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
        Carregando…
      </div>
    )
  }

  if (!hasModule(module)) {
    const nome = MODULE_LABELS[module] ?? module
    return (
      <AccessNotice
        icon={<PackageX size={26} />}
        title={`Módulo ${nome} não disponível`}
        message={`Seu plano não inclui o módulo ${nome}. Fale com o administrador do tenant para contratá-lo ou liberar seu acesso.`}
      />
    )
  }

  return children ?? <Outlet />
}
