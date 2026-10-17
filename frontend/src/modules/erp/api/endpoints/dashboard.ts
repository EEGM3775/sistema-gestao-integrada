import { erpClient, ERP_BASE } from '../erpClient'
import type { ErpDashboardData, PeriodoFluxo } from '../../types'

export async function fetchErpDashboard(empreendimentoId?: number, periodo?: PeriodoFluxo): Promise<ErpDashboardData> {
  const { data } = await erpClient.get<ErpDashboardData>(`${ERP_BASE}dashboard/`, {
    params: {
      ...(empreendimentoId ? { empreendimento_id: empreendimentoId } : {}),
      ...(periodo ? { fluxo_inicio: periodo.inicio, fluxo_fim: periodo.fim } : {}),
    },
  })
  return data
}
