import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import {
  fetchBoletos, fetchBoleto, gerarCobrancaContaAReceber,
  cancelarBoleto, verificarDocumentoBoleto,
} from '../api/endpoints/boletos'
import { fetchEventosWebhookAsaasPorBoleto } from '../api/endpoints/eventosWebhookAsaas'
import type { BoletoFiltros } from '../types'

/**
 * Lista paginada e filtrada de boletos (server-side — D.1.2, mesmo arquétipo
 * de `useContasAReceber`/`useContasAPagar`).
 */
export function useBoletos(filtros: BoletoFiltros = {}) {
  return useQuery({
    queryKey: erpKeys.boletos.list(filtros),
    queryFn: () => fetchBoletos(filtros),
    placeholderData: keepPreviousData,
  })
}

export function useBoleto(id: number | undefined) {
  return useQuery({
    queryKey: erpKeys.boletos.detail(id ?? 0),
    queryFn: () => fetchBoleto(id as number),
    enabled: id != null,
  })
}

/** Timeline de eventos do webhook Asaas do boleto — `BoletoDetailPage` (D.1.2). */
export function useEventosWebhookAsaas(boletoId: number | undefined) {
  return useQuery({
    queryKey: erpKeys.eventosWebhookAsaas.porBoleto(boletoId ?? 0),
    queryFn: () => fetchEventosWebhookAsaasPorBoleto(boletoId as number),
    enabled: boletoId != null,
  })
}

/**
 * Aciona `gerar-cobranca` na `ContaReceber` (D.1.2): a task Celery cria o
 * `Boleto` de forma assíncrona — por isso invalida tanto `contasAReceber`
 * (a conta exibe `boletos[]` no detalhe) quanto `boletos` (a listagem
 * dedicada) + `dashboard`, mesmo arquétipo de `useDarBaixaContaAReceber`.
 */
export function useGerarCobrancaContaAReceber() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (contaReceberId: number) => gerarCobrancaContaAReceber(contaReceberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.contasAReceber.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.boletos.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.dashboard.all })
    },
  })
}

/**
 * Cancela o boleto no Asaas (síncrono no backend — devolve o boleto já
 * CANCELADO). Invalida boletos + contas a receber (a conta aninha `boletos[]`).
 */
export function useCancelarBoleto() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => cancelarBoleto(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.boletos.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.contasAReceber.all })
      queryClient.invalidateQueries({ queryKey: erpKeys.dashboard.all })
    },
  })
}

/**
 * Verifica o boleto AO VIVO no Asaas antes de abrir o documento. Como pode
 * mudar o status/URL local, invalida a lista de boletos no sucesso.
 */
export function useVerificarDocumentoBoleto() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => verificarDocumentoBoleto(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.boletos.all })
    },
  })
}
