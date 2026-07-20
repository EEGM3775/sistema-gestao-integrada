import apiClient from '@/api/apiClient'

/** Reexporta o `apiClient` autenticado — o calendário cai sob `/calendar/`. */
export const calendarClient = apiClient
export const CALENDAR_BASE = 'calendar/'
