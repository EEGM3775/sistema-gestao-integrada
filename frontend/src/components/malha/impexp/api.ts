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
  /**
   * R19 — a célula abre na conferência, corrigindo o palpite sem reenviar o
   * arquivo. Quem decide é o **recurso**, não a tela: sem esta declaração o
   * wizard voltaria a um `if recurso === '...'` escrito à mão.
   */
  editavel?: boolean
  /** Aceita mais de um valor (guardados separados por vírgula). */
  multipla?: boolean
  /** A allowlist da coluna. `null`/ausente = texto livre. `cor` é opcional. */
  opcoes?: { valor: string; rotulo: string; cor?: string }[] | null
}

/**
 * IE.3 — as duas naturezas de entrada, e é ela que decide o **gesto** da tela.
 *
 * `tabela` abre o seletor de planilha e o wizard de de-para; `arquivo` abre o
 * seletor de PASTA e confere uma lista de binários. O backend publica isto no
 * catálogo justamente para o frontend não voltar ao `if recurso === '…'` escrito
 * à mão — ver `Recurso.descrever()`.
 */
export type NaturezaRecurso = 'tabela' | 'arquivo'

export interface RecursoImpExp {
  id: string
  rotulo: string
  modulo: string
  exporta: boolean
  /** Saída de binário que já existe (o acervo), distinta do `exporta` tabular. */
  entrega: boolean
  importa: boolean
  desfazivel: boolean
  chave: string
  natureza: NaturezaRecurso
  formatos_saida: string[]
  formatos_entrada: string[]
  /** O que ESTE destino recebe quando a natureza é `arquivo`. */
  formatos_arquivo: string[]
  /**
   * D83 — o teto **deste destino** por formato, em MB, que é o que a porta dele
   * vai aplicar. Só vem em recurso de natureza `arquivo`.
   *
   * Existe porque o teto de formato de arquivo não é do plano nem do formato:
   * é do recurso (`Recurso.teto_mb_do_formato`). O `limites.formatos[].max_mb`
   * do catálogo global publica o número da **planilha** — 25 MB no
   * `profissional` — e a tela que acreditasse nele recusaria sozinha um DWG de
   * 64,9 MB que a porta aceita até 150. Preferir este campo, sempre que existir.
   */
  tetos_mb?: Record<string, number>
  contexto_requerido: string[]
  colunas: ColunaRecurso[]
}

/** O teto declarado ANTES do envio (parte 3 do método gov.br — ver `limites.py`). */
export interface FormatoDeclarado {
  codigo: string
  rotulo: string
  extensoes: string[]
  natureza: NaturezaRecurso
  max_mb: number
}

export interface LimitesDoPlano {
  max_mb: number
  formatos: FormatoDeclarado[]
  plano: string
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
   * Inválidas + já existentes. **Tudo ou nada** (14/10/2026): com uma só, o
   * lote não se aplica — a tela trava o Confirmar e oferece as recusadas.
   */
  travadas: number
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

export interface CatalogoImpExp {
  recursos: RecursoImpExp[]
  limites: LimitesDoPlano
}

export const listarCatalogo = async (): Promise<CatalogoImpExp> =>
  (await apiClient.get<CatalogoImpExp>('impexp/recursos/')).data

export const listarRecursos = async (): Promise<RecursoImpExp[]> =>
  (await listarCatalogo()).recursos

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

/**
 * IE.3 — a porta de LOTE de arquivo: N binários, uma decisão.
 *
 * **`caminhos` viaja em paralelo a `arquivos`, e não dentro do nome.** É o
 * caminho relativo na pasta — o `webkitRelativePath` que o navegador entrega ao
 * escolher um diretório — que carrega a taxonomia (disciplina, código, revisão)
 * de um acervo histórico; o nome sozinho faria a plataforma adivinhar pior do
 * que ela sabe. Embuti-lo no `filename` não é opção: nome com `/` é recusado
 * pelo storage do Django.
 */
export async function importarArquivos(pedido: {
  recurso: string
  arquivos: File[]
  contexto?: Record<string, unknown>
  /** Progresso de rede da remessa, em 0–100. */
  onProgresso?: (pct: number) => void
}): Promise<ResumoImportacao> {
  const corpo = new FormData()
  for (const arquivo of pedido.arquivos) {
    corpo.append('arquivos', arquivo)
    // `webkitRelativePath` só existe quando a escolha veio de uma pasta; com
    // arquivos soltos o nome é o caminho, e o backend faz o mesmo fallback.
    corpo.append('caminhos', arquivoComCaminho(arquivo))
  }
  if (pedido.contexto) corpo.append('contexto', JSON.stringify(pedido.contexto))
  const { data } = await apiClient.post<ResumoImportacao>(
    `impexp/${pedido.recurso}/importar-arquivos/`, corpo,
    {
      onUploadProgress: evento => {
        if (!pedido.onProgresso || !evento.total) return
        pedido.onProgresso(Math.round((evento.loaded / evento.total) * 100))
      },
    },
  )
  return data
}

export const arquivoComCaminho = (arquivo: File): string =>
  (arquivo as File & { webkitRelativePath?: string }).webkitRelativePath || arquivo.name

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

/**
 * R19 — corrige o palpite de colunas `editavel`, numa linha ou em várias.
 *
 * `linhas` ausente = todas as da importação, que é o gesto "aplicar a todos".
 * Corrigir **não** confirma o lote: os dois continuam sendo atos separados.
 */
export const corrigirLinhas = async (
  id: number, valores: Record<string, string>, linhas?: number[],
) =>
  (await apiClient.post<{ linhas_corrigidas: number }>(
    `impexp/importacoes/${id}/corrigir/`, { valores, linhas },
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
