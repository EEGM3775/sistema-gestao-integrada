import React, { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LogOut, ChevronDown, User, KeyRound } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { ChangePasswordModal } from '@/components/ChangePasswordModal'

export const AppTopbar: React.FC = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
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
      className="h-14 flex items-center justify-between px-5 shrink-0"
      style={{
        background: 'var(--color-brand-app)',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
      }}
    >
      {/* Logo (mobile — sidebar recolhida mostra o logo aqui) */}
      <Link
        to="/app/dashboard"
        className="lg:hidden text-xl font-extrabold tracking-tight"
        style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
      >
        SGI
      </Link>

      {/* Spacer desktop */}
      <div className="hidden lg:block" />

      {/* Direita: tenant + user menu */}
      <div className="flex items-center gap-3">
        {/* Badge tenant */}
        <span
          className="hidden sm:inline-block text-xs font-semibold px-2.5 py-1 rounded-full"
          style={{
            background: 'rgba(255,255,255,0.1)',
            color: 'rgba(255,255,255,0.7)',
            fontFamily: 'var(--font-body)',
          }}
        >
          SGI Demo
        </span>

        {/* User dropdown */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors duration-150"
            style={{
              background: menuOpen ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.08)',
              border: 'none',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.12)')}
            onMouseLeave={(e) => {
              if (!menuOpen) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.08)'
            }}
          >
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(255,255,255,0.2)' }}
            >
              <User size={14} style={{ color: '#FFFFFF' }} />
            </div>
            <span
              className="text-sm font-medium max-w-[100px] truncate"
              style={{ color: '#FFFFFF', fontFamily: 'var(--font-body)' }}
            >
              {user?.username ?? 'Usuário'}
            </span>
            <ChevronDown
              size={14}
              style={{
                color: 'rgba(255,255,255,0.6)',
                transform: menuOpen ? 'rotate(180deg)' : 'rotate(0)',
                transition: 'transform 0.2s',
              }}
            />
          </button>

          {menuOpen && (
            <div
              className="absolute right-0 top-full mt-2 w-44 rounded-xl py-1 z-50"
              style={{
                background: '#FFFFFF',
                boxShadow: 'var(--shadow-lg)',
                border: '1px solid #e2e8f0',
              }}
            >
              <div
                className="px-4 py-2.5 border-b"
                style={{ borderColor: '#e2e8f0' }}
              >
                <p className="text-xs font-semibold truncate" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                  {user?.username}
                </p>
                <p className="text-xs truncate" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                  {user?.email ?? ''}
                </p>
              </div>
              <button
                onClick={() => { setMenuOpen(false); setPwOpen(true) }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-150"
                style={{
                  fontFamily: 'var(--font-body)',
                  color: 'var(--color-text)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#f8fafc')}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = 'none')}
              >
                <KeyRound size={14} /> Alterar senha
              </button>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-150"
                style={{
                  fontFamily: 'var(--font-body)',
                  color: 'var(--color-danger)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#fff5f5')}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = 'none')}
              >
                <LogOut size={14} /> Sair da conta
              </button>
            </div>
          )}
        </div>
      </div>

      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}
    </header>
  )
}

export default AppTopbar
