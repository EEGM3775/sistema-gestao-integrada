import type { CSSProperties, ReactNode } from 'react'

interface NumProps {
  children: ReactNode
  size?: number
  weight?: number
  /** Token de cor (`var(--ink)`, `var(--danger-ink)`…). Nunca hex. */
  tone?: string
  align?: CSSProperties['textAlign']
  style?: CSSProperties
}

/**
 * Leitura de instrumento (identidade §6): todo preço/quantidade/código/prazo em
 * mono tabular, alinhado à direita — "colunas como réguas". A classe `.num` vem
 * de [index.css](../../index.css).
 */
export function Num({
  children,
  size = 13.5,
  weight = 600,
  tone = 'var(--ink)',
  align = 'right',
  style,
}: NumProps) {
  return (
    <span
      className="num"
      style={{ fontSize: size, fontWeight: weight, color: tone, textAlign: align, ...style }}
    >
      {children}
    </span>
  )
}
