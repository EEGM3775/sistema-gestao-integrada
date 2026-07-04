import React from 'react'
import { LogOut, HardHat, BarChart3, TrendingUp, UserCog, Plane, Brain, Building2, Users, Truck, CalendarDays } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useNavigate } from 'react-router-dom'

const MODULE_LABELS: Record<string, { label: string; icon: React.ReactNode }> = {
  erp_financeiro: { label: 'ERP / Financeiro',  icon: <BarChart3 size={16} /> },
  rh:             { label: 'RH',                 icon: <UserCog size={16} /> },
  crm:            { label: 'CRM',                icon: <TrendingUp size={16} /> },
  drone:          { label: 'Drone',              icon: <Plane size={16} /> },
}

const BASE_ITEMS = [
  { label: 'Empreendimentos', icon: <Building2 size={16} /> },
  { label: 'Obras',           icon: <HardHat size={16} /> },
  { label: 'Clientes',        icon: <Users size={16} /> },
  { label: 'Fornecedores',    icon: <Truck size={16} /> },
  { label: 'Diário / IA',     icon: <Brain size={16} /> },
  { label: 'Calendário',      icon: <CalendarDays size={16} /> },
]

const AppStubPage: React.FC = () => {
  const { user, modules, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-bg-alt)' }}>

      {/* Topbar */}
      <header
        className="h-14 flex items-center justify-between px-6 shrink-0"
        style={{ background: 'var(--color-brand-app)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}
      >
        <span
          className="text-xl font-extrabold tracking-tight"
          style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
        >
          SGI
        </span>
        <div className="flex items-center gap-4">
          <span className="text-sm" style={{ color: 'rgba(255,255,255,0.7)', fontFamily: 'var(--font-body)' }}>
            {user?.username}
          </span>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg transition-all duration-150"
            style={{
              fontFamily: 'var(--font-body)',
              color: 'rgba(255,255,255,0.7)',
              background: 'rgba(255,255,255,0.08)',
              border: 'none',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.15)')}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.08)')}
          >
            <LogOut size={14} /> Sair
          </button>
        </div>
      </header>

      {/* Conteúdo */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-16">
        <div className="w-full max-w-lg text-center">

          {/* Boas-vindas */}
          <div
            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-6"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF' }}
          >
            <HardHat size={32} />
          </div>

          <h1
            className="text-3xl font-bold mb-2"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            Bem-vindo, {user?.username}!
          </h1>
          <p
            className="text-sm mb-10"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
          >
            Login realizado com sucesso. O dashboard está em construção.
          </p>

          {/* Módulos ativos */}
          <div
            className="rounded-xl p-6 mb-6 text-left"
            style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}
          >
            <h3
              className="text-sm font-semibold uppercase tracking-widest mb-4"
              style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
            >
              Módulos base
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {BASE_ITEMS.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                  style={{
                    background: 'var(--color-bg-alt)',
                    color: 'var(--color-brand)',
                    fontFamily: 'var(--font-body)',
                  }}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </div>
              ))}
            </div>

            {modules.length > 0 && (
              <>
                <h3
                  className="text-sm font-semibold uppercase tracking-widest mt-5 mb-4"
                  style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
                >
                  Módulos contratados
                </h3>
                <div className="grid grid-cols-2 gap-2">
                  {modules.map((code) => {
                    const m = MODULE_LABELS[code]
                    if (!m) return null
                    return (
                      <div
                        key={code}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium"
                        style={{
                          background: '#e8f0fb',
                          color: 'var(--color-brand)',
                          fontFamily: 'var(--font-body)',
                        }}
                      >
                        {m.icon}
                        <span>{m.label}</span>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>

          <p
            className="text-xs"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
          >
            Os módulos e o dashboard completo serão implementados nas próximas fases.
          </p>
        </div>
      </main>
    </div>
  )
}

export default AppStubPage
