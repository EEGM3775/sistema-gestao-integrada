import type { StatusNFE } from '../../types'
import { STATUS_NFE_CONFIG } from './statusNfe'

/** Badge de status de NFS-e — espelha `StatusBoletoBadge`/`StatusContaBadge` (D.1.3). */
export function StatusNfeBadge({ status }: { status: StatusNFE }) {
  const cfg = STATUS_NFE_CONFIG[status] ?? { label: status, bg: '#f3f4f6', color: '#374151' }
  return (
    <span
      className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: cfg.bg, color: cfg.color, fontFamily: 'var(--font-body)' }}
    >
      {cfg.label}
    </span>
  )
}
