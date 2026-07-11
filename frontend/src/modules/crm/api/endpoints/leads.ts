import { crmClient, CRM_BASE } from '../crmClient'
import type {
  Lead,
  LeadPayload,
  LeadFiltros,
  PaginatedResponse,
} from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?status=&source=` para o DRF. */
function cleanParams(filtros: LeadFiltros): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export async function fetchLeads(filtros: LeadFiltros = {}): Promise<PaginatedResponse<Lead>> {
  const { data } = await crmClient.get<PaginatedResponse<Lead>>(`${CRM_BASE}leads/`, {
    params: cleanParams(filtros),
  })
  return data
}

export async function fetchLead(id: string): Promise<Lead> {
  const { data } = await crmClient.get<Lead>(`${CRM_BASE}leads/${id}/`)
  return data
}

export async function createLead(payload: LeadPayload): Promise<Lead> {
  const { data } = await crmClient.post<Lead>(`${CRM_BASE}leads/`, payload)
  return data
}

export async function updateLead(id: string, payload: LeadPayload): Promise<Lead> {
  const { data } = await crmClient.put<Lead>(`${CRM_BASE}leads/${id}/`, payload)
  return data
}

export async function deleteLead(id: string): Promise<void> {
  await crmClient.delete(`${CRM_BASE}leads/${id}/`)
}

/** Converte lead em Account + Contact + Opportunity. */
export async function convertLead(id: string): Promise<{ account: string; contact: string; opportunity: string }> {
  const { data } = await crmClient.post(`${CRM_BASE}leads/${id}/convert/`)
  return data
}

/** Recalcula a pontuação do lead. */
export async function scoreLead(id: string): Promise<Lead> {
  const { data } = await crmClient.post<Lead>(`${CRM_BASE}leads/${id}/score/`)
  return data
}