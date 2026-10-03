import { erpClient, ERP_BASE } from '../erpClient'
import type { DreObra, FinanceiroObraLinha } from '../../types'

/** D.1.4 — uma linha por obra com movimento financeiro. */
export async function fetchFinanceiroObras(): Promise<FinanceiroObraLinha[]> {
  const { data } = await erpClient.get<{ obras: FinanceiroObraLinha[] }>(`${ERP_BASE}obras/financeiro/`)
  return data.obras
}

/** D.1.4 — a DRE gerencial de uma obra. */
export async function fetchDreObra(obraId: number): Promise<DreObra> {
  const { data } = await erpClient.get<DreObra>(`${ERP_BASE}obras/${obraId}/dre/`)
  return data
}
