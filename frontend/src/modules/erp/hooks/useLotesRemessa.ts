import { useQuery } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import { fetchLotesRemessa, fetchLoteRemessa } from '../api/endpoints/lotesRemessa'

export function useLotesRemessa() {
  return useQuery({
    queryKey: erpKeys.lotesRemessa.list(),
    queryFn: () => fetchLotesRemessa(),
  })
}

export function useLoteRemessa(id: number | undefined) {
  return useQuery({
    queryKey: erpKeys.lotesRemessa.detail(id ?? 0),
    queryFn: () => fetchLoteRemessa(id as number),
    enabled: id != null,
  })
}
