import React, { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

/**
 * Campo de senha com botão próprio de exibir/ocultar. O olho nativo do Edge é
 * escondido via `index.css` (some em re-render) — este é estável.
 */
export const PasswordField: React.FC<{
  label: string
  value: string
  onChange: (v: string) => void
  hint?: string
  autoFocus?: boolean
  autoComplete?: string
}> = ({ label, value, onChange, hint, autoFocus, autoComplete = 'off' }) => {
  const [show, setShow] = useState(false)
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}>
        {label}
      </label>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          autoComplete={autoComplete}
          required
          autoFocus={autoFocus}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg text-sm outline-none"
          style={{
            padding: '10px 40px 10px 14px',
            fontFamily: 'var(--font-body)',
            border: '1.5px solid #e2e8f0',
            color: 'var(--color-text)',
            background: '#FFFFFF',
          }}
          onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
          onBlur={(e) => (e.currentTarget.style.borderColor = '#e2e8f0')}
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setShow((v) => !v)}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded"
          style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
          aria-label={show ? 'Ocultar senha' : 'Mostrar senha'}
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      {hint && <span className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>{hint}</span>}
    </div>
  )
}

export default PasswordField
