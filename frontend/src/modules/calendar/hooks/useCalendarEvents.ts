import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { calendarKeys } from '../api/queryKeys'
import {
  fetchEvents,
  fetchEvent,
  createEvent,
  updateEvent,
  deleteEvent,
  updateOccurrence,
  deleteOccurrence,
} from '../api/endpoints/events'
import type { CalendarEventPayload, CalendarRange, RecurrenceScope } from '../types'

export function useCalendarEvents(range: CalendarRange | null) {
  return useQuery({
    queryKey: calendarKeys.events.feed(range ?? { start: '', end: '' }),
    queryFn: () => fetchEvents(range as CalendarRange),
    enabled: range != null,
    placeholderData: keepPreviousData,
  })
}

export function useCalendarEvent(id: number | string | undefined) {
  return useQuery({
    queryKey: calendarKeys.events.detail(id ?? ''),
    queryFn: () => fetchEvent(id as number | string),
    enabled: id != null,
  })
}

function useInvalidateEvents() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: calendarKeys.events.all })
}

export function useCreateEvent() {
  const invalidate = useInvalidateEvents()
  return useMutation({
    mutationFn: (payload: CalendarEventPayload) => createEvent(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateEvent() {
  const invalidate = useInvalidateEvents()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number | string; payload: Partial<CalendarEventPayload> }) =>
      updateEvent(id, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteEvent() {
  const invalidate = useInvalidateEvents()
  return useMutation({
    mutationFn: (id: number | string) => deleteEvent(id),
    onSuccess: invalidate,
  })
}

export function useUpdateOccurrence() {
  const invalidate = useInvalidateEvents()
  return useMutation({
    mutationFn: ({ masterId, scope, occurrenceStart, payload }: {
      masterId: number; scope: RecurrenceScope; occurrenceStart: string
      payload: Partial<CalendarEventPayload>
    }) => updateOccurrence(masterId, scope, occurrenceStart, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteOccurrence() {
  const invalidate = useInvalidateEvents()
  return useMutation({
    mutationFn: ({ masterId, scope, occurrenceStart }: {
      masterId: number; scope: RecurrenceScope; occurrenceStart: string
    }) => deleteOccurrence(masterId, scope, occurrenceStart),
    onSuccess: invalidate,
  })
}
