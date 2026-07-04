import React from 'react'
import type { StatusEmpreendimento } from '@/types'

const CONFIG: Record<StatusEmpreendimento, { label: string; bg: string; color: string }> = {
  planejamento: { label: 'Planejamento', bg: '#e0f2fe', color: '#0369a1' },
  em_execucao:  { label: 'Em Execução',  bg: '#dcfce7', color: '#166534' },
  concluido:    { label: 'Concluído',    bg: '#f3f4f6', color: '#374151' },
  cancelado:    { label: 'Cancelado',    bg: '#fee2e2', color: '#991b1b' },
}

export const EmpreendimentoStatusBadge: React.FC<{ status: StatusEmpreendimento }> = ({ status }) => {
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

export default EmpreendimentoStatusBadge
