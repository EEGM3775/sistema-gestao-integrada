import type { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  /** `false` cola o conteúdo na borda (tabelas, listas divididas por `--line`). */
  pad?: boolean
}

/**
 * Superfície da Malha (identidade §5.3): `--surface` — **nunca branco puro**,
 * borda `--line`, raio `--r-md`. Acompanha o tema pelos tokens, sem cor fixa.
 */
export function Card({ children, pad = true, style, ...rest }: CardProps) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)',
        boxShadow: 'var(--shadow-sm)',
        padding: pad ? 16 : 0,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  )
}
