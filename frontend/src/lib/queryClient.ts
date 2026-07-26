import { QueryClient } from '@tanstack/react-query'

/**
 * Cliente único do TanStack Query (camada de estado de servidor — D.1.0).
 *
 * `staleTime` > 0 evita refetch a cada montagem de tela (o mesmo dado — ex.:
 * uma `ContaPagar`/`ContaReceber` — aparece no dashboard, na obra e no
 * cliente/fornecedor); a invalidação
 * por `queryKey` nas mutações é o gatilho de atualização entre telas.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})
