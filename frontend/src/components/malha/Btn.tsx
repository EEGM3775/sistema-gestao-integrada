import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react'

type Variante = 'primary' | 'ghost' | 'brand' | 'perigo'

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variante
  tam?: 'sm' | 'md'
  children: ReactNode
}

/**
 * Botão da Malha. Promovido dos kits locais (SCM/SIL/Orçamento tinham cópias
 * idênticas) quando o IE.0c precisou de um botão em componente **compartilhado**
 * — um primitivo do kit não pode importar do kit de um módulo.
 *
 * Cores só por token, como o resto da Malha: acompanha claro/escuro sem reescrita.
 */
export function Btn({ variant = 'ghost', tam = 'md', children, style, ...rest }: BtnProps) {
  const v: Record<Variante, CSSProperties> = {
    primary: { background: 'var(--accent)', color: '#1A1204' },
    ghost: { background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)' },
    brand: { background: 'var(--brand)', color: 'var(--brand-ink)' },
    perigo: {
      background: 'var(--danger-soft)', color: 'var(--danger-ink)',
      border: '1px solid var(--danger-soft)',
    },
  }
  const t: Record<string, CSSProperties> = {
    sm: { fontSize: 12, padding: '5px 10px', gap: 5 },
    md: { fontSize: 13, padding: '8px 14px', gap: 7 },
  }
  return (
    <button
      {...rest}
      style={{
        display: 'inline-flex', alignItems: 'center', fontWeight: 650,
        borderRadius: 'var(--r-sm)', border: '1px solid transparent', whiteSpace: 'nowrap',
        cursor: rest.disabled ? 'not-allowed' : 'pointer', opacity: rest.disabled ? 0.5 : 1,
        ...t[tam], ...v[variant], ...style,
      }}
    >
      {children}
    </button>
  )
}
