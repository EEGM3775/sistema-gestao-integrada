/** Tipos do módulo Calendário. */

/** Origem de um evento no feed agregado do backend (`extendedProps.type`). */
export type EventSource = 'local' | 'diario_obra' | 'holiday' | 'tarefa' | 'reuniao'

/** Tipo de um evento próprio (CalendarEvent.event_type). */
export type EventType = 'tarefa' | 'reuniao' | 'lembrete'

/**
 * Evento no formato que o backend emite para o FullCalendar. O feed mistura
 * eventos próprios (editáveis, `source === 'local'`, `id` numérico) com leituras
 * agregadas de diário/feriado/CRM (somente leitura).
 */
export interface CalendarFeedEvent {
  id?: number | string
  title: string
  start: string
  end?: string
  allDay: boolean
  extendedProps: {
    type: EventSource
    [key: string]: unknown
  }
}

/** Registro completo de um evento próprio (retrieve/CRUD de CalendarEvent). */
export interface CalendarEvent {
  id: number
  title: string
  description: string | null
  start_time: string
  end_time: string
  all_day: boolean
  event_type: EventType
  user: number
  tenant: number
  /** Regra RRULE (Fatia B); vazio = evento único. */
  recurrence_rule: string
  /** Lembretes (Fatia C): offsets em minutos antes do início (0 = na hora). */
  reminders: number[]
}

/** Payload de criação/edição de um evento próprio. */
export interface CalendarEventPayload {
  title: string
  description?: string | null
  start_time: string
  end_time: string
  all_day: boolean
  event_type: EventType
  /** Regra RRULE (Fatia B); string vazia torna o evento único. */
  recurrence_rule?: string
  /** Lembretes (Fatia C): offsets em minutos antes do início. Ausente = não altera. */
  reminders?: number[]
}

/** Alcance de uma edição/exclusão numa série recorrente. */
export type RecurrenceScope = 'this' | 'all' | 'future'

/**
 * Referência a uma ocorrência recorrente clicada no feed (vem em
 * `extendedProps` das ocorrências virtuais que o backend expande).
 */
export interface OccurrenceRef {
  masterId: number
  occurrenceStart: string
  recurrenceRule: string
}

/** Janela consultada ao backend (query params `start`/`end`, ISO) + localidade
 * (Fatia F): `uf`/`ibge` filtram os feriados estaduais/municipais. */
export interface CalendarRange {
  start: string
  end: string
  uf?: string
  ibge?: string
}

/** Escopo de um feriado (Fatia F) — determina cor e rótulo de localidade. */
export type HolidayScope = 'nacional' | 'estadual' | 'municipal'

/** Obra com a localidade resolvida do endereço (seletor do calendário). */
export interface ObraLocalidade {
  obra_id: number
  nome: string
  uf: string
  ibge: string
  cidade: string
}

/** Município de uma UF (seletor). */
export interface Municipio {
  ibge: string
  nome: string
}

/** Localidade selecionada no topo do calendário. */
export interface LocalidadeSelecionada {
  uf: string
  ibge: string
}

/** Carimbo da última sincronização de feriados (visível ao superuser). */
export interface FeriadosStatus {
  atualizado_em: string | null
  total: number
  anos: string
  detalhes: Record<string, number>
}
