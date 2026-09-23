import type { ClasseABC, Fonte, ItemOrcado, StatusOrcamento } from './types'

export type Kind = 'slate' | 'info' | 'amber' | 'good' | 'danger' | 'net'
export interface Estado { label: string; kind: Kind; pulse?: boolean }

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const BRL_CURTO = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 2 })
const NUM4 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
const NUM2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function brl(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? BRL.format(n) : '—'
}

export function brlCurto(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  return `R$ ${BRL_CURTO.format(n)}`
}

export function num(v: string | number | null | undefined, casas: 2 | 4 = 4): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  return (casas === 4 ? NUM4 : NUM2).format(n)
}

export function pct(v: string | number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? `${n.toFixed(casas).replace('.', ',')}%` : '—'
}

/** Digitação pt-BR ("1.240,55") → decimal do DRF ("1240.55"). */
export function paraDecimal(entrada: string): string {
  const limpo = entrada.trim().replace(/\s/g, '').replace(/\./g, '').replace(',', '.')
  const n = Number(limpo)
  return Number.isFinite(n) ? String(n) : '0'
}

/** Decimal do DRF → texto editável em pt-BR, sem zeros de enfeite. */
export function paraEdicao(valor: string | null | undefined): string {
  if (valor === null || valor === undefined || valor === '') return ''
  const n = Number(valor)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 6 })
}

export function mesBR(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [ano, mes] = iso.split('-')
  const nomes = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
  const i = Number(mes) - 1
  return nomes[i] ? `${nomes[i]}/${ano}` : iso
}

export function dataBR(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('pt-BR')
}

export const FONTE_ROTULO: Record<Fonte, string> = {
  sinapi: 'SINAPI', orse: 'ORSE', sicro: 'SICRO', seinfra: 'SEINFRA',
  sedop: 'SEDOP', tcpo: 'TCPO', embasa: 'EMBASA', propria: 'PRÓPRIA',
}

export const STATUS_ESTADO: Record<StatusOrcamento, Estado> = {
  rascunho: { label: 'Rascunho', kind: 'amber', pulse: true },
  aprovado: { label: 'Aprovado', kind: 'good' },
  superado: { label: 'Superado', kind: 'slate' },
  cancelado: { label: 'Cancelado', kind: 'danger' },
}

export const CLASSE_KIND: Record<ClasseABC, Kind> = { A: 'danger', B: 'amber', C: 'slate' }

/** Nó da árvore EAP montado a partir da lista plana que o `arvore/` devolve. */
export interface NoEap {
  item: ItemOrcado
  filhos: NoEap[]
  nivel: number
}

export function montarArvore(itens: ItemOrcado[]): NoEap[] {
  const porPai = new Map<number | null, ItemOrcado[]>()
  for (const item of itens) {
    const chave = item.pai
    const lista = porPai.get(chave)
    if (lista) lista.push(item)
    else porPai.set(chave, [item])
  }
  for (const lista of porPai.values()) {
    lista.sort((a, b) => a.ordem - b.ordem || a.item_orcado_id - b.item_orcado_id)
  }
  const construir = (pai: number | null, nivel: number): NoEap[] =>
    (porPai.get(pai) ?? []).map(item => ({ item, filhos: construir(item.item_orcado_id, nivel + 1), nivel }))
  return construir(null, 0)
}

/** Achata a árvore respeitando quais sintéticos estão recolhidos. */
export function achatar(nos: NoEap[], recolhidos: ReadonlySet<number>): NoEap[] {
  const saida: NoEap[] = []
  const visitar = (lista: NoEap[]) => {
    for (const no of lista) {
      saida.push(no)
      if (no.filhos.length && !recolhidos.has(no.item.item_orcado_id)) visitar(no.filhos)
    }
  }
  visitar(nos)
  return saida
}

export function peso(valor: string, total: string): number {
  const t = Number(total)
  if (!Number.isFinite(t) || t === 0) return 0
  return (Number(valor) / t) * 100
}
