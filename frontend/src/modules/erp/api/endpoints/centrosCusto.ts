import { erpClient, ERP_BASE } from '../erpClient'
import type { CentroCusto, PaginatedResponse } from '../../types'

/** Lista de centros de custo do tenant — usada nos selects do `RateioField` (D.1.1). */
export async function fetchCentrosCusto(): Promise<PaginatedResponse<CentroCusto> | CentroCusto[]> {
  const { data } = await erpClient.get<PaginatedResponse<CentroCusto> | CentroCusto[]>(`${ERP_BASE}centros-custo/`, {
    params: { ativo: true, page_size: 200 },
  })
  return data
}
