import { useEffect } from 'react'
import {
  buildRRule, parseRRule, weekdayCode, WEEKDAYS,
  type Freq, type RecurrenceEnd,
} from '../recurrence'
import { inputStyle, selectStyle, labelStyle } from '../formStyles'

interface Props {
  /** Regra RRULE atual (string vazia = não repete). */
  value: string
  onChange: (rule: string) => void
  /** Data de início do evento (`datetime-local`/`date`) — semeia o dia da semana. */
  anchorDate: string
}

const FREQ_LABEL: Record<Freq, string> = {
  none: 'Não repete',
  daily: 'Diariamente',
  weekly: 'Semanalmente',
  monthly: 'Mensalmente',
  yearly: 'Anualmente',
}

/**
 * Editor de recorrência (Fatia B): frequência, intervalo, dias da semana e
 * término (nunca / em data / após N). Mantém a regra como string RRULE; o
 * estado é derivado dela a cada render (fonte única = `value`).
 */
export function RecurrenceEditor({ value, onChange, anchorDate }: Props) {
  const state = parseRRule(value)

  // Ao virar "semanal" sem dias marcados, semeia com o dia do próprio evento.
  useEffect(() => {
    if (state.freq === 'weekly' && state.weekdays.length === 0 && anchorDate) {
      onChange(buildRRule({ ...state, weekdays: [weekdayCode(anchorDate)] }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.freq])

  const patch = (partial: Partial<typeof state>) => onChange(buildRRule({ ...state, ...partial }))

  const toggleWeekday = (code: string) => {
    const set = new Set(state.weekdays)
    if (set.has(code)) set.delete(code)
    else set.add(code)
    patch({ weekdays: WEEKDAYS.map(w => w.code).filter(c => set.has(c)) })
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <label style={labelStyle}>Repetição</label>
        <select
          style={selectStyle}
          value={state.freq}
          onChange={e => {
            const freq = e.target.value as Freq
            if (freq === 'none') onChange('')
            else patch({ freq })
          }}
        >
          {(Object.keys(FREQ_LABEL) as Freq[]).map(f => (
            <option key={f} value={f}>{FREQ_LABEL[f]}</option>
          ))}
        </select>
      </div>

      {state.freq !== 'none' && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelStyle}>A cada</label>
              <input
                type="number" min={1} max={99} style={inputStyle}
                value={state.interval}
                onChange={e => patch({ interval: Math.max(1, parseInt(e.target.value, 10) || 1) })}
              />
            </div>
            <div className="flex items-end pb-1.5 text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {state.freq === 'daily' && 'dia(s)'}
              {state.freq === 'weekly' && 'semana(s)'}
              {state.freq === 'monthly' && 'mês(es)'}
              {state.freq === 'yearly' && 'ano(s)'}
            </div>
          </div>

          {state.freq === 'weekly' && (
            <div>
              <label style={labelStyle}>Dias da semana</label>
              <div className="flex gap-1.5">
                {WEEKDAYS.map(w => {
                  const active = state.weekdays.includes(w.code)
                  return (
                    <button
                      key={w.code} type="button" onClick={() => toggleWeekday(w.code)}
                      title={w.code}
                      className="w-8 h-8 rounded-full text-xs font-semibold"
                      style={{
                        border: '1.5px solid ' + (active ? 'var(--color-brand)' : '#e2e8f0'),
                        background: active ? 'var(--color-brand)' : '#FFFFFF',
                        color: active ? '#FFFFFF' : 'var(--color-text-muted)',
                        cursor: 'pointer', fontFamily: 'var(--font-body)',
                      }}
                    >
                      {w.label}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <div>
            <label style={labelStyle}>Termina</label>
            <div className="grid grid-cols-2 gap-3">
              <select
                style={selectStyle}
                value={state.end}
                onChange={e => patch({ end: e.target.value as RecurrenceEnd })}
              >
                <option value="never">Nunca</option>
                <option value="until">Em uma data</option>
                <option value="count">Após N vezes</option>
              </select>
              {state.end === 'until' && (
                <input type="date" style={inputStyle} value={state.until}
                  onChange={e => patch({ until: e.target.value })} />
              )}
              {state.end === 'count' && (
                <input type="number" min={1} max={999} style={inputStyle} value={state.count}
                  onChange={e => patch({ count: Math.max(1, parseInt(e.target.value, 10) || 1) })} />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
