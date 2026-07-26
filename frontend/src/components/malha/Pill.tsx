import type { ReactNode } from 'react'

/**
 * Semânticos de UI (identidade §5.2) + `accent` para "requer decisão".
 * As cores de **estágio** do ciclo nunca entram aqui — estado de interface não
 * reutiliza cor de estágio como significado (anti-padrão §11).
 */
export type PillKind = 'good' | 'info' | 'danger' | 'net' | 'accent' | 'slate'

const KIND: Record<PillKind, { bg: string; fg: string }> = {
  good: { bg: 'var(--good-soft)', fg: 'var(--good-ink)' },
  info: { bg: 'var(--info-soft)', fg: 'var(--info-ink)' },
  danger: { bg: 'var(--danger-soft)', fg: 'var(--danger-ink)' },
  net: { bg: 'var(--net-soft)', fg: 'var(--net-ink)' },
  accent: { bg: 'var(--accent-soft)', fg: 'var(--accent-ink)' },
  slate: { bg: 'var(--surface-2)', fg: 'var(--ink-3)' },
}

/** Estado **nomeado** (§8): cor sozinha nunca comunica — a pílula sempre traz rótulo. */
export function Pill({
  kind = 'slate',
  pulse,
  children,
}: {
  kind?: PillKind
  pulse?: boolean
  children: ReactNode
}) {
  const c = KIND[kind]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        background: c.bg,
        color: c.fg,
        borderRadius: 999,
        padding: '3px 9px',
        fontSize: 11.5,
        fontWeight: 600,
        lineHeight: 1.4,
        whiteSpace: 'nowrap',
      }}
    >
      {pulse && <span className="malha-dot" />}
      {children}
    </span>
  )
}
