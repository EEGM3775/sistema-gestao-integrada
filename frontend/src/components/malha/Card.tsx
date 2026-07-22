import React from 'react'

/**
 * Superfície-base do produto (docs/identidade-visual.md §5.3): `--surface` (nunca
 * branco puro), borda `--line`, raio `--r-lg`, sombra discreta. Acompanha o tema.
 */
interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Padding interno; `false` para controlar por conta própria. */
  pad?: boolean
}

export const Card: React.FC<CardProps> = ({ pad = true, style, children, ...rest }) => (
  <div
    style={{
      background: 'var(--surface)',
      border: '1px solid var(--line)',
      borderRadius: 'var(--r-lg)',
      boxShadow: 'var(--shadow-sm)',
      ...(pad ? { padding: 18 } : null),
      ...style,
    }}
    {...rest}
  >
    {children}
  </div>
)

export default Card
