import type { StatusBoleto } from '../../types'
import { STATUS_BOLETO_CONFIG } from './statusBoleto'

/** Badge de status de Boleto — espelha `StatusBoletoBadge`/`StatusContaBadge` (D.1.2/D.1.1). */
export function StatusBoletoBadge({ status }: { status: StatusBoleto }) {
  const cfg = STATUS_BOLETO_CONFIG[status] ?? { label: status, bg: '#f3f4f6', color: '#374151' }
  return (
    <span
      className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: cfg.bg, color: cfg.color, fontFamily: 'var(--font-body)' }}
    >
      {cfg.label}
    </span>
  )
}
