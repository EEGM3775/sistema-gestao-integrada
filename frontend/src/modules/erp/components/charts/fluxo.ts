/* Dados e período do fluxo de caixa do hub — fora dos componentes para o fast
 * refresh, que só recarrega arquivo que exporta apenas componentes. */
import { apiDecimalToCents } from '@/utils/money'
import type { FluxoCaixaMes, PeriodoFluxo } from '../../types'

export type ModoFluxo = 'barras' | 'linha'
export type AtalhoPeriodo = '3m' | '6m' | '12m' | 'ano' | 'personalizado'

/** Cores em hex — atributo SVG `fill`/`stroke` não resolve `var(--...)` de forma confiável. */
export const COR_FLUXO = { receitas: '#16a34a', despesas: '#dc2626', resultado: '#0A2A5B' } as const

export interface PontoFluxo {
  mes: string
  /** Centavos — a soma do período sai daqui sem erro de ponto flutuante. */
  receitas: number
  despesas: number
  resultado: number
}

/** `AAAA-MM` somado de `n` meses. */
export function somarMeses(mes: string, n: number): string {
  const [a, m] = mes.split('-').map(Number)
  const total = a * 12 + (m - 1) + n
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, '0')}`
}

/** Mês corrente no fuso do navegador, `AAAA-MM`. */
export function mesCorrente(): string {
  const hoje = new Date()
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}`
}

/** Período de um atalho, terminando no mês corrente. */
export function periodoDoAtalho(atalho: Exclude<AtalhoPeriodo, 'personalizado'>): PeriodoFluxo {
  const fim = mesCorrente()
  if (atalho === 'ano') return { inicio: `${fim.slice(0, 4)}-01`, fim }
  const meses = { '3m': 3, '6m': 6, '12m': 12 }[atalho]
  return { inicio: somarMeses(fim, -(meses - 1)), fim }
}

/**
 * A série do período inteiro: o backend só devolve meses com movimento, e um
 * mês sem nada é zero — não um buraco que a linha atravessa.
 */
export function serieDoPeriodo(data: FluxoCaixaMes[], periodo: PeriodoFluxo): PontoFluxo[] {
  const porMes = new Map(data.map(m => [m.mes.slice(0, 7), m]))
  const pontos: PontoFluxo[] = []
  for (let mes = periodo.inicio; mes <= periodo.fim; mes = somarMeses(mes, 1)) {
    const m = porMes.get(mes)
    const receitas = m ? apiDecimalToCents(m.receitas) : 0
    const despesas = m ? apiDecimalToCents(m.despesas) : 0
    pontos.push({ mes, receitas, despesas, resultado: receitas - despesas })
  }
  return pontos
}
