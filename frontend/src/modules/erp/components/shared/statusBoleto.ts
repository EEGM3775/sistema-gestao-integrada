import type { StatusBoleto } from '../../types'

/** Rótulos e cores de `StatusBoleto` — compartilhado entre `StatusBoletoBadge` e o `FilterBar` de Boletos (D.1.2). */

export const STATUS_BOLETO_CONFIG: Record<StatusBoleto, { label: string; bg: string; color: string }> = {
  AGUARDANDO: { label: 'Aguardando emissão', bg: '#f3f4f6', color: '#374151' },
  EMITIDO:    { label: 'Emitido',            bg: '#e0f2fe', color: '#0369a1' },
  PAGO:       { label: 'Pago',               bg: '#dcfce7', color: '#166534' },
  VENCIDO:    { label: 'Vencido',            bg: '#fef3c7', color: '#92400e' },
  CANCELADO:  { label: 'Cancelado',          bg: '#fee2e2', color: '#991b1b' },
  ERRO:       { label: 'Erro',               bg: '#fee2e2', color: '#991b1b' },
}

export const STATUS_BOLETO_OPTIONS = (Object.keys(STATUS_BOLETO_CONFIG) as StatusBoleto[]).map(value => ({
  value, label: STATUS_BOLETO_CONFIG[value].label,
}))
