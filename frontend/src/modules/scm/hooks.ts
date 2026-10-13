import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import type { Resource } from './api/scmApi'
import {
  produtos, centrosCusto, ofertas, faixas, demandas, itensDemanda,
  cotacoes, propostas, itensProposta, pedidos, itensPedido, recebimentos, avaliacoes,
  getScmDashboard, adjudicarCotacao, publicarDemanda, comprarDireto, gerarDeCotacao, compraAvulsa,
} from './api/scmApi'
import { scmKeys } from './api/queryKeys'
import type {
  Produto, CentroCusto, OfertaFornecedor, Demanda, ItemDemanda, Cotacao, Proposta,
  ItemProposta, PedidoCompra, ItemPedido, Recebimento, AvaliacaoFornecedor,
} from './types'

type Params = Record<string, unknown>
interface Keys { all: readonly unknown[]; list: (p?: Params) => readonly unknown[]; detail: (id: number) => readonly unknown[] }

function makeHooks<T, P>(res: Resource<T, P>, keys: Keys) {
  return {
    useList(params: Params = {}, enabled = true) {
      return useQuery({ queryKey: keys.list(params), queryFn: () => res.listPaged(params), placeholderData: keepPreviousData, enabled })
    },
    useAll(params: Params = {}, enabled = true) {
      return useQuery({ queryKey: [...keys.list(params), 'all'], queryFn: () => res.listAll(params), enabled })
    },
    useDetail(id: number | undefined) {
      return useQuery({ queryKey: keys.detail(id ?? 0), queryFn: () => res.get(id as number), enabled: id != null })
    },
    useCreate() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (payload: P) => res.create(payload), onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) })
    },
    useUpdate() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (v: { id: number; payload: Partial<P> }) => res.update(v.id, v.payload), onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) })
    },
    useRemove() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (id: number) => res.remove(id), onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) })
    },
  }
}

export const produtosHooks = makeHooks<Produto, unknown>(produtos, scmKeys.produtos)
export const centrosCustoHooks = makeHooks<CentroCusto, unknown>(centrosCusto, scmKeys.centrosCusto)
export const ofertasHooks = makeHooks<OfertaFornecedor, unknown>(ofertas, scmKeys.ofertas)
export const faixasHooks = makeHooks<unknown, unknown>(faixas, scmKeys.faixas)
export const demandasHooks = makeHooks<Demanda, unknown>(demandas, scmKeys.demandas)
export const itensDemandaHooks = makeHooks<ItemDemanda, unknown>(itensDemanda, scmKeys.itensDemanda)
export const cotacoesHooks = makeHooks<Cotacao, unknown>(cotacoes, scmKeys.cotacoes)
export const propostasHooks = makeHooks<Proposta, unknown>(propostas, scmKeys.propostas)
export const itensPropostaHooks = makeHooks<ItemProposta, unknown>(itensProposta, scmKeys.itensProposta)
export const pedidosHooks = makeHooks<PedidoCompra, unknown>(pedidos, scmKeys.pedidos)
export const itensPedidoHooks = makeHooks<ItemPedido, unknown>(itensPedido, scmKeys.itensPedido)
export const recebimentosHooks = makeHooks<Recebimento, unknown>(recebimentos, scmKeys.recebimentos)
export const avaliacoesHooks = makeHooks<AvaliacaoFornecedor, unknown>(avaliacoes, scmKeys.avaliacoes)

function useVerb<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: scmKeys.all }) })
}
export const useAdjudicar = () => useVerb((v: { cotacao: number; proposta: number }) => adjudicarCotacao(v.cotacao, v.proposta))
export const usePublicarDemanda = () => useVerb((id: number) => publicarDemanda(id))
export const useComprarDireto = () => useVerb((v: { oferta: number; quantidade: string; centro_custo?: number | null }) => comprarDireto(v))
export const useCompraAvulsa = () => useVerb((v: Parameters<typeof compraAvulsa>[0]) => compraAvulsa(v))
export const useGerarDeCotacao = () => useVerb((cotacao: number) => gerarDeCotacao(cotacao))

export function useScmDashboard(mes?: string) {
  return useQuery({ queryKey: scmKeys.dashboard(mes), queryFn: () => getScmDashboard(mes), placeholderData: keepPreviousData })
}
