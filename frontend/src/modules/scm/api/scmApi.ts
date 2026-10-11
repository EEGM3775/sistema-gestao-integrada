import apiClient from '@/api/apiClient'
import type {
  Paginated, ScmDashboard, Produto, CentroCusto, OfertaFornecedor, Demanda, ItemDemanda,
  Cotacao, Proposta, ItemProposta, PedidoCompra, ItemPedido, Recebimento, AvaliacaoFornecedor,
} from '../types'

// Cliente REST do SCM sobre /api/scm/ (apiClient já injeta auth + refresh).
type Params = Record<string, unknown>

function resource<T, P>(path: string) {
  return {
    listPaged: async (params: Params = {}) => (await apiClient.get<Paginated<T>>(`scm/${path}/`, { params })).data,
    listAll: async (params: Params = {}) => {
      // Endpoints com paginação desligada (itens-*) devolvem array puro.
      const { data } = await apiClient.get<Paginated<T> | T[]>(`scm/${path}/`, { params: { ...params, page_size: 500 } })
      return Array.isArray(data) ? data : data.results
    },
    get: async (id: number) => (await apiClient.get<T>(`scm/${path}/${id}/`)).data,
    create: async (payload: P) => (await apiClient.post<T>(`scm/${path}/`, payload)).data,
    update: async (id: number, payload: Partial<P>) => (await apiClient.patch<T>(`scm/${path}/${id}/`, payload)).data,
    remove: async (id: number) => { await apiClient.delete(`scm/${path}/${id}/`) },
  }
}
export type Resource<T, P> = ReturnType<typeof resource<T, P>>

export const produtos = resource<Produto, unknown>('produtos')
export const centrosCusto = resource<CentroCusto, unknown>('centros-custo')
export const ofertas = resource<OfertaFornecedor, unknown>('ofertas')
export const faixas = resource<unknown, unknown>('faixas-preco')
export const demandas = resource<Demanda, unknown>('demandas')
export const itensDemanda = resource<ItemDemanda, unknown>('itens-demanda')
export const cotacoes = resource<Cotacao, unknown>('cotacoes')
export const propostas = resource<Proposta, unknown>('propostas')
export const itensProposta = resource<ItemProposta, unknown>('itens-proposta')
export const pedidos = resource<PedidoCompra, unknown>('pedidos')
export const itensPedido = resource<ItemPedido, unknown>('itens-pedido')
export const recebimentos = resource<Recebimento, unknown>('recebimentos')
export const avaliacoes = resource<AvaliacaoFornecedor, unknown>('avaliacoes')

export async function getScmDashboard(mes?: string) {
  const { data } = await apiClient.get<ScmDashboard>('scm/dashboard/', { params: mes ? { mes } : {} })
  return data
}

// Verbos de domínio
export const adjudicarCotacao = (cotacao: number, proposta: number) => apiClient.post(`scm/cotacoes/${cotacao}/adjudicar/`, { proposta_id: proposta })
export const publicarDemanda = (demanda: number) => apiClient.post(`scm/demandas/${demanda}/publicar/`)
export const comprarDireto = (body: { oferta: number; quantidade: string; centro_custo?: number | null }) =>
  apiClient.post<{ pedido_id: number }>('scm/pedidos/comprar_direto/', body).then(r => r.data)
export const gerarDeCotacao = (cotacao: number) =>
  apiClient.post<{ pedido_id: number }>('scm/pedidos/gerar_de_cotacao/', { cotacao }).then(r => r.data)

/** Compra sem catálogo e sem cotação — fornecedor, itens, preço (dono, 10/10/2026). */
export interface ItemDeCompraAvulsa { produto?: number | null; descricao?: string; quantidade: string; preco_unitario: string }
export const compraAvulsa = (body: {
  fornecedor: number; centro_custo?: number | null; data_entrega_prevista?: string | null
  observacao?: string; itens: ItemDeCompraAvulsa[]
}) => apiClient.post<{ pedido_id: number }>('scm/pedidos/compra_avulsa/', body).then(r => r.data)
