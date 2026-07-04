import { erpClient, ERP_BASE } from '../erpClient'
import type {
  BaixaPayload, ContaPagar, ContaPagarFiltros, ContaPagarPayload,
  GerarLoteRemessaPayload, LoteRemessa, PaginatedResponse,
} from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?status=&fornecedor=` para o DRF. */
function cleanParams(filtros: ContaPagarFiltros): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export async function fetchContasAPagar(filtros: ContaPagarFiltros = {}): Promise<PaginatedResponse<ContaPagar>> {
  const { data } = await erpClient.get<PaginatedResponse<ContaPagar>>(`${ERP_BASE}contas-a-pagar/`, {
    params: cleanParams(filtros),
  })
  return data
}

export async function fetchContaAPagar(id: number): Promise<ContaPagar> {
  const { data } = await erpClient.get<ContaPagar>(`${ERP_BASE}contas-a-pagar/${id}/`)
  return data
}

export async function createContaAPagar(payload: ContaPagarPayload): Promise<ContaPagar> {
  const { data } = await erpClient.post<ContaPagar>(`${ERP_BASE}contas-a-pagar/`, payload)
  return data
}

export async function updateContaAPagar(id: number, payload: ContaPagarPayload): Promise<ContaPagar> {
  const { data } = await erpClient.put<ContaPagar>(`${ERP_BASE}contas-a-pagar/${id}/`, payload)
  return data
}

/** Baixa manual (total ou parcial) — único caminho de quitação, espelhado pelo futuro webhook do Asaas (D.1.2). */
export async function darBaixaContaAPagar(id: number, payload: BaixaPayload): Promise<ContaPagar> {
  const { data } = await erpClient.post<ContaPagar>(`${ERP_BASE}contas-a-pagar/${id}/dar-baixa/`, payload)
  return data
}

/** Registra um lote de remessa bancária agrupando títulos selecionados (sem gerar o arquivo CNAB). */
export async function gerarLoteRemessa(payload: GerarLoteRemessaPayload): Promise<LoteRemessa> {
  const { data } = await erpClient.post<LoteRemessa>(`${ERP_BASE}contas-a-pagar/gerar-lote-remessa/`, payload)
  return data
}
