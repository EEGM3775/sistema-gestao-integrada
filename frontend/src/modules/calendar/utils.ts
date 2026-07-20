import type { EventSource, EventType, HolidayScope } from './types'

/** Paleta por origem do evento (fundo/borda/texto), no espírito do design navy. */
export const SOURCE_STYLE: Record<EventSource, { bg: string; border: string; text: string; label: string }> = {
  local:       { bg: '#1e40af', border: '#1e3a8a', text: '#FFFFFF', label: 'Meus eventos' },
  reuniao:     { bg: '#7c3aed', border: '#6d28d9', text: '#FFFFFF', label: 'Reuniões (CRM)' },
  tarefa:      { bg: '#d97706', border: '#b45309', text: '#FFFFFF', label: 'Tarefas (CRM)' },
  diario_obra: { bg: '#0891b2', border: '#0e7490', text: '#FFFFFF', label: 'Diário de obra' },
  holiday:     { bg: '#e11d48', border: '#be123c', text: '#FFFFFF', label: 'Feriados' },
}

/** Cor por escopo de feriado (Fatia F): nacional/estadual/municipal — cada um
 * distinto das cores de origem acima. O rótulo da localidade vai no título. */
export const HOLIDAY_SCOPE_STYLE: Record<HolidayScope, { bg: string; border: string; text: string; label: string }> = {
  nacional:  { bg: '#dc2626', border: '#b91c1c', text: '#FFFFFF', label: 'Feriado nacional (Brasil)' },
  estadual:  { bg: '#16a34a', border: '#15803d', text: '#FFFFFF', label: 'Feriado estadual (UF)' },
  municipal: { bg: '#d946ef', border: '#c026d3', text: '#FFFFFF', label: 'Feriado municipal (cidade)' },
}

/** Unidades federativas do Brasil (para o seletor de estado). */
export const UFS: { uf: string; nome: string }[] = [
  { uf: 'AC', nome: 'Acre' }, { uf: 'AL', nome: 'Alagoas' }, { uf: 'AP', nome: 'Amapá' },
  { uf: 'AM', nome: 'Amazonas' }, { uf: 'BA', nome: 'Bahia' }, { uf: 'CE', nome: 'Ceará' },
  { uf: 'DF', nome: 'Distrito Federal' }, { uf: 'ES', nome: 'Espírito Santo' }, { uf: 'GO', nome: 'Goiás' },
  { uf: 'MA', nome: 'Maranhão' }, { uf: 'MT', nome: 'Mato Grosso' }, { uf: 'MS', nome: 'Mato Grosso do Sul' },
  { uf: 'MG', nome: 'Minas Gerais' }, { uf: 'PA', nome: 'Pará' }, { uf: 'PB', nome: 'Paraíba' },
  { uf: 'PR', nome: 'Paraná' }, { uf: 'PE', nome: 'Pernambuco' }, { uf: 'PI', nome: 'Piauí' },
  { uf: 'RJ', nome: 'Rio de Janeiro' }, { uf: 'RN', nome: 'Rio Grande do Norte' }, { uf: 'RS', nome: 'Rio Grande do Sul' },
  { uf: 'RO', nome: 'Rondônia' }, { uf: 'RR', nome: 'Roraima' }, { uf: 'SC', nome: 'Santa Catarina' },
  { uf: 'SP', nome: 'São Paulo' }, { uf: 'SE', nome: 'Sergipe' }, { uf: 'TO', nome: 'Tocantins' },
]

/** Rótulos dos tipos de evento próprio. */
export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  tarefa: 'Tarefa',
  reuniao: 'Reunião',
  lembrete: 'Lembrete',
}

/** ISO (com offset) → valor de `<input type="datetime-local">` (hora local, sem tz). */
export function isoToLocalInput(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** ISO → valor de `<input type="date">` (YYYY-MM-DD, dia local). */
export function isoToDateInput(iso: string): string {
  return isoToLocalInput(iso).slice(0, 10)
}

/** Valor de `datetime-local` (hora local) → ISO com offset, para o backend. */
export function localInputToIso(value: string): string {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toISOString()
}

/** Valor de `date` (YYYY-MM-DD) → ISO à meia-noite local. */
export function dateInputToIso(value: string): string {
  return localInputToIso(`${value}T00:00`)
}
