import { calendarClient, CALENDAR_BASE } from '../calendarClient'
import type { Agenda, AgendaPayload, CalendarEvent, RsvpStatus } from '../../types'

/** Agendas que a pessoa vê (Fatia D): as dela, as de equipe em que está e as da empresa. */
export async function fetchAgendas(): Promise<Agenda[]> {
  const { data } = await calendarClient.get<Agenda[]>(`${CALENDAR_BASE}calendars/`)
  return data
}

export async function createAgenda(payload: AgendaPayload): Promise<Agenda> {
  const { data } = await calendarClient.post<Agenda>(`${CALENDAR_BASE}calendars/`, payload)
  return data
}

export async function updateAgenda(id: number, payload: Partial<AgendaPayload>): Promise<Agenda> {
  const { data } = await calendarClient.patch<Agenda>(`${CALENDAR_BASE}calendars/${id}/`, payload)
  return data
}

export async function deleteAgenda(id: number): Promise<void> {
  await calendarClient.delete(`${CALENDAR_BASE}calendars/${id}/`)
}

/** O convidado responde (vale para a série inteira, se for recorrente). */
export async function responderConvite(eventId: number, status: Exclude<RsvpStatus, 'pendente'>): Promise<CalendarEvent> {
  const { data } = await calendarClient.post<CalendarEvent>(`${CALENDAR_BASE}events/${eventId}/responder/`, { status })
  return data
}

/** Recorte do `.ics`: uma agenda (`id`), a pessoal implícita (`'meus'`) ou tudo (`''`). */
export type RecorteIcs = number | 'meus' | ''

/** Baixa a agenda em `.ics` (Fatia E). Pelo axios, para levar a sessão. */
export async function exportarIcs(recorte: RecorteIcs, nome: string): Promise<void> {
  const { data } = await calendarClient.get<Blob>(`${CALENDAR_BASE}events/exportar-ics/`, {
    params: recorte === '' ? {} : { calendar: recorte },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = `${nome || 'agenda'}.ics`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Importa um `.ics` na agenda escolhida. Tudo ou nada: o 400 traz `erros`. */
export async function importarIcs(arquivo: File, recorte: RecorteIcs): Promise<{ criados: number }> {
  const corpo = new FormData()
  corpo.append('arquivo', arquivo)
  if (recorte !== '') corpo.append('calendar', String(recorte))
  const { data } = await calendarClient.post<{ criados: number }>(`${CALENDAR_BASE}events/importar-ics/`, corpo)
  return data
}
