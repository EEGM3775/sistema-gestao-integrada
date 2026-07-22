import React from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Card } from './Card'

/**
 * Cartão de KPI (docs/identidade-visual.md §5.3 / §6): rótulo em caps miúdo, valor
 * em **mono tabular** (leitura de instrumento), delta com os `--*-ink` semânticos
 * (nunca a cor viva do estágio). Voz §8: número com unidade e origem — passe a
 * unidade no `value`/`suffix`, não deixe número solto.
 *
 * `accent` reserva o realce âmbar para o cartão que "requer decisão" — um por tela.
 */
interface KpiCardProps {
  label: string
  icon?: React.ReactNode
  value: React.ReactNode
  /** Prefixo miúdo antes do valor (ex.: "R$"). */
  prefix?: string
  /** Sufixo miúdo depois do valor (ex.: "kg", "%"). */
  suffix?: string
  delta?: { value: string; dir: 'up' | 'down' }
  accent?: boolean
  /** Slot de sparkline no canto inferior direito. */
  spark?: React.ReactNode
}

export const KpiCard: React.FC<KpiCardProps> = ({ label, icon, value, prefix, suffix, delta, accent, spark }) => (
  <Card
    pad={false}
    style={{
      padding: '16px 18px',
      position: 'relative',
      overflow: 'hidden',
      ...(accent
        ? {
            background: 'linear-gradient(135deg, var(--accent-soft), var(--surface))',
            borderColor: 'color-mix(in srgb, var(--accent) 40%, var(--line))',
          }
        : null),
    }}
  >
    <div style={{ fontSize: 12, color: 'var(--ink-3)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7 }}>
      {icon && (
        <span style={{ display: 'grid', placeItems: 'center', width: 14, height: 14 }}>
          {React.cloneElement(icon as React.ReactElement<{ size?: number }>, { size: 14 })}
        </span>
      )}
      {label}
    </div>

    <div className="num" style={{ fontSize: 27, fontWeight: 750, letterSpacing: '-0.03em', marginTop: 8 }}>
      {prefix && <small style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-3)', marginRight: 1 }}>{prefix}</small>}
      {value}
      {suffix && <small style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-3)', marginLeft: 3 }}>{suffix}</small>}
    </div>

    {delta && (
      <div
        style={{
          fontSize: 11.5,
          marginTop: 5,
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          fontWeight: 600,
          color: delta.dir === 'up' ? 'var(--good-ink)' : 'var(--danger-ink)',
        }}
      >
        {delta.dir === 'up' ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
        {delta.value}
      </div>
    )}

    {spark && <div style={{ position: 'absolute', right: 0, bottom: 0, width: 96, height: 44, opacity: 0.9 }}>{spark}</div>}
  </Card>
)

export default KpiCard
