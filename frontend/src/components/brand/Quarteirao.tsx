import React from 'react'

/**
 * Marco "o Quarteirão" (docs/identidade-visual.md §2) — quatro avenidas girando
 * ao redor da praça central (a plataforma). Giro sempre horário: Originar (verde,
 * esquerda) → Construir (âmbar, topo) → Negociar (coral, direita) → Operar (teal,
 * base). NUNCA rotacionar/espelhar; a praça NUNCA recebe cor de edição.
 *
 * Variante padrão (app): tile arredondado + praça na tinta do tema (`--ink`),
 * como no shell do protótipo. Passe `tile={null}` para desenhar sem fundo.
 */
interface QuarteiraoProps {
  size?: number
  /** Cor do tile de fundo; `null` desenha sem fundo. Default: `var(--inset)`. */
  tile?: string | null
  /** Cor da praça central. Default: `var(--ink)` (acompanha o tema). */
  praca?: string
  radius?: number
  className?: string
  title?: string
}

export const Quarteirao: React.FC<QuarteiraoProps> = ({
  size = 34,
  tile = 'var(--inset)',
  praca = 'var(--ink)',
  radius = 20,
  className,
  title = 'Marco SGI',
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 96 96"
    className={className}
    style={{ flex: 'none' }}
    role="img"
    aria-label={title}
  >
    {tile !== null && <rect width="96" height="96" rx={radius} fill={tile} />}
    <rect x="14" y="14" width="14" height="48" fill="#3E9C6E" />{/* Originar */}
    <rect x="32" y="14" width="50" height="14" fill="#E79A22" />{/* Construir */}
    <rect x="68" y="32" width="14" height="50" fill="#E4655F" />{/* Negociar */}
    <rect x="14" y="68" width="50" height="14" fill="#1D9AA6" />{/* Operar */}
    <rect x="42" y="42" width="12" height="12" fill={praca} />{/* praça = plataforma */}
  </svg>
)

export default Quarteirao
