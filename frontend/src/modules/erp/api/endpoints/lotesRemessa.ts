import { erpClient, ERP_BASE } from '../erpClient'
import type { LoteRemessa, PaginatedResponse } from '../../types'

export async function fetchLotesRemessa(): Promise<PaginatedResponse<LoteRemessa>> {
  const { data } = await erpClient.get<PaginatedResponse<LoteRemessa>>(`${ERP_BASE}lotes-remessa/`)
  return data
}

export async function fetchLoteRemessa(id: number): Promise<LoteRemessa> {
  const { data } = await erpClient.get<LoteRemessa>(`${ERP_BASE}lotes-remessa/${id}/`)
  return data
}
