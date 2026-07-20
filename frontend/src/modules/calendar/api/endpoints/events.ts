import { calendarClient, CALENDAR_BASE } from '../calendarClient'
import type {
  CalendarEvent,
  CalendarEventPayload,
  CalendarFeedEvent,
  CalendarRange,
  RecurrenceScope,
} from '../../types'

/**
 * Feed agregado do período — eventos próprios + diário de obra + feriados +
 * tarefas/reuniões do CRM, já no formato FullCalendar. Somente os de
 * `extendedProps.type === 'local'` são editáveis (têm `id` numérico próprio).
 */
export async function fetchEvents(range: CalendarRange): Promise<CalendarFeedEvent[]> {
  const { data } = await calendarClient.get<CalendarFeedEvent[]>(`${CALENDAR_BASE}events/`, {
    params: {
      start: range.start, end: range.end,
      ...(range.uf ? { uf: range.uf } : {}),
      ...(range.ibge ? { ibge: range.ibge } : {}),
    },
  })
  return data
}

/** Registro completo de um evento próprio (para editar). */
export async function fetchEvent(id: number | string): Promise<CalendarEvent> {
  const { data } = await calendarClient.get<CalendarEvent>(`${CALENDAR_BASE}events/${id}/`)
  return data
}

export async function createEvent(payload: CalendarEventPayload): Promise<CalendarEvent> {
  const { data } = await calendarClient.post<CalendarEvent>(`${CALENDAR_BASE}events/`, payload)
  return data
}

export async function updateEvent(
  id: number | string,
  payload: Partial<CalendarEventPayload>,
): Promise<CalendarEvent> {
  const { data } = await calendarClient.patch<CalendarEvent>(`${CALENDAR_BASE}events/${id}/`, payload)
  return data
}

export async function deleteEvent(id: number | string): Promise<void> {
  await calendarClient.delete(`${CALENDAR_BASE}events/${id}/`)
}

/**
 * Edita uma série recorrente (Fatia B). `scope`: `this` cria um override só
 * desta ocorrência; `all` altera a série toda; `future` divide a série a partir
 * desta ocorrência. `masterId` é o evento-mestre; `occurrenceStart` (ISO) a
 * ocorrência clicada.
 */
export async function updateOccurrence(
  masterId: number,
  scope: RecurrenceScope,
  occurrenceStart: string,
  payload: Partial<CalendarEventPayload>,
): Promise<void> {
  await calendarClient.post(`${CALENDAR_BASE}events/${masterId}/update-recurrence/`, {
    scope, occurrence_start: occurrenceStart, payload,
  })
}

/** Exclui de uma série recorrente (`this` / `all` / `future`). */
export async function deleteOccurrence(
  masterId: number,
  scope: RecurrenceScope,
  occurrenceStart: string,
): Promise<void> {
  await calendarClient.post(`${CALENDAR_BASE}events/${masterId}/delete-recurrence/`, {
    scope, occurrence_start: occurrenceStart,
  })
}
