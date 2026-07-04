import { useQuery } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import { fetchCentrosCusto } from '../api/endpoints/centrosCusto'
import type { CentroCusto } from '../types'

/** Centros de custo ativos do tenant — alimenta os selects do `RateioField` (D.1.1). */
export function useCentrosCusto() {
  return useQuery({
    queryKey: erpKeys.centrosCusto.list(),
    queryFn: () => fetchCentrosCusto(),
    select: (data): CentroCusto[] => (Array.isArray(data) ? data : data.results),
    staleTime: 5 * 60_000,
  })
}
