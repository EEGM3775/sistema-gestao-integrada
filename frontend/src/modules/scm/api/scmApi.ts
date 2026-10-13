import apiClient from '@/api/apiClient'
import type {
  Paginated, ScmDashboard, Produto, CentroCusto, OfertaFornecedor, Demanda, ItemDemanda,
  Cotacao, Proposta, ItemProposta, PedidoCompra, ItemPedido, Recebimento, AvaliacaoFornecedor,
  PainelPedido, NotaFiscalCompra, ItemCadastrado, FichaItem,
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

// ─── D284: o pedido de ponta a ponta ─────────────────────────────────────────
export const painelPedido = (id: number) => apiClient.get<PainelPedido>(`scm/pedidos/${id}/painel/`).then(r => r.data)

/** Multipart: as linhas viajam como JSON e a NF-e (número, chave, XML, PDF) vai junto. */
export function receberPedido(id: number, body: {
  itens: { item_pedido: number; quantidade: string }[]; data: string; encerrar: boolean; observacao?: string
  nf_numero?: string; nf_serie?: string; nf_chave?: string; nf_xml?: File | null; nf_pdf?: File | null
}) {
  const fd = new FormData()
  fd.append('itens', JSON.stringify(body.itens)); fd.append('data', body.data); fd.append('encerrar', body.encerrar ? 'true' : 'false')
  if (body.observacao) fd.append('observacao', body.observacao)
  if (body.nf_numero) fd.append('nf_numero', body.nf_numero)
  if (body.nf_serie) fd.append('nf_serie', body.nf_serie)
  if (body.nf_chave) fd.append('nf_chave', body.nf_chave)
  if (body.nf_xml) fd.append('nf_xml', body.nf_xml)
  if (body.nf_pdf) fd.append('nf_pdf', body.nf_pdf)
  return apiClient.post<{ status_pedido: string; a_mais: string[]; encerrados: string[]; aguardando_nfe: boolean }>(`scm/pedidos/${id}/receber/`, fd).then(r => r.data)
}

export function lancarNota(pedido: number, body: { numero?: string; serie?: string; chave?: string; xml?: File | null; pdf?: File | null; recebimento?: number | null }) {
  const fd = new FormData()
  for (const [k, v] of Object.entries(body)) if (v != null && v !== '') fd.append(k, v instanceof File ? v : String(v))
  return apiClient.post<NotaFiscalCompra>(`scm/pedidos/${pedido}/notas/`, fd).then(r => r.data)
}
export function anexarDocumentoNota(nota: number, body: { chave?: string; xml?: File | null; pdf?: File | null }) {
  const fd = new FormData()
  for (const [k, v] of Object.entries(body)) if (v != null && v !== '') fd.append(k, v instanceof File ? v : String(v))
  return apiClient.post<NotaFiscalCompra>(`scm/notas-fiscais/${nota}/documento/`, fd).then(r => r.data)
}
export const abrirCotacaoDaDemanda = (demanda: number, data_limite?: string | null) =>
  apiClient.post<{ demanda_id: number; cotacao_id: number }>(`scm/demandas/${demanda}/abrir-cotacao/`, { data_limite: data_limite || null }).then(r => r.data)
/** Cotar direto do catálogo: demanda + cotação abertas de uma vez. */
export const cotarItens = (body: { itens: { produto: number; quantidade: string }[]; centro_custo?: number | null; data_limite?: string | null; observacao?: string }) =>
  apiClient.post<{ demanda_id: number; cotacao_id: number }>('scm/demandas/cotar/', body).then(r => r.data)
export const corrigirNota =(nota: number, body: { numero: string; serie: string; chave: string }) =>
  apiClient.post<NotaFiscalCompra>(`scm/notas-fiscais/${nota}/corrigir/`, body).then(r => r.data)
export const removerNota = (nota: number, motivo = '') =>
  apiClient.post(`scm/notas-fiscais/${nota}/remover/`, { motivo }).then(r => r.data)
export interface MeioDigitado{ tipo: string; valor: string; parcelas: number; primeiro_vencimento: string; intervalo_dias: number; descricao: string }
export const definirCobranca = (pedido: number, meios: MeioDigitado[]) =>
  apiClient.post<{ titulos: number[] }>(`scm/pedidos/${pedido}/cobranca/`, { meios }).then(r => r.data)
export const editarPedido = (pedido: number, body: Record<string, unknown>) =>
  apiClient.post<{ mudancas: string[] }>(`scm/pedidos/${pedido}/editar/`, body).then(r => r.data)
export const cancelarPedido = (pedido: number, motivo: string) =>
  apiClient.post(`scm/pedidos/${pedido}/cancelar/`, { motivo }).then(r => r.data)
export const enviarPedido = (pedido: number, canal: 'email' | 'whatsapp' | 'impresso', para = '') =>
  apiClient.post<PedidoCompra>(`scm/pedidos/${pedido}/enviar/`, { canal, para }).then(r => r.data)
export const pdfDoPedido = (pedido: number) =>
  apiClient.get<Blob>(`scm/pedidos/${pedido}/pdf/`, { responseType: 'blob' }).then(r => r.data)
export const cadastrarItem = (body: { descricao?: string; unidade?: string; fornecedor?: number | null; preco?: string; item_pedido?: number }) =>
  apiClient.post<ItemCadastrado>('scm/pedidos/cadastrar_item/', body).then(r => r.data)
export const fichaItem = (item: number) => apiClient.get<FichaItem>(`catalogo/itens/${item}/ficha/`).then(r => r.data)

/** Compra sem catálogo e sem cotação — fornecedor, itens, preço (dono, 10/10/2026). */
export interface ItemDeCompraAvulsa { produto?: number | null; descricao?: string; unidade?: string; quantidade: string; preco_unitario: string }
export const compraAvulsa = (body: {
  fornecedor: number; centro_custo?: number | null; data_entrega_prevista?: string | null
  observacao?: string; demanda?: number | null; itens: ItemDeCompraAvulsa[]
}) => apiClient.post<{ pedido_id: number }>('scm/pedidos/compra_avulsa/', body).then(r => r.data)
