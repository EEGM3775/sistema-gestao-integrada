import { useQuery } from '@tanstack/react-query'
import { getDivergenciasAsaas, type RelatorioDivergenciasAsaas } from '@/modules/clientes/services/clientesService'

/**
 * Divergências de cadastro relevantes ao ERP (hoje: identidade banco × Asaas —
 * o que bloquearia/desviaria uma cobrança). Estruturado como a fonte única do
 * alerta de divergências do módulo; novas categorias de divergência de ERP
 * entram agregando aqui.
 *
 * `staleTime` alto porque cada carga bate no gateway externo (Asaas); `retry:
 * false` porque um 502 (Asaas fora) não deve entrar em loop de retry.
 */
export function useDivergenciasErp(enabled: boolean) {
  return useQuery<RelatorioDivergenciasAsaas>({
    queryKey: ['erp', 'divergencias', 'asaas'],
    queryFn: async () => (await getDivergenciasAsaas()).data,
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}
