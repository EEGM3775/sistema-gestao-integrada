// Formatadores (instrumento — §6) e mapas de estado (§5.2/§8: estado nomeado e
// medido, cor semântica nunca reutiliza cor de estágio) do SCM.
import type { PillKind } from '@/components/malha'
import type {
  StatusDemanda, StatusCotacao, StatusProposta, StatusPedido,
  Visibilidade, OrigemPedido, TipoItem, TipoCentroCusto, OrigemDemanda,
} from './types'

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const QTY = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 })

/** Valor monetário (decimal string do DRF) → "R$ 1.234,50"; nulo → travessão. */
export function brl(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? BRL.format(n) : '—'
}

/** Quantidade (decimal string) → "1.234,5"; nulo → travessão. */
export function qty(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? QTY.format(n) : '—'
}

/** "YYYY-MM-DD" → "DD/MM/AAAA" (sem fuso). */
export function dataBR(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}/${m}/${y}` : '—'
}

/** ISO datetime → "DD/MM/AAAA". */
export function dataHoraBR(iso: string | null | undefined): string {
  if (!iso) return '—'
  return dataBR(iso.slice(0, 10))
}

export interface Estado { label: string; kind: PillKind; pulse?: boolean }

export const demandaEstado: Record<StatusDemanda, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate' },
  aberta: { label: 'Aberta', kind: 'info', pulse: true },
  em_cotacao: { label: 'Em cotação', kind: 'amber', pulse: true },
  atendida: { label: 'Atendida', kind: 'good' },
  cancelada: { label: 'Cancelada', kind: 'danger' },
}

export const cotacaoEstado: Record<StatusCotacao, Estado> = {
  aberta: { label: 'Aberta', kind: 'info', pulse: true },
  encerrada: { label: 'Encerrada', kind: 'slate' },
  adjudicada: { label: 'Adjudicada', kind: 'good' },
}

export const propostaEstado: Record<StatusProposta, Estado> = {
  recebida: { label: 'Recebida', kind: 'slate' },
  vencedora: { label: 'Vencedora', kind: 'good' },
  recusada: { label: 'Recusada', kind: 'danger' },
}

export const pedidoEstado: Record<StatusPedido, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'slate' },
  aprovado: { label: 'Aprovado', kind: 'info' },
  enviado: { label: 'Enviado', kind: 'info', pulse: true },
  recebido_parcial: { label: 'Recebido parcial', kind: 'amber', pulse: true },
  recebido_total: { label: 'Recebido total', kind: 'good' },
  cancelado: { label: 'Cancelado', kind: 'danger' },
}

export const visibilidadeEstado: Record<Visibilidade, Estado> = {
  privada: { label: 'Privada', kind: 'slate' },
  rede: { label: 'Rede', kind: 'net' },
}

export const origemPedidoLabel: Record<OrigemPedido, string> = {
  compra_direta: 'Compra direta',
  cotacao: 'Cotação',
  manual: 'Manual',
}

export const origemDemandaLabel: Record<OrigemDemanda, string> = {
  manual: 'Manual',
  estoque: 'Falta no estoque',
}

export const tipoItemLabel: Record<TipoItem, string> = {
  material: 'Material',
  servico: 'Serviço',
}

export const tipoCentroCustoLabel: Record<TipoCentroCusto, string> = {
  obra: 'Obra',
  empreendimento: 'Empreendimento',
  almoxarifado: 'Almoxarifado / Central',
  filial: 'Filial',
  administrativo: 'Administrativo',
  outro: 'Outro',
}
