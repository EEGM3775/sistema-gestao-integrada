import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import { Card } from './Card'

/** Anel de carregamento no acento — a única animação de espera da Malha. */
export const Spinner = ({ size = 24 }: { size?: number }) => (
  <span
    style={{
      width: size,
      height: size,
      borderRadius: 999,
      border: '2.5px solid var(--line)',
      borderTopColor: 'var(--accent)',
      display: 'inline-block',
      animation: 'malha-spin .8s linear infinite',
    }}
  />
)

/**
 * "Carregando…" **sempre diz o quê** (anti-padrão §11: nunca um spinner mudo).
 */
export function Loading({ o }: { o: string }) {
  return (
    <div style={{ display: 'grid', placeItems: 'center', gap: 12, padding: 48 }}>
      <Spinner />
      <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Carregando {o}…</span>
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <Card
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
        padding: 40,
        color: 'var(--ink-3)',
      }}
    >
      <Inbox size={30} style={{ opacity: 0.7 }} />
      <span style={{ fontSize: 13, textAlign: 'center', maxWidth: 460 }}>{children}</span>
    </Card>
  )
}

/**
 * O selo de honestidade da régua (frontend.md §1.6.4): onde ainda **não há
 * fonte**, a tela diz "em breve" — nunca inventa um número para preencher o
 * espaço.
 */
export function EmBreve({ children }: { children?: ReactNode }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontSize: 11,
        fontWeight: 600,
        color: 'var(--ink-3)',
        background: 'var(--inset)',
        border: '1px dashed var(--line)',
        borderRadius: 999,
        padding: '2px 9px',
      }}
    >
      {children ?? 'em breve'}
    </span>
  )
}
