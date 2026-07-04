import { erpClient, ERP_BASE } from '../erpClient'
import type { Boleto, BoletoFiltros, PaginatedResponse } from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?status=&conta_receber=` para o DRF. */
function cleanParams(filtros: BoletoFiltros): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

export async function fetchBoletos(filtros: BoletoFiltros = {}): Promise<PaginatedResponse<Boleto>> {
  const { data } = await erpClient.get<PaginatedResponse<Boleto>>(`${ERP_BASE}boletos/`, {
    params: cleanParams(filtros),
  })
  return data
}

export async function fetchBoleto(id: number): Promise<Boleto> {
  const { data } = await erpClient.get<Boleto>(`${ERP_BASE}boletos/${id}/`)
  return data
}

/** Aciona `ContaReceberViewSet.gerar_cobranca` — enfileira `funcoescobrancas.tasks.criar_cobranca` (D.1.2). */
export async function gerarCobrancaContaAReceber(contaReceberId: number): Promise<{ detail: string }> {
  const { data } = await erpClient.post<{ detail: string }>(
    `${ERP_BASE}contas-a-receber/${contaReceberId}/gerar-cobranca/`,
  )
  return data
}
