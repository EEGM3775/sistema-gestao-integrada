/**
 * IE.0c — o cliente do motor de importação/exportação.
 *
 * **Um conjunto de funções para todo módulo.** Nada aqui conhece domínio: o
 * `recurso` é uma string que o backend publica em `/api/impexp/recursos/`, e o
 * que a tela sabe do formulário sai da própria declaração (colunas, formatos,
 * campos de destino). Módulo novo não escreve API nova — é o espelho exato do
 * desenho do backend (planta §11.1).
 */
import apiClient from '@/api/apiClient'

export type SituacaoLinha = 'nova' | 'duplicada' | 'invalida'
export type StatusImportacao =
  | 'lendo' | 'conferindo' | 'aplicada' | 'descartada' | 'desfeita' | 'erro'
export type StatusExportacao = 'pronta' | 'gerando' | 'erro'

export interface ColunaRecurso {
  campo: string
  rotulo: string
  tipo: string
  obrigatoria: boolean
  exemplo: string
}

export interface RecursoImpExp {
  id: string
  rotulo: string
  modulo: string
  exporta: boolean
  importa: boolean
  desfazivel: boolean
  chave: string
  formatos_saida: string[]
  formatos_entrada: string[]
  contexto_requerido: string[]
  colunas: ColunaRecurso[]
}

export interface ResumoImportacao {
  importacao_id: number
  recurso: string
  arquivo: string
  status: StatusImportacao
  status_nome: string
  mensagem: string
  contexto: Record<string, unknown>
  assincrona: boolean
  processadas: number
  /** 0–100. No caminho síncrono nasce em 100. */
  progresso: number
  total: number
  aplicadas: number
  novas: number
  duplicadas: number
  invalidas: number
  aceitas: number
  /**
   * R4 no caminho de job: o cabeçalho não casou e o lote está **esperando** o
   * de-para, com o arquivo preservado. Não é um erro terminal — é um passo.
   */
  aguarda_de_para: boolean
  cabecalhos_vistos: string[][]
  obrigatorias: string[]
  colunas_do_recurso: { campo: string; rotulo: string; obrigatoria: boolean }[]
}

export interface LinhaConferencia {
  linha_id: number
  numero: number
  chave: string
  valores: Record<string, string | number | boolean | null>
  situacao: SituacaoLinha
  motivo: string
  aceita: boolean
  bruto: (string | null)[]
}

export interface DetalheImportacao extends ResumoImportacao {
  linhas: LinhaConferencia[]
}

export interface ResumoExportacao {
  exportacao_id: number
  recurso: string
  formato: string
  status: StatusExportacao
  status_nome: string
  mensagem: string
  linhas: number
  baixavel: boolean
  expira_em: string | null
}

/** A resposta 422 da R4: o motor não adivinha cabeçalho, mostra o que viu. */
export interface PedidoDeDePara {
  code: 'colunas_nao_reconhecidas'
  detail: string
  cabecalhos_vistos: string[][]
  obrigatorias: string[]
  colunas: { campo: string; rotulo: string; obrigatoria: boolean }[]
}

export interface MapaSalvo {
  mapa_id: number
  recurso: string
  nome: string
  mapa: Record<string, number>
  delimitador: string
  criado_por: string
  criado_em: string
}

export const listarRecursos = async (): Promise<RecursoImpExp[]> =>
  (await apiClient.get<{ recursos: RecursoImpExp[] }>('impexp/recursos/')).data.recursos

// ---------------------------------------------------------------------------
// Exportação
// ---------------------------------------------------------------------------

/**
 * Baixa o recorte da tela (R7) ou devolve o lote quando o motor decidiu por job.
 *
 * `responseType: 'blob'` com **202 possível** é o detalhe que exige cuidado: o
 * corpo do 202 é JSON, mas o axios já o entregou como Blob, então ele é lido de
 * volta com `.text()`. Pedir JSON e converter no outro caminho seria pior —
 * arquivo binário passando por parse de texto corrompe silenciosamente.
 */
export async function exportar(
  recurso: string,
  params: Record<string, string | number | undefined> = {},
): Promise<{ tipo: 'arquivo' } | { tipo: 'job'; lote: ResumoExportacao }> {
  const limpos = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== ''),
  )
  const resposta = await apiClient.get(`impexp/${recurso}/exportar/`, {
    params: limpos,
    responseType: 'blob',
  })
  if (resposta.status === 202) {
    const texto = await (resposta.data as Blob).text()
    return { tipo: 'job', lote: JSON.parse(texto) as ResumoExportacao }
  }
  baixarBlob(resposta.data as Blob, nomeDoCabecalho(resposta.headers) || `${recurso}.arquivo`)
  return { tipo: 'arquivo' }
}

export const consultarExportacao = async (id: number): Promise<ResumoExportacao> =>
  (await apiClient.get<ResumoExportacao>(`impexp/exportacoes/${id}/`)).data

export async function baixarExportacao(id: number, nome: string) {
  const resposta = await apiClient.get(`impexp/exportacoes/${id}/`, {
    params: { baixar: 1 },
    responseType: 'blob',
  })
  baixarBlob(resposta.data as Blob, nomeDoCabecalho(resposta.headers) || nome)
}

export async function baixarModelo(recurso: string) {
  const resposta = await apiClient.get(`impexp/${recurso}/modelo/`, { responseType: 'blob' })
  baixarBlob(resposta.data as Blob, nomeDoCabecalho(resposta.headers) || 'modelo.xlsx')
}

export async function baixarRecusadas(importacaoId: number) {
  const resposta = await apiClient.get(`impexp/importacoes/${importacaoId}/recusadas/`, {
    responseType: 'blob',
  })
  baixarBlob(resposta.data as Blob, `recusadas-${importacaoId}.xlsx`)
}

// ---------------------------------------------------------------------------
// Importação — R1: preparar, conferir, decidir
// ---------------------------------------------------------------------------

export interface PedidoImportacao {
  recurso: string
  arquivo: File
  contexto?: Record<string, unknown>
  dePara?: Record<string, number>
  mapa?: number
  delimitador?: string
}

export async function importar(pedido: PedidoImportacao): Promise<ResumoImportacao> {
  const corpo = new FormData()
  corpo.append('arquivo', pedido.arquivo)
  if (pedido.contexto) corpo.append('contexto', JSON.stringify(pedido.contexto))
  if (pedido.dePara) corpo.append('de_para', JSON.stringify(pedido.dePara))
  if (pedido.mapa) corpo.append('mapa', String(pedido.mapa))
  if (pedido.delimitador) corpo.append('delimitador', pedido.delimitador)
  const { data } = await apiClient.post<ResumoImportacao>(
    `impexp/${pedido.recurso}/importar/`, corpo,
  )
  return data
}

export interface LoteHistorico extends ResumoImportacao {
  criada_em: string
  decidida_em: string | null
  usuario_nome: string
  /** R6 — só o último lote aplicado se desfaz. */
  pode_desfazer: boolean
}

export const listarImportacoes = async (recurso: string): Promise<LoteHistorico[]> =>
  (await apiClient.get<{ importacoes: LoteHistorico[] }>(
    `impexp/${recurso}/importacoes/`,
  )).data.importacoes

export const consultarImportacao = async (
  id: number, params: Record<string, string | number> = {},
): Promise<DetalheImportacao> =>
  (await apiClient.get<DetalheImportacao>(`impexp/importacoes/${id}/`, { params })).data

export const marcarLinhas = async (id: number, aceitar: boolean, linhas?: number[]) =>
  (await apiClient.post<{ linhas_marcadas: number }>(
    `impexp/importacoes/${id}/marcar/`, { aceitar, linhas },
  )).data

export const aplicarImportacao = async (id: number): Promise<ResumoImportacao> =>
  (await apiClient.post<ResumoImportacao>(`impexp/importacoes/${id}/aplicar/`)).data

export const descartarImportacao = async (id: number): Promise<ResumoImportacao> =>
  (await apiClient.post<ResumoImportacao>(`impexp/importacoes/${id}/descartar/`)).data

export const desfazerImportacao = async (id: number): Promise<ResumoImportacao> =>
  (await apiClient.post<ResumoImportacao>(`impexp/importacoes/${id}/desfazer/`)).data

/** R4 — relê o **mesmo arquivo** guardado, agora com o de-para na mão. */
export const remapearImportacao = async (
  id: number, dePara: Record<string, number>,
): Promise<ResumoImportacao> =>
  (await apiClient.post<ResumoImportacao>(
    `impexp/importacoes/${id}/remapear/`, { de_para: dePara },
  )).data

// ---------------------------------------------------------------------------
// De-para salvável (R4)
// ---------------------------------------------------------------------------

export const listarMapas = async (recurso: string): Promise<MapaSalvo[]> =>
  (await apiClient.get<{ mapas: MapaSalvo[] }>(`impexp/${recurso}/mapas/`)).data.mapas

export const salvarMapa = async (
  recurso: string, nome: string, mapa: Record<string, number>, delimitador = '',
): Promise<MapaSalvo> =>
  (await apiClient.post<MapaSalvo>(`impexp/${recurso}/mapas/`, { nome, mapa, delimitador })).data

export const excluirMapa = async (id: number) => {
  await apiClient.delete(`impexp/mapas/${id}/`)
}

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------

function nomeDoCabecalho(headers: unknown): string {
  const bruto = (headers as Record<string, string> | undefined)?.['content-disposition'] ?? ''
  return decodeURIComponent(/filename="?([^"]+)"?/.exec(bruto)?.[1] ?? '')
}

function baixarBlob(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = nome
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Sem o revoke, cada exportação numa sessão longa deixa o arquivo inteiro
  // retido em memória até o refresh da aba.
  URL.revokeObjectURL(url)
}
