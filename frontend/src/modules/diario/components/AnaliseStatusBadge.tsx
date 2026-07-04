import React from 'react'
import { Brain, Loader2, CheckCircle2, AlertTriangle, CircleDashed } from 'lucide-react'

interface Config {
  label: string
  bg: string
  color: string
  icon: React.ReactNode
}

// Aceita tanto o vocabulário normalizado do frontend quanto o cru do modelo.
const CONFIG: Record<string, Config> = {
  sem_analise:     { label: 'Sem análise', bg: '#f3f4f6', color: '#6b7280', icon: <CircleDashed size={12} /> },
  pendente:        { label: 'Pendente',    bg: '#fef9c3', color: '#854d0e', icon: <Brain size={12} /> },
  em_andamento:    { label: 'Processando', bg: '#e0f2fe', color: '#0369a1', icon: <Loader2 size={12} className="animate-spin" /> },
  em_processamento:{ label: 'Processando', bg: '#e0f2fe', color: '#0369a1', icon: <Loader2 size={12} className="animate-spin" /> },
  completa:        { label: 'Concluída',   bg: '#dcfce7', color: '#166534', icon: <CheckCircle2 size={12} /> },
  concluido:       { label: 'Concluída',   bg: '#dcfce7', color: '#166534', icon: <CheckCircle2 size={12} /> },
  erro:            { label: 'Erro',        bg: '#fee2e2', color: '#991b1b', icon: <AlertTriangle size={12} /> },
}

export const AnaliseStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const cfg = CONFIG[status] ?? CONFIG.sem_analise
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: cfg.bg, color: cfg.color, fontFamily: 'var(--font-body)' }}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  )
}

export default AnaliseStatusBadge
