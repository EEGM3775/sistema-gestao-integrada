import { crmClient, CRM_BASE } from '../crmClient'
import type {
  Opportunity,
  OpportunityPayload,
  OpportunityFiltros,
  OpportunityProduct,
  OpportunityProductPayload,
  PaginatedResponse,
} from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?search=` vazio para o DRF. */
function cleanParams(filtros: OpportunityFiltros): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export async function fetchOpportunities(filtros: OpportunityFiltros = {}): Promise<PaginatedResponse<Opportunity>> {
  const { data } = await crmClient.get<PaginatedResponse<Opportunity>>(`${CRM_BASE}opportunities/`, {
    params: cleanParams(filtros),
  })
  return data
}

export async function fetchOpportunity(id: string): Promise<Opportunity> {
  const { data } = await crmClient.get<Opportunity>(`${CRM_BASE}opportunities/${id}/`)
  return data
}

export async function createOpportunity(payload: OpportunityPayload): Promise<Opportunity> {
  const { data } = await crmClient.post<Opportunity>(`${CRM_BASE}opportunities/`, payload)
  return data
}

export async function updateOpportunity(id: string, payload: OpportunityPayload): Promise<Opportunity> {
  const { data } = await crmClient.put<Opportunity>(`${CRM_BASE}opportunities/${id}/`, payload)
  return data
}

export async function deleteOpportunity(id: string): Promise<void> {
  await crmClient.delete(`${CRM_BASE}opportunities/${id}/`)
}

// ─── Opportunity Products ─────────────────────────────────────────────────────

export async function fetchOpportunityProducts(opportunityId?: string): Promise<PaginatedResponse<OpportunityProduct>> {
  const { data } = await crmClient.get<PaginatedResponse<OpportunityProduct>>(`${CRM_BASE}opportunity-products/`, {
    params: opportunityId ? { opportunity_id: opportunityId } : undefined,
  })
  return data
}

export async function createOpportunityProduct(payload: OpportunityProductPayload): Promise<OpportunityProduct> {
  const { data } = await crmClient.post<OpportunityProduct>(`${CRM_BASE}opportunity-products/`, payload)
  return data
}

export async function updateOpportunityProduct(id: string, payload: OpportunityProductPayload): Promise<OpportunityProduct> {
  const { data } = await crmClient.put<OpportunityProduct>(`${CRM_BASE}opportunity-products/${id}/`, payload)
  return data
}

export async function deleteOpportunityProduct(id: string): Promise<void> {
  await crmClient.delete(`${CRM_BASE}opportunity-products/${id}/`)
}