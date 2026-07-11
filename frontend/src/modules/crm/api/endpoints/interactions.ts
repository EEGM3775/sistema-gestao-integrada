import { crmClient, CRM_BASE } from '../crmClient'
import type {
  Interaction,
  InteractionPayload,
  InteractionFiltros,
  PaginatedResponse,
} from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?type=` vazio para o DRF. */
function cleanParams(filtros: InteractionFiltros): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export async function fetchInteractions(filtros: InteractionFiltros = {}): Promise<PaginatedResponse<Interaction>> {
  const { data } = await crmClient.get<PaginatedResponse<Interaction>>(`${CRM_BASE}interactions/`, {
    params: cleanParams(filtros),
  })
  return data
}

export async function fetchInteraction(id: string): Promise<Interaction> {
  const { data } = await crmClient.get<Interaction>(`${CRM_BASE}interactions/${id}/`)
  return data
}

export async function createInteraction(payload: InteractionPayload): Promise<Interaction> {
  const { data } = await crmClient.post<Interaction>(`${CRM_BASE}interactions/`, payload)
  return data
}

export async function updateInteraction(id: string, payload: InteractionPayload): Promise<Interaction> {
  const { data } = await crmClient.put<Interaction>(`${CRM_BASE}interactions/${id}/`, payload)
  return data
}

export async function deleteInteraction(id: string): Promise<void> {
  await crmClient.delete(`${CRM_BASE}interactions/${id}/`)
}