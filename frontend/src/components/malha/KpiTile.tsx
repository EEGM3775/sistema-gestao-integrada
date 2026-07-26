import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Card } from './Card'
import { EmBreve } from './States'

interface KpiTileProps {
  label: string
  /** O número **real**. `null` só é aceito junto de `pendente` — ver `EmBreve`. */
  valor: ReactNode | null
  /** A base do número (anti-padrão §11: número sem unidade, percentual sem base). */
  base?: string
  icon?: ReactNode
  /** Rota do módulo dono do dado — é o que torna a integração clicável (§1.6.6). */
  to?: string
  /** Sem fonte de dado ainda: rotula "em breve" em vez de fabricar. */
  pendente?: boolean
  /** Módulo de origem, exibido como procedência do número. */
  origem?: string
}

/**
 * Mosaico de KPI do hub. O valor é sempre agregado **real** do backend ou o selo
 * "em breve" — a régua (frontend.md §1.6.4) proíbe número fabricado.
 */
export function KpiTile({ label, valor, base, icon, to, pendente, origem }: KpiTileProps) {
  const corpo = (
    <Card
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        height: '100%',
        transition: 'border-color .14s, box-shadow .14s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon && <span style={{ color: 'var(--ink-3)', display: 'grid', placeItems: 'center' }}>{icon}</span>}
        <span
          style={{
            fontSize: 10.5,
            letterSpacing: '0.07em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
            fontWeight: 700,
            lineHeight: 1.3,
          }}
        >
          {label}
        </span>
        {to && <ArrowUpRight size={13} style={{ marginLeft: 'auto', color: 'var(--ink-3)', flexShrink: 0 }} />}
      </div>

      {pendente ? (
        <EmBreve />
      ) : (
        <span
          className="num"
          style={{ fontSize: 23, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.1 }}
        >
          {valor}
        </span>
      )}

      {(base || origem) && (
        <span style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 'auto', lineHeight: 1.4 }}>
          {base}
          {base && origem ? ' · ' : ''}
          {origem}
        </span>
      )}
    </Card>
  )

  if (!to) return corpo
  return (
    <Link to={to} style={{ textDecoration: 'none', display: 'block', height: '100%' }}>
      {corpo}
    </Link>
  )
}
