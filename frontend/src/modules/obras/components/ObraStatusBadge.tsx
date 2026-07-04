import React from 'react'
import type { StatusObra } from '@/types'

const CONFIG: Record<StatusObra, { label: string; bg: string; color: string }> = {
  planejamento: { label: 'Planejamento', bg: '#e0f2fe', color: '#0369a1' },
  em_execucao:  { label: 'Em Execução',  bg: '#dcfce7', color: '#166534' },
  concluida:    { label: 'Concluída',    bg: '#f3f4f6', color: '#374151' },
  cancelada:    { label: 'Cancelada',    bg: '#fee2e2', color: '#991b1b' },
}

export const ObraStatusBadge: React.FC<{ status: StatusObra }> = ({ status }) => {
  const cfg = CONFIG[status] ?? { label: status, bg: '#f3f4f6', color: '#374151' }
  return (
    <span
      className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: cfg.bg, color: cfg.color, fontFamily: 'var(--font-body)' }}
    >
      {cfg.label}
    </span>
  )
}

export default ObraStatusBadge
