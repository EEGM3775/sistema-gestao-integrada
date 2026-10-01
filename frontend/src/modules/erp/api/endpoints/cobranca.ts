import { erpClient, ERP_BASE } from '../erpClient'
import type {
  AndamentoLote, BancoCnab, CarteiraCobranca, ContaPagar, ContaReceber, PreviaCobranca, PreviaLote,
  PreviaLoteNfse, RemessaCnab, ResultadoLoteNfse, RetornoCnab,
} from '../../types'

/** Itens 52/55/56/57 — prévia e emissão de boleto, lote, estorno e CNAB. */

export async function fetchPreviaCobranca(contaId: number, vencimento?: string): Promise<PreviaCobranca> {
  const { data } = await erpClient.get<PreviaCobranca>(`${ERP_BASE}contas-a-receber/${contaId}/previa-cobranca/`, {
    params: vencimento ? { vencimento } : {},
  })
  return data
}

export async function gerarCobranca(contaId: number, vencimento?: string): Promise<{ detail: string }> {
  const { data } = await erpClient.post<{ detail: string }>(
    `${ERP_BASE}contas-a-receber/${contaId}/gerar-cobranca/`, vencimento ? { vencimento } : {},
  )
  return data
}

export async function estornarBaixaReceber(contaId: number, motivo: string): Promise<ContaReceber> {
  const { data } = await erpClient.post<ContaReceber>(`${ERP_BASE}contas-a-receber/${contaId}/estornar-baixa/`, { motivo })
  return data
}

export async function estornarBaixaPagar(contaId: number, motivo: string): Promise<ContaPagar> {
  const { data } = await erpClient.post<ContaPagar>(`${ERP_BASE}contas-a-pagar/${contaId}/estornar-baixa/`, { motivo })
  return data
}

/**
 * A escolha de contas do lote: ids marcados, ou "todas do filtro" com os filtros
 * da grade na query — menos as que a pessoa desmarcou depois (`excluir_ids`).
 */
export interface EscolhaDoLote {
  ids?: number[]
  todos_do_filtro?: boolean
  excluir_ids?: number[]
  filtros?: Record<string, string | number | undefined>
  vencimento_segunda_via?: string
}

function corpoEQuery(e: EscolhaDoLote) {
  const params: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(e.filtros ?? {})) if (v !== undefined && v !== '') params[k] = v
  const corpo: Record<string, unknown> = { vencimento_segunda_via: e.vencimento_segunda_via || undefined }
  if (e.todos_do_filtro) {
    corpo.todos_do_filtro = true
    if (e.excluir_ids?.length) corpo.excluir_ids = e.excluir_ids
  } else corpo.ids = e.ids
  return { corpo, params: e.todos_do_filtro ? params : {} }
}

export async function previaLote(e: EscolhaDoLote): Promise<PreviaLote> {
  const { corpo, params } = corpoEQuery(e)
  const { data } = await erpClient.post<PreviaLote>(`${ERP_BASE}contas-a-receber/previa-cobrancas-lote/`, corpo, { params })
  return data
}

export async function gerarLote(e: EscolhaDoLote, canal: 'asaas' | 'cnab', contaCobranca?: number): Promise<AndamentoLote> {
  const { corpo, params } = corpoEQuery(e)
  const { data } = await erpClient.post<AndamentoLote>(
    `${ERP_BASE}contas-a-receber/gerar-cobrancas-lote/`, { ...corpo, canal, conta_cobranca: contaCobranca }, { params },
  )
  return data
}

/** NFS-e em lote — a mesma escolha da grade, sozinha ou junto do lote de boletos. */
export async function previaLoteNfse(e: EscolhaDoLote): Promise<PreviaLoteNfse> {
  const { corpo, params } = corpoEQuery(e)
  const { data } = await erpClient.post<PreviaLoteNfse>(`${ERP_BASE}contas-a-receber/previa-lote-nfse/`, corpo, { params })
  return data
}

export async function emitirLoteNfse(e: EscolhaDoLote): Promise<ResultadoLoteNfse> {
  const { corpo, params } = corpoEQuery(e)
  const { data } = await erpClient.post<ResultadoLoteNfse>(`${ERP_BASE}contas-a-receber/emitir-lote-nfse/`, corpo, { params })
  return data
}

export async function fetchAndamentoLote(loteId: number): Promise<AndamentoLote> {
  const { data } = await erpClient.get<AndamentoLote>(`${ERP_BASE}lotes-cobranca/${loteId}/`)
  return data
}

/** O PDF e a miniatura vêm pelo backend (a CSP e o X-Frame-Options barram o Asaas embutido). */
export async function fetchPdfBoleto(boletoId: number): Promise<Blob> {
  const { data } = await erpClient.get<Blob>(`${ERP_BASE}boletos/${boletoId}/pdf/`, { responseType: 'blob' })
  return data
}

export async function fetchMiniaturaBoleto(boletoId: number): Promise<Blob> {
  const { data } = await erpClient.get<Blob>(`${ERP_BASE}boletos/${boletoId}/miniatura/`, { responseType: 'blob' })
  return data
}

export async function fetchCarteiras(): Promise<CarteiraCobranca[]> {
  const { data } = await erpClient.get<CarteiraCobranca[] | { results: CarteiraCobranca[] }>(`${ERP_BASE}carteiras-cobranca/`)
  return Array.isArray(data) ? data : data.results
}

export async function fetchBancosCnab(): Promise<BancoCnab[]> {
  const { data } = await erpClient.get<BancoCnab[]>(`${ERP_BASE}carteiras-cobranca/bancos/`)
  return data
}

export async function salvarCarteira(c: Partial<CarteiraCobranca>): Promise<CarteiraCobranca> {
  const url = c.conta_cobranca_id
    ? `${ERP_BASE}carteiras-cobranca/${c.conta_cobranca_id}/`
    : `${ERP_BASE}carteiras-cobranca/`
  const { data } = c.conta_cobranca_id
    ? await erpClient.patch<CarteiraCobranca>(url, c)
    : await erpClient.post<CarteiraCobranca>(url, c)
  return data
}

export async function fetchRemessas(): Promise<RemessaCnab[]> {
  const { data } = await erpClient.get<RemessaCnab[] | { results: RemessaCnab[] }>(`${ERP_BASE}remessas-cnab/`)
  return Array.isArray(data) ? data : data.results
}

export async function baixarRemessa(remessa: RemessaCnab): Promise<void> {
  const { data } = await erpClient.get<Blob>(`${ERP_BASE}remessas-cnab/${remessa.remessa_id}/arquivo/`, { responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = remessa.nome_arquivo
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function fetchRetornos(): Promise<RetornoCnab[]> {
  const { data } = await erpClient.get<RetornoCnab[] | { results: RetornoCnab[] }>(`${ERP_BASE}retornos-cnab/`)
  return Array.isArray(data) ? data : data.results
}

export async function enviarRetorno(contaCobranca: number, arquivo: File): Promise<RetornoCnab> {
  const form = new FormData()
  form.append('conta_cobranca', String(contaCobranca))
  form.append('arquivo', arquivo)
  const { data } = await erpClient.post<RetornoCnab>(`${ERP_BASE}retornos-cnab/enviar/`, form)
  return data
}
