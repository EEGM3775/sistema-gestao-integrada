import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'

const LandingHeader: React.FC = () => {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 transition-shadow duration-300"
      style={{
        background: '#FFFFFF',
        boxShadow: scrolled ? 'var(--shadow-md)' : 'none',
        borderBottom: scrolled ? 'none' : '1px solid #e9ecef',
      }}
    >
      <div className="max-w-6xl mx-auto px-6 flex items-center justify-between h-[70px]">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2">
          <span
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            SGI
          </span>
          <span
            className="hidden sm:block text-sm font-medium"
            style={{ color: 'var(--color-text-muted)' }}
          >
            Gestão Integrada
          </span>
        </Link>

        {/* Nav desktop */}
        <nav className="hidden md:flex items-center gap-8">
          {[
            { label: 'Funcionalidades', href: '#modulos' },
            { label: 'Módulos', href: '#modulos' },
            { label: 'Segurança', href: '#seguranca' },
          ].map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="text-sm font-medium transition-colors duration-150"
              style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}
              onMouseEnter={(e) => ((e.target as HTMLElement).style.color = 'var(--color-brand)')}
              onMouseLeave={(e) => ((e.target as HTMLElement).style.color = 'var(--color-text)')}
            >
              {item.label}
            </a>
          ))}
        </nav>

        {/* CTA desktop */}
        <div className="hidden md:flex items-center gap-3">
          <Link
            to="/login"
            className="text-sm font-semibold px-5 py-2 rounded-lg transition-all duration-150"
            style={{
              fontFamily: 'var(--font-body)',
              color: 'var(--color-brand)',
              border: '2px solid var(--color-brand)',
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget
              el.style.background = 'var(--color-brand)'
              el.style.color = '#FFFFFF'
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget
              el.style.background = 'transparent'
              el.style.color = 'var(--color-brand)'
            }}
          >
            Acessar
          </Link>
          <a
            href="#solicitar-demo"
            className="text-sm font-semibold px-5 py-2 rounded-lg transition-all duration-150"
            style={{
              fontFamily: 'var(--font-body)',
              background: 'var(--color-brand)',
              color: '#FFFFFF',
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')
            }
          >
            Solicitar Demo
          </a>
        </div>

        {/* Hamburguer mobile */}
        <button
          className="md:hidden p-2 rounded-lg"
          style={{ color: 'var(--color-brand)' }}
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="Menu"
        >
          {menuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Menu mobile */}
      {menuOpen && (
        <div
          className="md:hidden border-t px-6 py-4 flex flex-col gap-4"
          style={{ background: '#FFFFFF', borderColor: '#e9ecef' }}
        >
          {['Funcionalidades', 'Módulos', 'Segurança'].map((label) => (
            <a
              key={label}
              href="#modulos"
              className="text-sm font-medium"
              style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}
              onClick={() => setMenuOpen(false)}
            >
              {label}
            </a>
          ))}
          <Link
            to="/login"
            className="text-sm font-semibold text-center py-2 rounded-lg border-2"
            style={{
              borderColor: 'var(--color-brand)',
              color: 'var(--color-brand)',
              fontFamily: 'var(--font-body)',
            }}
            onClick={() => setMenuOpen(false)}
          >
            Acessar
          </Link>
          <a
            href="#solicitar-demo"
            className="text-sm font-semibold text-center py-2 rounded-lg"
            style={{
              background: 'var(--color-brand)',
              color: '#FFFFFF',
              fontFamily: 'var(--font-body)',
            }}
            onClick={() => setMenuOpen(false)}
          >
            Solicitar Demo
          </a>
        </div>
      )}
    </header>
  )
}

export default LandingHeader
