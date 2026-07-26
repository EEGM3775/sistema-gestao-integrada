import { erpClient, ERP_BASE } from '../erpClient'
import type {
  DocumentoGateway,
  NotaFiscalRecebida, NotaFiscalRecebidaFiltros,
  NotaFiscalServico, NotaFiscalServicoFiltros, PaginatedResponse,
} from '../../types'

/** Remove chaves vazias — o axios não deve mandar `?status=&fornecedor=` para o DRF.
 *
 * Genérico porque este arquivo serve DOIS tipos de filtro (NFS-e emitida e NF
 * recebida). `Record<string, unknown>` não aceita interface sem index signature,
 * então os dois call sites falhavam no `tsc`. */
function cleanParams<T extends object>(filtros: T): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v as string | number
  }
  return out
}

/** NFS-e emitidas (model `NotaFiscalServico`) — as abas separam emitidas × canceladas via `status`/`excluir_status`. */
export async function fetchNotasFiscaisServico(
  filtros: NotaFiscalServicoFiltros = {},
): Promise<PaginatedResponse<NotaFiscalServico>> {
  const { data } = await erpClient.get<PaginatedResponse<NotaFiscalServico>>(
    `${ERP_BASE}notas-fiscais-servico/`, { params: cleanParams(filtros) },
  )
  return data
}

/** NF recebidas de fornecedor (model `NotaFiscal`). */
export async function fetchNotasFiscaisRecebidas(
  filtros: NotaFiscalRecebidaFiltros = {},
): Promise<PaginatedResponse<NotaFiscalRecebida>> {
  const { data } = await erpClient.get<PaginatedResponse<NotaFiscalRecebida>>(
    `${ERP_BASE}notas-fiscais/`, { params: cleanParams(filtros) },
  )
  return data
}

/** Reconsulta o status da NFS-e na NFE.io (enfileira a task; a NF atualiza quando responder). */
export async function consultarStatusNfse(id: number): Promise<{ message: string }> {
  const { data } = await erpClient.post<{ message: string }>(`${ERP_BASE}nf/${id}/consultar/`)
  return data
}

/** Cancela a NFS-e na NFE.io (enfileira a task; exige `erp.nf.cancelar`). */
export async function cancelarNfse(id: number): Promise<{ message: string }> {
  const { data } = await erpClient.post<{ message: string }>(`${ERP_BASE}notas-fiscais-servico/${id}/cancelar/`)
  return data
}

/** Verifica a NFS-e AO VIVO na NFE.io antes de abrir o documento (`NotaFiscalServicoViewSet.documento`). */
export async function verificarDocumentoNfse(id: number): Promise<DocumentoGateway> {
  const { data } = await erpClient.get<DocumentoGateway>(`${ERP_BASE}notas-fiscais-servico/${id}/documento/`)
  return data
}
