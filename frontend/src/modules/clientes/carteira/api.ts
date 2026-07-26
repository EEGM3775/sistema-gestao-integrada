import apiClient from '@/api/apiClient'
import type {
  FinanceiroCliente, FiltrosCarteira, ObraResposta, OpcoesCarteira,
  PaginaCarteira, RespostaGrupos, Visao,
} from './types'

/** Só o que tem valor vira query param — chave vazia polui a URL e a cache. */
function limpar(filtros: FiltrosCarteira): Record<string, string> {
  return Object.fromEntries(
    Object.entries(filtros).filter(([, v]) => v !== undefined && v !== ''),
  ) as Record<string, string>
}

export async function buscarCarteira(params: {
  visao: Visao
  filtros: FiltrosCarteira
  ordenar?: string
  page: number
  pageSize?: number
}): Promise<PaginaCarteira> {
  const { data } = await apiClient.get<PaginaCarteira>('clientes/carteira/', {
    params: {
      visao: params.visao,
      ...limpar(params.filtros),
      ...(params.ordenar ? { ordenar: params.ordenar } : {}),
      page: params.page,
      page_size: params.pageSize ?? 100,
    },
  })
  return data
}

export async function buscarGrupos(params: {
  visao: Visao
  filtros: FiltrosCarteira
  niveis: string[]
}): Promise<RespostaGrupos> {
  const { data } = await apiClient.get<RespostaGrupos>('clientes/carteira/grupos/', {
    params: { visao: params.visao, ...limpar(params.filtros), por: params.niveis.join(',') },
  })
  return data
}

export async function buscarOpcoes(): Promise<OpcoesCarteira> {
  const { data } = await apiClient.get<OpcoesCarteira>('clientes/carteira/opcoes/')
  return data
}

export async function buscarFinanceiroCliente(clienteId: number): Promise<FinanceiroCliente> {
  const { data } = await apiClient.get<FinanceiroCliente>(`clientes/${clienteId}/financeiro/`)
  return data
}

export async function buscarObraCliente(clienteId: number): Promise<ObraResposta> {
  const { data } = await apiClient.get<ObraResposta>(`clientes/${clienteId}/obra/`)
  return data
}
