import apiClient from '@/api/apiClient'
import type {
  Paginated, SilDashboard, Item, LocalEstoque, SaldoEstoque, MovimentacaoEstoque, Lote,
  Requisicao, ItemRequisicao, Transferencia, ItemTransferencia, Devolucao, ItemDevolucao,
  Inventario, ItemInventario, ObraOpt, FornecedorOpt, FuncionarioOpt, EtapaOpt,
  EntregaEPI, Ferramenta, EmprestimoFerramenta, CurvaABC, AplicadoLinha,
} from '../types'

// Cliente REST do SIL sobre /api/sil/ (apiClient já injeta auth + refresh).
type Params = Record<string, unknown>

function resource<T, P>(base: string, path: string) {
  return {
    listPaged: async (params: Params = {}) => (await apiClient.get<Paginated<T>>(`${base}/${path}/`, { params })).data,
    listAll: async (params: Params = {}) => {
      // Endpoints com paginação desligada (itens-*) devolvem array puro.
      const { data } = await apiClient.get<Paginated<T> | T[]>(`${base}/${path}/`, { params: { ...params, page_size: 500 } })
      return Array.isArray(data) ? data : data.results
    },
    get: async (id: number) => (await apiClient.get<T>(`${base}/${path}/${id}/`)).data,
    create: async (payload: P) => (await apiClient.post<T>(`${base}/${path}/`, payload)).data,
    update: async (id: number, payload: Partial<P>) => (await apiClient.patch<T>(`${base}/${path}/${id}/`, payload)).data,
    remove: async (id: number) => { await apiClient.delete(`${base}/${path}/${id}/`) },
  }
}
export type Resource<T, P> = ReturnType<typeof resource<T, P>>

export const itens = resource<Item, unknown>('catalogo', 'itens')
export const locais = resource<LocalEstoque, unknown>('sil', 'locais')
export const saldos = resource<SaldoEstoque, unknown>('sil', 'saldos')
export const movimentacoes = resource<MovimentacaoEstoque, unknown>('sil', 'movimentacoes')
export const lotes = resource<Lote, unknown>('sil', 'lotes')
export const requisicoes = resource<Requisicao, unknown>('sil', 'requisicoes')
export const itensRequisicao = resource<ItemRequisicao, unknown>('sil', 'itens-requisicao')
export const transferencias = resource<Transferencia, unknown>('sil', 'transferencias')
export const itensTransferencia = resource<ItemTransferencia, unknown>('sil', 'itens-transferencia')
export const devolucoes = resource<Devolucao, unknown>('sil', 'devolucoes')
export const itensDevolucao = resource<ItemDevolucao, unknown>('sil', 'itens-devolucao')
export const inventarios = resource<Inventario, unknown>('sil', 'inventarios')
export const itensInventario = resource<ItemInventario, unknown>('sil', 'itens-inventario')
export const entregasEpi = resource<EntregaEPI, unknown>('sil', 'entregas-epi')
export const ferramentas = resource<Ferramenta, unknown>('sil', 'ferramentas')
export const emprestimos = resource<EmprestimoFerramenta, unknown>('sil', 'emprestimos')

export async function getSilDashboard() {
  const { data } = await apiClient.get<SilDashboard>('sil/dashboard/')
  return data
}
export async function getCurvaABC() {
  const { data } = await apiClient.get<CurvaABC>('sil/curva-abc/')
  return data
}
export async function getAplicado(obra?: number) {
  const { data } = await apiClient.get<AplicadoLinha[]>('sil/aplicado/', { params: obra ? { obra } : {} })
  return data
}

// Opções para selects (cadastros-base — o almoxarife tem `.view`).
export async function listObras() {
  const { data } = await apiClient.get<Paginated<ObraOpt> | ObraOpt[]>('obras/', { params: { page_size: 200 } })
  return Array.isArray(data) ? data : data.results
}
export async function listFornecedores() {
  const { data } = await apiClient.get<Paginated<FornecedorOpt> | FornecedorOpt[]>('fornecedores/', { params: { page_size: 200 } })
  return Array.isArray(data) ? data : data.results
}
export async function listFuncionarios() {
  // Colaborador vem do RH (integração). 403 se o tenant não tiver RH → o front cai em texto livre.
  try {
    const { data } = await apiClient.get<Paginated<FuncionarioOpt> | FuncionarioOpt[]>('funcionarios/', { params: { page_size: 300 } })
    return Array.isArray(data) ? data : data.results
  } catch { return [] as FuncionarioOpt[] }
}
export async function listEtapas(obra: number) {
  const { data } = await apiClient.get<Paginated<EtapaOpt> | EtapaOpt[]>('etapas-obras/', { params: { obra, page_size: 200 } })
  return Array.isArray(data) ? data : data.results
}

// Verbos de domínio (POST) — o único caminho que altera saldo passa pelo backend.
export const registrarMov = (body: {
  item: number; local: number; tipo: string; quantidade: string; custo_unitario?: string
  obra?: number | null; etapa?: number | null; observacao?: string
}) => apiClient.post<MovimentacaoEstoque>('sil/movimentacoes/registrar/', body).then(r => r.data)
export const definirMinimo = (saldo: number, ponto_reposicao: string) =>
  apiClient.post(`sil/saldos/${saldo}/definir_minimo/`, { ponto_reposicao })
export const gerarDemanda = (saldo: number, quantidade?: string) =>
  apiClient.post<{ demanda_id: number; status: string; quantidade: string }>(`sil/saldos/${saldo}/gerar_demanda/`, quantidade ? { quantidade } : {}).then(r => r.data)
export const aprovarRequisicao = (id: number) => apiClient.post(`sil/requisicoes/${id}/aprovar/`)
export const atenderRequisicao = (id: number) => apiClient.post(`sil/requisicoes/${id}/atender/`)
export const executarTransferencia = (id: number) => apiClient.post(`sil/transferencias/${id}/executar/`)
export const executarDevolucao = (id: number) => apiClient.post(`sil/devolucoes/${id}/executar/`)
export const fecharInventario = (id: number) => apiClient.post(`sil/inventarios/${id}/fechar/`)
export const reabrirInventario = (id: number) => apiClient.post(`sil/inventarios/${id}/reabrir/`)
export const devolverEpi = (id: number) => apiClient.post(`sil/entregas-epi/${id}/devolver/`)
export const alterarEstadoFerramenta = (id: number, body: { estado: string; proxima_calibracao?: string | null; proxima_manutencao?: string | null }) =>
  apiClient.post(`sil/ferramentas/${id}/alterar_estado/`, body)
export const devolverEmprestimo = (id: number) => apiClient.post(`sil/emprestimos/${id}/devolver/`)
