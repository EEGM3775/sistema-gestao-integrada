import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import type { Resource } from './api/scmApi'
import {
  produtos, centrosCusto, ofertas, faixas, demandas, itensDemanda,
  cotacoes, propostas, itensProposta, pedidos, itensPedido, recebimentos, avaliacoes,
  publicarDemanda, adjudicarCotacao, comprarDireto, gerarDeCotacao,
} from './api/scmApi'
import { scmKeys } from './api/queryKeys'

type Params = Record<string, unknown>
interface KeyRoot {
  all: readonly unknown[]
  list: (p?: Params) => readonly unknown[]
  detail: (id: number) => readonly unknown[]
}

function makeHooks<T, P>(resource: Resource<T, P>, keys: KeyRoot) {
  return {
    useList(params: Params = {}) {
      return useQuery({ queryKey: keys.list(params), queryFn: () => resource.listPaged(params), placeholderData: keepPreviousData })
    },
    useAll(params: Params = {}, enabled = true) {
      return useQuery({ queryKey: [...keys.list(params), 'all'], queryFn: () => resource.listAll(params), enabled })
    },
    useDetail(id: number | undefined) {
      return useQuery({ queryKey: keys.detail(id ?? 0), queryFn: () => resource.get(id as number), enabled: id != null })
    },
    useCreate() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (payload: P) => resource.create(payload), onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) })
    },
    useUpdate() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (v: { id: number; payload: Partial<P> }) => resource.update(v.id, v.payload), onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) })
    },
    useRemove() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (id: number) => resource.remove(id), onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) })
    },
  }
}

export const produtosHooks = makeHooks(produtos, scmKeys.produtos)
export const centrosCustoHooks = makeHooks(centrosCusto, scmKeys.centrosCusto)
export const ofertasHooks = makeHooks(ofertas, scmKeys.ofertas)
export const faixasHooks = makeHooks(faixas, scmKeys.faixas)
export const demandasHooks = makeHooks(demandas, scmKeys.demandas)
export const itensDemandaHooks = makeHooks(itensDemanda, scmKeys.itensDemanda)
export const cotacoesHooks = makeHooks(cotacoes, scmKeys.cotacoes)
export const propostasHooks = makeHooks(propostas, scmKeys.propostas)
export const itensPropostaHooks = makeHooks(itensProposta, scmKeys.itensProposta)
export const pedidosHooks = makeHooks(pedidos, scmKeys.pedidos)
export const itensPedidoHooks = makeHooks(itensPedido, scmKeys.itensPedido)
export const recebimentosHooks = makeHooks(recebimentos, scmKeys.recebimentos)
export const avaliacoesHooks = makeHooks(avaliacoes, scmKeys.avaliacoes)

/** Verbos de domínio afetam vários recursos — invalidam a raiz `scm` inteira. */
function useScmVerb<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: scmKeys.all }) })
}

export const usePublicarDemanda = () => useScmVerb((id: number) => publicarDemanda(id))
export const useAdjudicar = () => useScmVerb((v: { cotacao: number; proposta: number }) => adjudicarCotacao(v.cotacao, v.proposta))
export const useComprarDireto = () => useScmVerb((v: { oferta: number; quantidade: string; centro_custo?: number | null }) => comprarDireto(v))
export const useGerarDeCotacao = () => useScmVerb((cotacao: number) => gerarDeCotacao(cotacao))

// ─── Hub (S.4) — contagens baratas via `count` da paginação ────────────────────

export interface ScmDashboard {
  demandasAbertas: number
  demandasEmCotacao: number
  cotacoesAbertas: number
  pedidosAprovados: number
  pedidosEnviados: number
  pedidosRecebidosParcial: number
  produtosAtivos: number
  ofertasDiretas: number
}

export function useScmDashboard() {
  return useQuery({
    queryKey: scmKeys.dashboard,
    queryFn: async (): Promise<ScmDashboard> => {
      const c = (p: Promise<{ count: number }>) => p.then(r => r.count)
      const [
        demandasAbertas, demandasEmCotacao, cotacoesAbertas,
        pedidosAprovados, pedidosEnviados, pedidosRecebidosParcial,
        produtosAtivos, ofertasDiretas,
      ] = await Promise.all([
        c(demandas.listPaged({ status: 'aberta', page_size: 1 })),
        c(demandas.listPaged({ status: 'em_cotacao', page_size: 1 })),
        c(cotacoes.listPaged({ status: 'aberta', page_size: 1 })),
        c(pedidos.listPaged({ status: 'aprovado', page_size: 1 })),
        c(pedidos.listPaged({ status: 'enviado', page_size: 1 })),
        c(pedidos.listPaged({ status: 'recebido_parcial', page_size: 1 })),
        c(produtos.listPaged({ ativo: true, page_size: 1 })),
        c(ofertas.listPaged({ compra_direta: true, page_size: 1 })),
      ])
      return {
        demandasAbertas, demandasEmCotacao, cotacoesAbertas,
        pedidosAprovados, pedidosEnviados, pedidosRecebidosParcial,
        produtosAtivos, ofertasDiretas,
      }
    },
  })
}
