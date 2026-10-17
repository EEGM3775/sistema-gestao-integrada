import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { calendarKeys } from '../api/queryKeys'
import {
  createAgenda, deleteAgenda, fetchAgendas, importarIcs, responderConvite, updateAgenda,
  type RecorteIcs,
} from '../api/endpoints/agendas'
import type { AgendaPayload, RsvpStatus } from '../types'

export function useAgendas() {
  return useQuery({ queryKey: calendarKeys.agendas, queryFn: fetchAgendas, staleTime: 60_000 })
}

/** Mexer numa agenda muda o que o feed mostra: invalida as duas coisas. */
function useInvalidarTudo() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: calendarKeys.all })
}

export function useSalvarAgenda() {
  const invalidar = useInvalidarTudo()
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: AgendaPayload }) =>
      id == null ? createAgenda(payload) : updateAgenda(id, payload),
    onSuccess: invalidar,
  })
}

export function useApagarAgenda() {
  const invalidar = useInvalidarTudo()
  return useMutation({ mutationFn: (id: number) => deleteAgenda(id), onSuccess: invalidar })
}

export function useResponderConvite() {
  const invalidar = useInvalidarTudo()
  return useMutation({
    mutationFn: ({ eventId, status }: { eventId: number; status: Exclude<RsvpStatus, 'pendente'> }) =>
      responderConvite(eventId, status),
    onSuccess: invalidar,
  })
}

export function useImportarIcs() {
  const invalidar = useInvalidarTudo()
  return useMutation({
    mutationFn: ({ arquivo, recorte }: { arquivo: File; recorte: RecorteIcs }) => importarIcs(arquivo, recorte),
    onSuccess: invalidar,
  })
}
