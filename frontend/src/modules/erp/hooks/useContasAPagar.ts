import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import {
  fetchContasAPagar, fetchContaAPagar, createContaAPagar, updateContaAPagar,
  darBaixaContaAPagar, gerarLoteRemessa,
} from '../api/endpoints/contasAPagar'
import type { BaixaPayload, ContaPagarFiltros, ContaPagarPayload, GerarLoteRemessaPayload } from '../types'

/**
 * Lista paginada e filtrada de contas a pagar (server-side — D.1.1).
 *
 * `placeholderData: keepPreviousData` mantém a página atual visível enquanto a
 * próxima carrega — evita o "pisca" da tabela ao trocar de página/filtro.
 */
export function useContasAPagar(filtros: ContaPagarFiltros = {}) {
  return useQuery({
    queryKey: erpKeys.contasAPagar.list(filtros),
    queryFn: () => fetchContasAPagar(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useContaAPagar(id: number | undefined) {
  return useQuery({
    queryKey: erpKeys.contasAPagar.detail(id ?? 0),
    queryFn: () => fetchContaAPagar(id as number),
    enabled: id != null,
  })
}

/**
 * Invalida `.all` (toda lista/detalhe) + `dashboard.all` — o mesmo dado visto
 * de ângulos diferentes (listão, Sheet de detalhe, KPIs/aging do hub) se
 * atualiza sozinho após qualquer mutação (docs/modulos/moduloerp.md §5.4).
 */
function useInvalidateContasAPagar() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: erpKeys.contasAPagar.all })
    queryClient.invalidateQueries({ queryKey: erpKeys.dashboard.all })
    queryClient.invalidateQueries({ queryKey: erpKeys.grade.all })
  }
}

export function useCreateContaAPagar() {
  const invalidate = useInvalidateContasAPagar()
  return useMutation({
    mutationFn: (payload: ContaPagarPayload) => createContaAPagar(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateContaAPagar() {
  const invalidate = useInvalidateContasAPagar()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ContaPagarPayload }) => updateContaAPagar(id, payload),
    onSuccess: invalidate,
  })
}

/** Baixa manual (total ou parcial) — único caminho de quitação, espelhado pelo futuro webhook do Asaas (D.1.2). */
export function useDarBaixaContaAPagar() {
  const invalidate = useInvalidateContasAPagar()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: BaixaPayload }) => darBaixaContaAPagar(id, payload),
    onSuccess: invalidate,
  })
}

/** Registra um lote de remessa bancária — afeta tanto as contas selecionadas quanto a lista de lotes. */
export function useGerarLoteRemessa() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: GerarLoteRemessaPayload) => gerarLoteRemessa(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.contasAPagar.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.lotesRemessa.all })
    },
  })
}
