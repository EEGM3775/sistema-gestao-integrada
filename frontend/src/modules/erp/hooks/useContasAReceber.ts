import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import {
  fetchContasAReceber, fetchContaAReceber, createContaAReceber, updateContaAReceber,
  darBaixaContaAReceber, emitirNotaFiscalServico, emitirNotaFiscalProduto,
} from '../api/endpoints/contasAReceber'
import type { BaixaPayload, ContaReceberFiltros, ContaReceberPayload, EmitirNfPayload } from '../types'

/**
 * Lista paginada e filtrada de contas a receber (server-side — D.1.1).
 *
 * `placeholderData: keepPreviousData` mantém a página atual visível enquanto a
 * próxima carrega — evita o "pisca" da tabela ao trocar de página/filtro.
 */
export function useContasAReceber(filtros: ContaReceberFiltros = {}) {
  return useQuery({
    queryKey: erpKeys.contasAReceber.list(filtros),
    queryFn: () => fetchContasAReceber(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useContaAReceber(id: number | undefined) {
  return useQuery({
    queryKey: erpKeys.contasAReceber.detail(id ?? 0),
    queryFn: () => fetchContaAReceber(id as number),
    enabled: id != null,
  })
}

/**
 * Invalida `.all` (toda lista/detalhe) + `boletos.all` + `dashboard.all` — o mesmo
 * dado visto de ângulos diferentes (listão, Sheet de detalhe, KPIs/aging do hub,
 * workspace de boletos) se atualiza sozinho após qualquer mutação
 * (docs/modulos/moduloerp.md §5.4). `boletos` entra porque a baixa que quita a
 * conta agora marca o boleto vinculado como PAGO (D3) — sem invalidar aqui, o
 * badge do boleto seguiria "Emitido" até um refresh manual.
 */
function useInvalidateContasAReceber() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: erpKeys.contasAReceber.all })
    queryClient.invalidateQueries({ queryKey: erpKeys.boletos.all })
    queryClient.invalidateQueries({ queryKey: erpKeys.dashboard.all })
  }
}

export function useCreateContaAReceber() {
  const invalidate = useInvalidateContasAReceber()
  return useMutation({
    mutationFn: (payload: ContaReceberPayload) => createContaAReceber(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateContaAReceber() {
  const invalidate = useInvalidateContasAReceber()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ContaReceberPayload }) => updateContaAReceber(id, payload),
    onSuccess: invalidate,
  })
}

/** Baixa manual (total ou parcial) — único caminho de quitação, espelhado pelo futuro webhook do Asaas (D.1.2). */
export function useDarBaixaContaAReceber() {
  const invalidate = useInvalidateContasAReceber()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: BaixaPayload }) => darBaixaContaAReceber(id, payload),
    onSuccess: invalidate,
  })
}

export function useEmitirNotaFiscalServico() {
  const invalidate = useInvalidateContasAReceber()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload?: EmitirNfPayload }) => emitirNotaFiscalServico(id, payload),
    onSuccess: invalidate,
  })
}

export function useEmitirNotaFiscalProduto() {
  const invalidate = useInvalidateContasAReceber()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload?: EmitirNfPayload }) => emitirNotaFiscalProduto(id, payload),
    onSuccess: invalidate,
  })
}
