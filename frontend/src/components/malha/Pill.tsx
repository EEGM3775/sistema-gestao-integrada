import React from 'react'

/**
 * Pílula de estado (docs/identidade-visual.md §5.2 + §8): estado **nomeado e
 * medido**, nunca cor sozinha. Os semânticos de UI NÃO reutilizam cor de estágio
 * do ciclo como significado. Use `pulse` para "em andamento" (ponto que respira).
 *
 * ✓ "recebido parcial · 60 de 120 kg"   ✗ "pendente…"
 */
export type PillKind = 'slate' | 'info' | 'amber' | 'good' | 'danger' | 'net'

const KIND: Record<PillKind, { bg: string; fg: string }> = {
  slate:  { bg: 'var(--inset)',       fg: 'var(--ink-2)' },
  info:   { bg: 'var(--info-soft)',   fg: 'var(--info-ink)' },
  amber:  { bg: 'var(--accent-soft)', fg: 'var(--accent-ink)' },
  good:   { bg: 'var(--good-soft)',   fg: 'var(--good-ink)' },
  danger: { bg: 'var(--danger-soft)', fg: 'var(--danger-ink)' },
  net:    { bg: 'var(--net-soft)',    fg: 'var(--net-ink)' },
}

interface PillProps {
  kind?: PillKind
  /** Ponto pulsante à esquerda (estado ativo/em andamento). */
  pulse?: boolean
  /** Ícone lucide (renderizado a 12px). */
  icon?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export const Pill: React.FC<PillProps> = ({ kind = 'slate', pulse, icon, children, className }) => {
  const c = KIND[kind]
  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontSize: 11.5,
        fontWeight: 650,
        lineHeight: 1.4,
        padding: '3px 9px',
        borderRadius: 999,
        whiteSpace: 'nowrap',
        background: c.bg,
        color: c.fg,
      }}
    >
      {pulse && <span className="malha-dot" />}
      {icon && (
        <span style={{ display: 'grid', placeItems: 'center', width: 12, height: 12 }}>
          {React.cloneElement(icon as React.ReactElement<{ size?: number; strokeWidth?: number }>, { size: 12, strokeWidth: 2.4 })}
        </span>
      )}
      {children}
    </span>
  )
}

export default Pill
