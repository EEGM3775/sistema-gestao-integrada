import type {
  TipoMov, StatusRequisicao, StatusTransferencia, StatusDevolucao, StatusInventario,
  StatusEPI, EstadoFerramenta, StatusEmprestimo,
} from './types'

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const QTY = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 })

export const num = (v: string | number | null | undefined): number | null => {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}
export const brl = (v: string | number | null | undefined) => { const n = num(v); return n == null ? '—' : BRL.format(n) }
export const qty = (v: string | number | null | undefined) => { const n = num(v); return n == null ? '—' : QTY.format(n) }
export const dataBR = (iso: string | null | undefined) => {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}/${m}/${y}` : '—'
}

export type Kind = 'slate' | 'info' | 'amber' | 'good' | 'danger' | 'net'
export interface Estado { label: string; kind: Kind; pulse?: boolean }

// Movimento → cor/sentido (o mesmo vocabulário de Pill do SCM).
export const movEstado: Record<TipoMov, Estado> = {
  entrada: { label: 'Entrada', kind: 'good' }, saida: { label: 'Saída', kind: 'danger' },
  ajuste: { label: 'Ajuste', kind: 'amber' }, transf_saida: { label: 'Transf. saída', kind: 'info' },
  transf_entrada: { label: 'Transf. entrada', kind: 'info' }, devolucao: { label: 'Devolução', kind: 'net' },
}
export const requisicaoEstado: Record<StatusRequisicao, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate' }, pendente: { label: 'Pendente', kind: 'amber', pulse: true },
  aprovada: { label: 'Aprovada', kind: 'info', pulse: true }, atendida: { label: 'Atendida', kind: 'good' },
  parcial: { label: 'Parcial', kind: 'amber' }, cancelada: { label: 'Cancelada', kind: 'danger' },
}
export const transferenciaEstado: Record<StatusTransferencia, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate', pulse: true }, executada: { label: 'Executada', kind: 'good' }, cancelada: { label: 'Cancelada', kind: 'danger' },
}
export const devolucaoEstado: Record<StatusDevolucao, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate', pulse: true }, executada: { label: 'Executada', kind: 'good' }, cancelada: { label: 'Cancelada', kind: 'danger' },
}
export const inventarioEstado: Record<StatusInventario, Estado> = {
  aberto: { label: 'Aberto', kind: 'amber', pulse: true }, fechado: { label: 'Fechado', kind: 'good' },
}
export const epiEstado: Record<StatusEPI, Estado> = {
  entregue: { label: 'Entregue', kind: 'good' }, devolvido: { label: 'Devolvido', kind: 'slate' },
  substituido: { label: 'Substituído', kind: 'info' }, danificado: { label: 'Danificado', kind: 'danger' },
}
export const ferramentaEstado: Record<EstadoFerramenta, Estado> = {
  disponivel: { label: 'Disponível', kind: 'good' }, emprestada: { label: 'Emprestada', kind: 'info', pulse: true },
  manutencao: { label: 'Manutenção', kind: 'amber' }, baixada: { label: 'Baixada', kind: 'slate' },
}
export const emprestimoEstado: Record<StatusEmprestimo, Estado> = {
  emprestada: { label: 'Emprestada', kind: 'info', pulse: true }, devolvida: { label: 'Devolvida', kind: 'good' },
}
// Classe da curva ABC → cor.
export const abcKind: Record<'A' | 'B' | 'C', Kind> = { A: 'danger', B: 'amber', C: 'good' }
