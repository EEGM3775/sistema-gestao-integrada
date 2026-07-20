import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { crmKeys } from '../api/queryKeys'
import {
  fetchOpportunities,
  fetchOpportunity,
  createOpportunity,
  updateOpportunity,
  deleteOpportunity,
  fetchOpportunityProducts,
  createOpportunityProduct,
  updateOpportunityProduct,
  deleteOpportunityProduct,
} from '../api/endpoints/opportunities'
import type { OpportunityFiltros, OpportunityPayload, OpportunityProductPayload } from '../types'

export function useOpportunities(filtros: OpportunityFiltros = {}) {
  return useQuery({
    queryKey: crmKeys.opportunities.list(filtros),
    queryFn: () => fetchOpportunities(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useOpportunity(id: string | undefined) {
  return useQuery({
    queryKey: crmKeys.opportunities.detail(id ?? ''),
    queryFn: () => fetchOpportunity(id as string),
    enabled: id != null,
  })
}

function useInvalidateOpportunities() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: crmKeys.opportunities.all })
  }
}

export function useCreateOpportunity() {
  const invalidate = useInvalidateOpportunities()
  return useMutation({
    mutationFn: (payload: OpportunityPayload) => createOpportunity(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateOpportunity() {
  const invalidate = useInvalidateOpportunities()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OpportunityPayload }) => updateOpportunity(id, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteOpportunity() {
  const invalidate = useInvalidateOpportunities()
  return useMutation({
    mutationFn: (id: string) => deleteOpportunity(id),
    onSuccess: invalidate,
  })
}

// ─── Opportunity Products ─────────────────────────────────────────────────────

export function useOpportunityProducts(opportunityId?: string) {
  return useQuery({
    queryKey: ['crm', 'opportunity-products', opportunityId ?? null],
    queryFn: () => fetchOpportunityProducts(opportunityId),
    enabled: opportunityId != null,
  })
}

export function useCreateOpportunityProduct() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: OpportunityProductPayload) => createOpportunityProduct(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm', 'opportunity-products'] })
    },
  })
}

export function useUpdateOpportunityProduct() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OpportunityProductPayload }) => updateOpportunityProduct(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm', 'opportunity-products'] })
    },
  })
}

export function useDeleteOpportunityProduct() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteOpportunityProduct(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm', 'opportunity-products'] })
    },
  })
}