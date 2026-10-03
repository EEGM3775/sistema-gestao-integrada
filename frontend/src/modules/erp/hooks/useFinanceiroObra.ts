import { useQuery } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import { fetchDreObra, fetchFinanceiroObras } from '../api/endpoints/financeiroObra'

/** D.1.4 — a lista do financeiro por obra (receita, custo, resultado). */
export function useFinanceiroObras() {
  return useQuery({ queryKey: erpKeys.financeiroObra.lista(), queryFn: fetchFinanceiroObras })
}

/** D.1.4 — a DRE de uma obra. */
export function useDreObra(obraId: number | null) {
  return useQuery({
    queryKey: erpKeys.financeiroObra.dre(obraId ?? 0),
    queryFn: () => fetchDreObra(obraId as number),
    enabled: obraId != null,
  })
}
