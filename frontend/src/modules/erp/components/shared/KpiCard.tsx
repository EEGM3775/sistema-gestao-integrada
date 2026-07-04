import type { ReactNode } from 'react'

interface KpiCardProps {
  label: string
  value: string
  icon?: ReactNode
  accentBg?: string
  accentColor?: string
  sub?: string
}

/** Card de KPI do hub financeiro (docs/modulos/moduloerp.md §5.5 — arquétipo "Dashboard"). */
export function KpiCard({ label, value, icon, accentBg = '#dcfce7', accentColor = 'var(--color-brand)', sub }: KpiCardProps) {
  return (
    <div className="rounded-xl p-4 flex flex-col gap-3" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <div className="flex items-center gap-3">
        {icon && (
          <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: accentBg, color: accentColor }}>
            {icon}
          </div>
        )}
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-body)' }}>
          {label}
        </span>
      </div>
      <div>
        <span className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>{value}</span>
        {sub && <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>{sub}</p>}
      </div>
    </div>
  )
}
