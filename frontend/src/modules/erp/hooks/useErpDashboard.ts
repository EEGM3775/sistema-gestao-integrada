import { useQuery } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import { fetchErpDashboard } from '../api/endpoints/dashboard'

/** KPIs agregados do dashboard financeiro (`/api/erp/dashboard/`), opcionalmente por empreendimento. */
export function useErpDashboard(empreendimentoId?: number) {
  return useQuery({
    queryKey: erpKeys.dashboard.summary(empreendimentoId),
    queryFn: () => fetchErpDashboard(empreendimentoId),
  })
}
