import type { ReactElement } from 'react'
import { Outlet } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { AccessNotice } from './AccessNotice'

interface AdminRouteProps {
  /** Uso como wrapper direto; se ausente, funciona como layout route via `<Outlet/>`. */
  children?: ReactElement
}

/**
 * Guarda de rota da administração do tenant (achado F7). Irmão do
 * `ModuleRoute`: lá o critério é entitlement do tenant, aqui é o papel do
 * usuário (`is_tenant_admin`).
 *
 * Existia só o comentário "guardado por is_tenant_admin" em `App.tsx` e a trava
 * do link na sidebar — URL digitada direto montava a tela de papéis/usuários. A
 * API barra depois (a IAM exige `is_tenant_admin` nesses endpoints), mas a UI já
 * tinha aparecido, o que é exatamente o padrão que o F4 fechou nos módulos.
 */
export default function AdminRoute({ children }: AdminRouteProps) {
  const { loading, isTenantAdmin } = useAuth()

  if (loading) {
    return (
      <div className="px-6 py-8" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
        Carregando…
      </div>
    )
  }

  if (!isTenantAdmin) {
    return (
      <AccessNotice
        icon={<ShieldAlert size={26} />}
        title="Área de administração restrita"
        message="Só o administrador da empresa gerencia papéis e usuários. Se você precisa desse acesso, peça a quem administra o seu tenant."
      />
    )
  }

  return children ?? <Outlet />
}
