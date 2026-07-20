import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { crmKeys } from '../api/queryKeys'
import {
  fetchLeads,
  fetchLead,
  createLead,
  updateLead,
  deleteLead,
  convertLead,
  scoreLead,
} from '../api/endpoints/leads'
import type { LeadFiltros, LeadPayload } from '../types'

/**
 * Lista paginada e filtrada de leads (server-side).
 */
export function useLeads(filtros: LeadFiltros = {}) {
  return useQuery({
    queryKey: crmKeys.leads.list(filtros),
    queryFn: () => fetchLeads(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useLead(id: string | undefined) {
  return useQuery({
    queryKey: crmKeys.leads.detail(id ?? ''),
    queryFn: () => fetchLead(id as string),
    enabled: id != null,
  })
}

function useInvalidateLeads() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: crmKeys.leads.all })
  }
}

export function useCreateLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: (payload: LeadPayload) => createLead(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: LeadPayload }) => updateLead(id, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: (id: string) => deleteLead(id),
    onSuccess: invalidate,
  })
}

export function useConvertLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: (id: string) => convertLead(id),
    onSuccess: invalidate,
  })
}

export function useScoreLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: (id: string) => scoreLead(id),
    onSuccess: invalidate,
  })
}