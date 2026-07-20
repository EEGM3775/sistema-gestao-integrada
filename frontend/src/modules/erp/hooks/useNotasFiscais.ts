import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import {
  cancelarNfse, consultarStatusNfse, verificarDocumentoNfse,
  fetchNotasFiscaisRecebidas, fetchNotasFiscaisServico,
} from '../api/endpoints/notasFiscais'
import { emitirNotaFiscalServico } from '../api/endpoints/contasAReceber'
import type { EmitirNfPayload, NotaFiscalRecebidaFiltros, NotaFiscalServicoFiltros } from '../types'

/**
 * Camada de dados das Notas Fiscais (D.1.3, docs/modulos/moduloerp.md §13).
 * Mesmo arquétipo de `useBoletos` (listão server-side). Consultar/cancelar são
 * assíncronos no backend (enfileiram Celery) — por isso invalidam a lista para
 * o novo status aparecer quando a NFE.io responder e o usuário recarregar/repolir.
 */
export function useNotasFiscaisServico(filtros: NotaFiscalServicoFiltros = {}) {
  return useQuery({
    queryKey: erpKeys.notasFiscaisServico.list(filtros),
    queryFn: () => fetchNotasFiscaisServico(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useNotasFiscaisRecebidas(filtros: NotaFiscalRecebidaFiltros = {}) {
  return useQuery({
    queryKey: erpKeys.notasFiscaisRecebidas.list(filtros),
    queryFn: () => fetchNotasFiscaisRecebidas(filtros),
    placeholderData: keepPreviousData,
  })
}

/**
 * Verifica a NFS-e AO VIVO na NFE.io antes de abrir o documento (a versão
 * CANCELADA quando cancelada). Invalida a lista no sucesso (o status pode mudar).
 */
export function useVerificarDocumentoNfse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => verificarDocumentoNfse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.notasFiscaisServico.all })
    },
  })
}

export function useConsultarStatusNfse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => consultarStatusNfse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.notasFiscaisServico.all })
    },
  })
}

export function useCancelarNfse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => cancelarNfse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.notasFiscaisServico.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.dashboard.all })
    },
  })
}

/**
 * Emite uma NFS-e a partir de uma conta a receber (a NF nasce do título — o
 * tomador e o valor vêm dele). Enfileira a task de emissão (202) e invalida a
 * lista de NF (a nota aparece como `PROCESSANDO` na aba Emitidas) + a conta a
 * receber (ganha o vínculo `nota_fiscal_servico`).
 */
export function useEmitirNfse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ contaId, payload }: { contaId: number; payload?: EmitirNfPayload }) =>
      emitirNotaFiscalServico(contaId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.notasFiscaisServico.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.contasAReceber.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.dashboard.all })
    },
  })
}
