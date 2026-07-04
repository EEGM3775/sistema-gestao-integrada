import { erpClient, ERP_BASE } from '../erpClient'
import type {
  BaixaPayload, ContaReceber, ContaReceberFiltros, ContaReceberPayload,
  EmitirNfPayload, PaginatedResponse,
} from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?status=&cliente=` para o DRF. */
function cleanParams(filtros: ContaReceberFiltros): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export async function fetchContasAReceber(filtros: ContaReceberFiltros = {}): Promise<PaginatedResponse<ContaReceber>> {
  const { data } = await erpClient.get<PaginatedResponse<ContaReceber>>(`${ERP_BASE}contas-a-receber/`, {
    params: cleanParams(filtros),
  })
  return data
}

export async function fetchContaAReceber(id: number): Promise<ContaReceber> {
  const { data } = await erpClient.get<ContaReceber>(`${ERP_BASE}contas-a-receber/${id}/`)
  return data
}

export async function createContaAReceber(payload: ContaReceberPayload): Promise<ContaReceber> {
  const { data } = await erpClient.post<ContaReceber>(`${ERP_BASE}contas-a-receber/`, payload)
  return data
}

export async function updateContaAReceber(id: number, payload: ContaReceberPayload): Promise<ContaReceber> {
  const { data } = await erpClient.put<ContaReceber>(`${ERP_BASE}contas-a-receber/${id}/`, payload)
  return data
}

/** Baixa manual (total ou parcial) — único caminho de quitação, espelhado pelo futuro webhook do Asaas (D.1.2). */
export async function darBaixaContaAReceber(id: number, payload: BaixaPayload): Promise<ContaReceber> {
  const { data } = await erpClient.post<ContaReceber>(`${ERP_BASE}contas-a-receber/${id}/dar-baixa/`, payload)
  return data
}

export async function emitirNotaFiscalServico(id: number, payload: EmitirNfPayload = {}): Promise<unknown> {
  const { data } = await erpClient.post(`${ERP_BASE}contas-a-receber/${id}/emitir-nfse/`, payload)
  return data
}

export async function emitirNotaFiscalProduto(id: number, payload: EmitirNfPayload = {}): Promise<unknown> {
  const { data } = await erpClient.post(`${ERP_BASE}contas-a-receber/${id}/emitir-nfe/`, payload)
  return data
}
