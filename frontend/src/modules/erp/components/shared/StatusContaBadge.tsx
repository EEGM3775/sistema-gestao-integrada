import type { StatusConta } from '../../types'
import { STATUS_CONTA_CONFIG } from './statusConta'

/** Badge de status de ContaPagar/ContaReceber — mesmo `StatusConta` nos dois lados (D.1.1). */
export function StatusContaBadge({ status }: { status: StatusConta }) {
  const cfg = STATUS_CONTA_CONFIG[status] ?? { label: status, bg: '#f3f4f6', color: '#374151' }
  return (
    <span
      className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: cfg.bg, color: cfg.color, fontFamily: 'var(--font-body)' }}
    >
      {cfg.label}
    </span>
  )
}
