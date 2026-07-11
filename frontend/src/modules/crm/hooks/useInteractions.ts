import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { crmKeys } from '../api/queryKeys'
import {
  fetchInteractions,
  fetchInteraction,
  createInteraction,
  updateInteraction,
  deleteInteraction,
} from '../api/endpoints/interactions'
import type { InteractionFiltros, InteractionPayload } from '../types'

export function useInteractions(filtros: InteractionFiltros = {}) {
  return useQuery({
    queryKey: crmKeys.interactions.list(filtros),
    queryFn: () => fetchInteractions(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useInteraction(id: string | undefined) {
  return useQuery({
    queryKey: crmKeys.interactions.detail(id ?? ''),
    queryFn: () => fetchInteraction(id as string),
    enabled: id != null,
  })
}

function useInvalidateInteractions() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: crmKeys.interactions.all })
  }
}

export function useCreateInteraction() {
  const invalidate = useInvalidateInteractions()
  return useMutation({
    mutationFn: (payload: InteractionPayload) => createInteraction(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateInteraction() {
  const invalidate = useInvalidateInteractions()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: InteractionPayload }) => updateInteraction(id, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteInteraction() {
  const invalidate = useInvalidateInteractions()
  return useMutation({
    mutationFn: (id: string) => deleteInteraction(id),
    onSuccess: invalidate,
  })
}