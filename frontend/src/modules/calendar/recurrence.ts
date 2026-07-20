/**
 * Conversão entre o estado do editor de repetição e a string RRULE (RFC 5545)
 * que o backend expande (Fatia B). A regra é gravada SEM `DTSTART` — a âncora é
 * sempre o `start_time` do evento. `UNTIL` sai em UTC (`…Z`), exigido pelo
 * dateutil quando o DTSTART é tz-aware.
 */

export type Freq = 'none' | 'daily' | 'weekly' | 'monthly' | 'yearly'
export type RecurrenceEnd = 'never' | 'until' | 'count'

export interface RecurrenceState {
  freq: Freq
  interval: number
  /** dias da semana (só para `weekly`): 'MO','TU',… */
  weekdays: string[]
  end: RecurrenceEnd
  until: string // 'YYYY-MM-DD'
  count: number
}

export const WEEKDAYS: { code: string; label: string }[] = [
  { code: 'MO', label: 'S' }, { code: 'TU', label: 'T' }, { code: 'WE', label: 'Q' },
  { code: 'TH', label: 'Q' }, { code: 'FR', label: 'S' }, { code: 'SA', label: 'S' },
  { code: 'SU', label: 'D' },
]

const FREQ_TO_RRULE: Record<Exclude<Freq, 'none'>, string> = {
  daily: 'DAILY', weekly: 'WEEKLY', monthly: 'MONTHLY', yearly: 'YEARLY',
}
const RRULE_TO_FREQ: Record<string, Freq> = {
  DAILY: 'daily', WEEKLY: 'weekly', MONTHLY: 'monthly', YEARLY: 'yearly',
}

export const emptyRecurrence = (): RecurrenceState => ({
  freq: 'none', interval: 1, weekdays: [], end: 'never', until: '', count: 10,
})

/** Código do dia da semana ('MO'…'SU') de uma data ISO/`datetime-local`. */
export function weekdayCode(dateStr: string): string {
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return 'MO'
  // getDay(): 0=domingo … 6=sábado
  return ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'][d.getDay()]
}

/** Estado do editor → string RRULE (vazia quando não repete). */
export function buildRRule(state: RecurrenceState): string {
  if (state.freq === 'none') return ''
  const parts = [`FREQ=${FREQ_TO_RRULE[state.freq]}`]
  if (state.interval > 1) parts.push(`INTERVAL=${state.interval}`)
  if (state.freq === 'weekly' && state.weekdays.length > 0) {
    parts.push(`BYDAY=${state.weekdays.join(',')}`)
  }
  if (state.end === 'until' && state.until) {
    parts.push(`UNTIL=${state.until.replace(/-/g, '')}T235959Z`)
  } else if (state.end === 'count' && state.count > 0) {
    parts.push(`COUNT=${state.count}`)
  }
  return parts.join(';')
}

/** String RRULE → estado do editor (tolerante a prefixo `RRULE:`). */
export function parseRRule(rule: string | null | undefined): RecurrenceState {
  const state = emptyRecurrence()
  if (!rule) return state
  const parts: Record<string, string> = {}
  rule.replace(/^RRULE:/i, '').split(';').forEach(token => {
    const [k, v] = token.split('=')
    if (k && v) parts[k.toUpperCase()] = v
  })
  const freq = RRULE_TO_FREQ[parts.FREQ]
  if (!freq) return state
  state.freq = freq
  state.interval = parts.INTERVAL ? parseInt(parts.INTERVAL, 10) : 1
  state.weekdays = parts.BYDAY ? parts.BYDAY.split(',') : []
  if (parts.UNTIL) {
    state.end = 'until'
    const m = parts.UNTIL.match(/^(\d{4})(\d{2})(\d{2})/)
    if (m) state.until = `${m[1]}-${m[2]}-${m[3]}`
  } else if (parts.COUNT) {
    state.end = 'count'
    state.count = parseInt(parts.COUNT, 10)
  }
  return state
}

/** Resumo legível da regra, para exibir na lista/tooltip. */
export function describeRRule(rule: string | null | undefined): string {
  const s = parseRRule(rule)
  if (s.freq === 'none') return 'Não repete'
  const base: Record<Exclude<Freq, 'none'>, string> = {
    daily: s.interval > 1 ? `A cada ${s.interval} dias` : 'Diariamente',
    weekly: s.interval > 1 ? `A cada ${s.interval} semanas` : 'Semanalmente',
    monthly: s.interval > 1 ? `A cada ${s.interval} meses` : 'Mensalmente',
    yearly: s.interval > 1 ? `A cada ${s.interval} anos` : 'Anualmente',
  }
  let txt = base[s.freq]
  if (s.end === 'count') txt += `, ${s.count}×`
  else if (s.end === 'until' && s.until) txt += `, até ${s.until.split('-').reverse().join('/')}`
  return txt
}
