import type { StatusConta } from '../../types'

/** Rótulos e cores de `StatusConta` — compartilhado entre `StatusContaBadge` e os `FilterBar` de Contas a Pagar/Receber (D.1.1). */

export const STATUS_CONTA_CONFIG: Record<StatusConta, { label: string; bg: string; color: string }> = {
  ABERTO:    { label: 'Aberto',    bg: '#e0f2fe', color: '#0369a1' },
  PARCIAL:   { label: 'Parcial',   bg: '#fef3c7', color: '#92400e' },
  QUITADO:   { label: 'Quitado',   bg: '#dcfce7', color: '#166534' },
  CANCELADO: { label: 'Cancelado', bg: '#fee2e2', color: '#991b1b' },
}

export const STATUS_CONTA_OPTIONS = (Object.keys(STATUS_CONTA_CONFIG) as StatusConta[]).map(value => ({
  value, label: STATUS_CONTA_CONFIG[value].label,
}))
