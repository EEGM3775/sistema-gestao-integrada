/* Constantes de estilo e utilidades do Suprimentos — fora do `ui.tsx` para o
 * fast refresh, que só recarrega arquivo que exporta apenas componentes. */
import type { CSSProperties } from 'react'
import type { Kind } from '../lib'

export const mono: CSSProperties = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }
export const KIND: Record<Kind, [string, string]> = {
  slate: ['var(--inset)', 'var(--ink-2)'], info: ['var(--info-soft)', 'var(--info-ink)'], amber: ['var(--accent-soft)', 'var(--accent-ink)'],
  good: ['var(--good-soft)', 'var(--good-ink)'], danger: ['var(--danger-soft)', 'var(--danger-ink)'], net: ['var(--net-soft)', 'var(--net-ink)'],
}
export const CAPS: CSSProperties = { fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }
export const inp: CSSProperties = { width: '100%', padding: '8px 11px', fontSize: 13.5, color: 'var(--ink)', background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', outline: 'none', fontFamily: 'var(--sans)' }

/** Toast da página. `ms` alonga o que precisa ser lido (o código do item novo). */
export type Say = (m: string, ms?: number) => void

/** Número como a obra digita: "18,50", "1.234,5", "1 " — `Number()` puro lê
 *  "18,50" como NaN. Vírgula presente = decimal BR. */
export const lerDecimal = (v: string): number | null => {
  const t = (v ?? '').trim().replace(/\s/g, '')
  if (!t) return null
  const n = Number(t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t)
  return Number.isFinite(n) ? n : null
}
