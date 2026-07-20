import React, { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Building2, HardHat, Users, Truck,
  BarChart3, UserCog, TrendingUp, Brain, Plane,
  CalendarDays, PanelLeft, Lock, ShieldCheck,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

interface NavItem {
  label: string
  icon: React.ReactNode
  to: string
  module?: string       // entitlement code — se definido, item some se não tiver o módulo
  adminOnly?: boolean   // só aparece para admin do tenant
  implemented: boolean  // quando false: mostra o item mas não navega
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Início',          icon: <LayoutDashboard size={20} />, to: '/app/dashboard',      implemented: false },
  // ── Base ──
  { label: 'Empreendimentos', icon: <Building2 size={20} />,       to: '/app/empreendimentos',implemented: true },
  { label: 'Obras',           icon: <HardHat size={20} />,         to: '/app/obras',           implemented: true },
  { label: 'Clientes',        icon: <Users size={20} />,           to: '/app/clientes',        implemented: true },
  { label: 'Fornecedores',    icon: <Truck size={20} />,           to: '/app/fornecedores',    implemented: true },
  { label: 'RH',              icon: <UserCog size={20} />,         to: '/app/rh',              module: 'rh',             implemented: true },
  { label: 'Calendário',      icon: <CalendarDays size={20} />,    to: '/app/calendario',      implemented: true },
  // ── Módulos pagos ──
  { label: 'ERP',             icon: <BarChart3 size={20} />,       to: '/app/erp',             module: 'erp_financeiro', implemented: true },
  { label: 'Diário / IA',    icon: <Brain size={20} />,            to: '/app/diario',          implemented: true },
  { label: 'CRM',             icon: <TrendingUp size={20} />,      to: '/app/crm',             module: 'crm',            implemented: true },
  { label: 'Drone',           icon: <Plane size={20} />,           to: '/app/drone',           module: 'drone',          implemented: false },
  // ── Administração do tenant ──
  { label: 'Papéis e Acessos', icon: <ShieldCheck size={20} />,    to: '/app/admin/papeis',    adminOnly: true,          implemented: true },
  { label: 'Usuários',         icon: <Users size={20} />,          to: '/app/admin/usuarios',  adminOnly: true,          implemented: true },
]

const SEPARATOR_BEFORE = new Set(['ERP', 'Papéis e Acessos'])

export const AppSidebar: React.FC = () => {
  const { hasModule, isTenantAdmin } = useAuth()
  const [collapsed, setCollapsed] = useState(() =>
    localStorage.getItem('sgi_sidebar_collapsed') === 'true'
  )

  useEffect(() => {
    localStorage.setItem('sgi_sidebar_collapsed', String(collapsed))
  }, [collapsed])

  const visibleItems = NAV_ITEMS.filter(
    (item) => (!item.module || hasModule(item.module)) && (!item.adminOnly || isTenantAdmin)
  )

  return (
    <aside
      className="flex flex-col shrink-0 h-full transition-all duration-200"
      style={{
        width: collapsed ? '56px' : '220px',
        background: 'var(--color-brand-app)',
        borderRight: '1px solid rgba(255,255,255,0.07)',
      }}
    >
      {/* Toggle */}
      <div className="flex items-center h-14 px-3 shrink-0" style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        {!collapsed && (
          <span
            className="flex-1 text-lg font-extrabold tracking-tight truncate"
            style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
          >
            SGI
          </span>
        )}
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="p-1.5 rounded-lg transition-colors duration-150"
          style={{ color: 'rgba(255,255,255,0.5)', background: 'none', border: 'none', cursor: 'pointer' }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = '#FFFFFF')}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.5)')}
          aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
        >
          <PanelLeft size={18} />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 flex flex-col gap-0.5 px-2">
        {visibleItems.map((item) => (
          <React.Fragment key={item.label}>
            {SEPARATOR_BEFORE.has(item.label) && (
              <div className="my-2 mx-1" style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }} />
            )}
            <SidebarItem item={item} collapsed={collapsed} />
          </React.Fragment>
        ))}
      </nav>
    </aside>
  )
}

const SidebarItem: React.FC<{ item: NavItem; collapsed: boolean }> = ({ item, collapsed }) => {
  const baseStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: collapsed ? '8px' : '8px 10px',
    borderRadius: '8px',
    cursor: item.implemented ? 'pointer' : 'default',
    transition: 'background 0.15s',
    textDecoration: 'none',
    color: item.implemented ? 'rgba(255,255,255,0.75)' : 'rgba(255,255,255,0.35)',
    fontFamily: 'var(--font-body)',
    fontSize: '0.875rem',
    fontWeight: 500,
    width: '100%',
    opacity: item.implemented ? 1 : 0.6,
    justifyContent: collapsed ? 'center' : 'flex-start',
    position: 'relative',
  }

  const content = (
    <>
      <span className="shrink-0">{item.icon}</span>
      {!collapsed && <span className="truncate flex-1">{item.label}</span>}
      {!collapsed && !item.implemented && (
        <Lock size={12} style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
      )}
    </>
  )

  if (!item.implemented) {
    return (
      <span
        style={baseStyle}
        title={collapsed ? item.label : 'Em construção'}
      >
        {content}
      </span>
    )
  }

  return (
    <NavLink
      to={item.to}
      style={({ isActive }) => ({
        ...baseStyle,
        background: isActive ? 'rgba(255,255,255,0.12)' : 'transparent',
        color: isActive ? '#FFFFFF' : 'rgba(255,255,255,0.75)',
      })}
      title={collapsed ? item.label : undefined}
    >
      {content}
    </NavLink>
  )
}

export default AppSidebar
