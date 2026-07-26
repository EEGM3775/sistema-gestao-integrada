import type { ReactNode } from 'react'

interface SectionHeadProps {
  children: ReactNode
  right?: ReactNode
  /**
   * Cor de **endereço no ciclo** (`--st-orig/const/neg/oper`) — os tokens
   * seguros para texto da identidade §5.3. Ausente = seção transversal.
   */
  estagio?: string
  sub?: string
}

export function SectionHead({ children, right, estagio, sub }: SectionHeadProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, marginBottom: 12 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {estagio && (
            <span
              style={{ width: 8, height: 8, borderRadius: 2.5, background: estagio, flex: 'none' }}
              aria-hidden
            />
          )}
          <h2
            style={{
              fontSize: 11,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: estagio ?? 'var(--ink-3)',
              fontWeight: 700,
              fontFamily: 'var(--sans)',
            }}
          >
            {children}
          </h2>
        </div>
        {sub && <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 3 }}>{sub}</p>}
      </div>
      {right && <div style={{ marginLeft: 'auto', flex: 'none' }}>{right}</div>}
    </div>
  )
}
