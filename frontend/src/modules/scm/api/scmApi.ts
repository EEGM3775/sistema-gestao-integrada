import apiClient from '@/api/apiClient'
import type {
  PaginatedResponse, EntityOption,
  Produto, ProdutoPayload,
  CentroCusto, CentroCustoPayload,
  OfertaFornecedor, OfertaPayload,
  FaixaPrecoOferta, FaixaPayload,
  Demanda, DemandaPayload,
  ItemDemanda, ItemDemandaPayload,
  Cotacao, CotacaoPayload,
  Proposta, PropostaPayload,
  ItemProposta, ItemPropostaPayload,
  PedidoCompra, PedidoPayload,
  ItemPedido, ItemPedidoPayload,
  Recebimento, RecebimentoPayload,
  AvaliacaoFornecedor, AvaliacaoPayload,
  FornecedorLite, ObraLite, EmpreendimentoLite,
} from '../types'

/** Tudo cai sob `/api/scm/`. */
const SCM = 'scm/'

/** O DRF não deve receber `?status=&tipo=` — remove chaves vazias. */
export function cleanParams(params: Record<string, unknown> = {}): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v as string | number
  }
  return out
}

/** Tolera resposta paginada (listas do SCM) e array cru (fornecedores/obras). */
export function unwrapList<T>(data: PaginatedResponse<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results
}

export interface Resource<T, P> {
  listPaged(params?: Record<string, unknown>): Promise<PaginatedResponse<T>>
  listAll(params?: Record<string, unknown>): Promise<T[]>
  get(id: number): Promise<T>
  create(payload: P): Promise<T>
  update(id: number, payload: Partial<P>): Promise<T>
  remove(id: number): Promise<void>
}

function makeResource<T, P>(path: string): Resource<T, P> {
  return {
    listPaged: (params = {}) =>
      apiClient.get<PaginatedResponse<T>>(`${SCM}${path}`, { params: cleanParams(params) }).then(r => r.data),
    listAll: (params = {}) =>
      apiClient.get<PaginatedResponse<T> | T[]>(`${SCM}${path}`, { params: cleanParams(params) }).then(r => unwrapList(r.data)),
    get: id => apiClient.get<T>(`${SCM}${path}${id}/`).then(r => r.data),
    create: payload => apiClient.post<T>(`${SCM}${path}`, payload).then(r => r.data),
    update: (id, payload) => apiClient.patch<T>(`${SCM}${path}${id}/`, payload).then(r => r.data),
    remove: id => apiClient.delete(`${SCM}${path}${id}/`).then(() => undefined),
  }
}

export const produtos = makeResource<Produto, ProdutoPayload>('produtos/')
export const centrosCusto = makeResource<CentroCusto, CentroCustoPayload>('centros-custo/')
export const ofertas = makeResource<OfertaFornecedor, OfertaPayload>('ofertas/')
export const faixas = makeResource<FaixaPrecoOferta, FaixaPayload>('faixas-preco/')
export const demandas = makeResource<Demanda, DemandaPayload>('demandas/')
export const itensDemanda = makeResource<ItemDemanda, ItemDemandaPayload>('itens-demanda/')
export const cotacoes = makeResource<Cotacao, CotacaoPayload>('cotacoes/')
export const propostas = makeResource<Proposta, PropostaPayload>('propostas/')
export const itensProposta = makeResource<ItemProposta, ItemPropostaPayload>('itens-proposta/')
export const pedidos = makeResource<PedidoCompra, PedidoPayload>('pedidos/')
export const itensPedido = makeResource<ItemPedido, ItemPedidoPayload>('itens-pedido/')
export const recebimentos = makeResource<Recebimento, RecebimentoPayload>('recebimentos/')
export const avaliacoes = makeResource<AvaliacaoFornecedor, AvaliacaoPayload>('avaliacoes/')

// ─── Verbos de domínio ───────────────────────────────────────────────────────

export const publicarDemanda = (id: number) =>
  apiClient.post<Demanda>(`${SCM}demandas/${id}/publicar/`).then(r => r.data)

export const adjudicarCotacao = (id: number, propostaId: number) =>
  apiClient.post<Cotacao>(`${SCM}cotacoes/${id}/adjudicar/`, { proposta_id: propostaId }).then(r => r.data)

export const comprarDireto = (payload: { oferta: number; quantidade: string; centro_custo?: number | null }) =>
  apiClient.post<PedidoCompra>(`${SCM}pedidos/comprar_direto/`, payload).then(r => r.data)

export const gerarDeCotacao = (cotacao: number) =>
  apiClient.post<PedidoCompra>(`${SCM}pedidos/gerar_de_cotacao/`, { cotacao }).then(r => r.data)

// ─── Selects server-side (busca) e resolvedores de valor pré-selecionado ──────

export async function searchProdutos(search: string): Promise<EntityOption[]> {
  const data = await produtos.listPaged({ search, page_size: 20 })
  return data.results.map(p => ({ value: p.produto_id, label: p.descricao, hint: p.codigo_interno }))
}
export const resolveProduto = (id: number): Promise<EntityOption> =>
  produtos.get(id).then(p => ({ value: p.produto_id, label: p.descricao, hint: p.codigo_interno }))

export async function searchCentrosCusto(search: string): Promise<EntityOption[]> {
  const data = await centrosCusto.listPaged({ search, ativo: true, page_size: 20 })
  return data.results.map(c => ({ value: c.centro_custo_id, label: c.nome, hint: c.codigo }))
}
export const resolveCentroCusto = (id: number): Promise<EntityOption> =>
  centrosCusto.get(id).then(c => ({ value: c.centro_custo_id, label: c.nome, hint: c.codigo }))

export async function searchOfertasDiretas(search: string): Promise<EntityOption[]> {
  const data = await ofertas.listPaged({ search, compra_direta: true, ativo: true, page_size: 20 })
  return data.results.map(o => ({
    value: o.oferta_id,
    label: `${o.produto_descricao ?? `#${o.produto}`} — ${o.fornecedor_nome ?? ''}`,
    hint: o.produto_codigo,
  }))
}

export async function searchFornecedores(search: string): Promise<EntityOption[]> {
  const { data } = await apiClient.get<PaginatedResponse<FornecedorLite> | FornecedorLite[]>(
    'fornecedores/', { params: cleanParams({ search, page_size: 20 }) },
  )
  return unwrapList(data).map(f => ({ value: f.fornecedor_id, label: f.razao_social, hint: f.cnpj }))
}
export const resolveFornecedor = (id: number): Promise<EntityOption> =>
  apiClient.get<FornecedorLite>(`fornecedores/${id}/`)
    .then(r => ({ value: r.data.fornecedor_id, label: r.data.razao_social, hint: r.data.cnpj }))

/** Obras/empreendimentos são poucos por tenant — carregados inteiros (vínculo opcional do centro de custo). */
export async function listObrasOpt(): Promise<EntityOption[]> {
  const { data } = await apiClient.get<PaginatedResponse<ObraLite> | ObraLite[]>('obras/')
  return unwrapList(data).map(o => ({ value: o.obra_id, label: o.nome_obra }))
}
export async function listEmpreendimentosOpt(): Promise<EntityOption[]> {
  const { data } = await apiClient.get<PaginatedResponse<EmpreendimentoLite> | EmpreendimentoLite[]>('empreendimentos/')
  return unwrapList(data).map(e => ({ value: e.empreendimento_id, label: e.empreendimento }))
}
