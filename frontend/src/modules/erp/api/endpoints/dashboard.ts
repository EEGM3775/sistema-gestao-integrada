import { erpClient, ERP_BASE } from '../erpClient'
import type { ErpDashboardData } from '../../types'

export async function fetchErpDashboard(empreendimentoId?: number): Promise<ErpDashboardData> {
  const { data } = await erpClient.get<ErpDashboardData>(`${ERP_BASE}dashboard/`, {
    params: empreendimentoId ? { empreendimento_id: empreendimentoId } : undefined,
  })
  return data
}
