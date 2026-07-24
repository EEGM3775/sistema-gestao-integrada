import type { StatusDemanda, StatusCotacao, StatusProposta, StatusPedido, OrigemPedido } from './types'

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

export const demandaEstado: Record<StatusDemanda, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate' }, aberta: { label: 'Aberta', kind: 'info', pulse: true },
  em_cotacao: { label: 'Em cotação', kind: 'amber', pulse: true }, atendida: { label: 'Atendida', kind: 'good' }, cancelada: { label: 'Cancelada', kind: 'danger' },
}
export const cotacaoEstado: Record<StatusCotacao, Estado> = {
  aberta: { label: 'Aberta', kind: 'info', pulse: true }, encerrada: { label: 'Encerrada', kind: 'slate' }, adjudicada: { label: 'Adjudicada', kind: 'good' },
}
export const propostaEstado: Record<StatusProposta, Estado> = {
  recebida: { label: 'Recebida', kind: 'slate' }, vencedora: { label: 'Vencedora', kind: 'good' }, recusada: { label: 'Recusada', kind: 'danger' },
}
export const pedidoEstado: Record<StatusPedido, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate' }, aprovado: { label: 'Aprovado', kind: 'info' }, enviado: { label: 'Enviado', kind: 'info', pulse: true },
  recebido_parcial: { label: 'Recebido parcial', kind: 'amber', pulse: true }, recebido_total: { label: 'Recebido total', kind: 'good' }, cancelado: { label: 'Cancelado', kind: 'danger' },
}
export const origemPedido: Record<OrigemPedido, { label: string; kind: Kind }> = {
  compra_direta: { label: 'Direta', kind: 'net' }, cotacao: { label: 'Cotação', kind: 'amber' }, manual: { label: 'Manual', kind: 'slate' },
}
