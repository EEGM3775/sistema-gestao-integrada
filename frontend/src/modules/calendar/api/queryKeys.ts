import type { CalendarRange } from '../types'

/** Fábrica de chaves do TanStack Query para o módulo Calendário. */
export const calendarKeys = {
  all: ['calendar'] as const,
  events: {
    all: ['calendar', 'events'] as const,
    feed: (range: CalendarRange) => ['calendar', 'events', 'feed', range] as const,
    detail: (id: number | string) => ['calendar', 'events', 'detail', String(id)] as const,
  },
  /** Agendas (Fatia D). */
  agendas: ['calendar', 'agendas'] as const,
}
