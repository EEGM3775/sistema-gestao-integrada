import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import { fetchErpDashboard } from '../api/endpoints/dashboard'
import type { PeriodoFluxo } from '../types'

/**
 * KPIs agregados do dashboard financeiro (`/api/erp/dashboard/`), opcionalmente
 * por empreendimento e com o período do fluxo de caixa. Trocar o período mantém
 * o painel anterior na tela até o novo chegar (sem piscar o hub inteiro).
 */
export function useErpDashboard(empreendimentoId?: number, periodo?: PeriodoFluxo) {
  return useQuery({
    queryKey: erpKeys.dashboard.summary(empreendimentoId, periodo),
    queryFn: () => fetchErpDashboard(empreendimentoId, periodo),
    placeholderData: keepPreviousData,
  })
}
