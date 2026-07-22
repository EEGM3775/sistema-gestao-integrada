import React, { useState, useRef, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, ChevronDown, ChevronRight, User, KeyRound } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { ChangePasswordModal } from '@/components/ChangePasswordModal'
import { NotificationBell } from '@/components/notifications/NotificationBell'
import { ThemeToggle } from '@/components/ThemeToggle'
import { EdicaoChip } from '@/components/brand/EdicaoChip'
import { Quarteirao } from '@/components/brand/Quarteirao'

// Rótulos de trilha por segmento de rota (declaram o endereço da tela).
const SEGMENT_LABELS: Record<string, string> = {
  dashboard: 'Início',
  empreendimentos: 'Empreendimentos',
  obras: 'Obras',
  clientes: 'Clientes',
  fornecedores: 'Fornecedores',
  erp: 'ERP / Financeiro',
  'contas-a-pagar': 'Contas a pagar',
  'contas-a-receber': 'Contas a receber',
  boletos: 'Boletos',
  rh: 'RH',
  cargos: 'Cargos',
  crm: 'CRM',
  leads: 'Leads',
  diario: 'Diário + IA',
  calendario: 'Calendário',
  drone: 'Drone',
  scm: 'Suprimentos',
  produtos: 'Produtos',
  ofertas: 'Ofertas',
  'centros-custo': 'Centros de custo',
  demandas: 'Demandas',
  cotacoes: 'Cotações',
  pedidos: 'Pedidos',
  admin: 'Administração',
  papeis: 'Papéis e Acessos',
  usuarios: 'Usuários',
}

function useBreadcrumb(): string[] {
  const { pathname } = useLocation()
  const segs = pathname.split('/').filter(Boolean)
  const appIdx = segs.indexOf('app')
  const tail = appIdx >= 0 ? segs.slice(appIdx + 1) : segs
  return tail
    .filter((s) => !/^\d+$/.test(s)) // some ids numéricos de detalhe
    .map((s) => SEGMENT_LABELS[s] ?? s)
}

export const AppTopbar: React.FC = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const crumbs = useBreadcrumb()
  const [menuOpen, setMenuOpen] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <header
      className="flex items-center gap-3.5 shrink-0 sticky top-0 z-20"
      style={{
        padding: '12px 26px',
        background: 'var(--glass)',
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        borderBottom: '1px solid var(--line)',
      }}
    >
      {/* Marco (mobile — sidebar oculta) */}
      <Link to="/app/dashboard" className="lg:hidden" aria-label="Início">
        <Quarteirao size={28} />
      </Link>

      {/* Trilha (breadcrumb) */}
      <nav className="hidden sm:flex items-center gap-2 min-w-0" style={{ fontSize: 13, color: 'var(--ink-3)', fontWeight: 500 }}>
        {crumbs.length === 0 && <b style={{ color: 'var(--ink)', fontWeight: 600 }}>Plataforma</b>}
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1
          return (
            <React.Fragment key={`${c}-${i}`}>
              {i > 0 && <ChevronRight size={14} style={{ opacity: 0.5, flex: 'none' }} />}
              <span className="truncate" style={last ? { color: 'var(--ink)', fontWeight: 600 } : undefined}>{c}</span>
            </React.Fragment>
          )
        })}
      </nav>

      {/* Chip de estágio — endereço no ciclo */}
      <EdicaoChip className="hidden md:inline-flex" />

      <div className="flex-1" />

      {/* Direita: tema · notificações · usuário */}
      <ThemeToggle />
      <NotificationBell />

      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="flex items-center gap-2 rounded-lg transition-colors duration-150"
          style={{
            padding: '5px 10px 5px 6px',
            background: menuOpen ? 'var(--surface-2)' : 'var(--surface)',
            border: '1px solid var(--line)',
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--line)')}
        >
          <div style={{ width: 26, height: 26, borderRadius: 7, background: 'linear-gradient(135deg,var(--brand-2),var(--brand))', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 700, fontSize: 11 }}>
            <User size={14} />
          </div>
          <span className="text-sm font-medium max-w-[120px] truncate" style={{ color: 'var(--ink)' }}>
            {user?.username ?? 'Usuário'}
          </span>
          <ChevronDown size={14} style={{ color: 'var(--ink-3)', transform: menuOpen ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }} />
        </button>

        {menuOpen && (
          <div
            className="absolute right-0 top-full mt-2 w-48 py-1 z-50"
            style={{ background: 'var(--surface)', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)' }}
          >
            <div className="px-4 py-2.5" style={{ borderBottom: '1px solid var(--line)' }}>
              <p className="text-xs font-semibold truncate" style={{ color: 'var(--ink)' }}>{user?.username}</p>
              <p className="text-xs truncate" style={{ color: 'var(--ink-3)' }}>{user?.email ?? ''}</p>
            </div>
            <button
              onClick={() => { setMenuOpen(false); setPwOpen(true) }}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-150"
              style={{ color: 'var(--ink-2)', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-2)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
            >
              <KeyRound size={14} /> Alterar senha
            </button>
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-150"
              style={{ color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--danger-soft)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
            >
              <LogOut size={14} /> Sair da conta
            </button>
          </div>
        )}
      </div>

      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}
    </header>
  )
}

export default AppTopbar
