import React from 'react'
import { Link } from 'react-router-dom'

/**
 * Moldura das telas públicas de conta (recuperar senha, redefinir, confirmar
 * e-mail). Reaproveita a linguagem visual do `LoginPage` sem arrastar o painel
 * lateral de marketing: aqui o usuário está resolvendo um problema, não sendo
 * convencido do produto.
 */
export const AuthShell: React.FC<{
  icone: React.ReactNode
  titulo: string
  subtitulo?: string
  children: React.ReactNode
}> = ({ icone, titulo, subtitulo, children }) => (
  <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12" style={{ background: '#f8fafc' }}>
    <Link to="/" className="mb-8" style={{ textDecoration: 'none' }}>
      <span
        className="text-3xl font-extrabold tracking-tight"
        style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
      >
        SGI
      </span>
    </Link>

    <div
      className="w-full max-w-md rounded-2xl p-8"
      style={{ background: '#FFFFFF', boxShadow: '0 10px 40px rgba(0,0,0,0.08)' }}
    >
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: '#dcfce7', color: 'var(--color-brand)' }}
        >
          {icone}
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {titulo}
          </h1>
        </div>
      </div>

      {subtitulo && (
        <p
          className="text-sm leading-relaxed mb-6"
          style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
        >
          {subtitulo}
        </p>
      )}

      {children}
    </div>

    <p className="text-xs mt-8" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
      © {new Date().getFullYear()} SGI — Sistema de Gestão Integrada
    </p>
  </div>
)

export const campoStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 16px',
  borderRadius: '8px',
  fontSize: '0.875rem',
  outline: 'none',
  transition: 'all 150ms',
  fontFamily: 'var(--font-body)',
  border: '1.5px solid #e2e8f0',
  color: 'var(--color-text)',
  background: '#FFFFFF',
}

export const botaoPrimario: React.CSSProperties = {
  width: '100%',
  padding: '12px 20px',
  borderRadius: '8px',
  border: 'none',
  background: 'var(--color-brand)',
  color: '#FFFFFF',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  fontSize: '0.875rem',
  fontWeight: 600,
}

export const botaoSecundario: React.CSSProperties = {
  width: '100%',
  padding: '12px 20px',
  borderRadius: '8px',
  border: '1.5px solid #e2e8f0',
  background: 'none',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  fontSize: '0.875rem',
  fontWeight: 600,
  color: 'var(--color-text-muted)',
}
