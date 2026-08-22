import apiClient from '@/api/apiClient'
import type {
  Acervo,
  ComentarioMarcacao,
  Desenho,
  DisciplinaCatalogo,
  Documento,
  FilaDaConversao,
  Marcacao,
  Medicao,
  Paginado,
  Ponto,
  PontoDeVista,
  ResumoImportacaoBcf,
  Revisao,
  StatusPrancheta,
} from './types'

const base = '/prancheta'

export const carregarAcervo = (obra: number) =>
  apiClient.get<Acervo>(`${base}/acervo/`, { params: { obra } }).then((r) => r.data)

export const statusPrancheta = () =>
  apiClient.get<StatusPrancheta>(`${base}/status/`).then((r) => r.data)

export const listarDocumentos = (params?: Record<string, unknown>) =>
  apiClient.get<Paginado<Documento>>(`${base}/documentos/`, { params }).then((r) => r.data)

export const listarRevisoes = (documento: number) =>
  apiClient
    .get<Paginado<Revisao>>(`${base}/revisoes/`, { params: { documento, ordering: '-revisao' } })
    .then((r) => r.data)

/**
 * Histórico da **obra** — todas as revisões, da mais recente para trás.
 *
 * Filtra no servidor (`documento__obra`) e não no cliente: a listagem é
 * paginada, então peneirar aqui faria a tela dizer "sem histórico" sempre que a
 * primeira página não tivesse nenhuma revisão desta obra.
 */
export const listarHistoricoDaObra = (obra: number, pagina = 1) =>
  apiClient
    .get<Paginado<Revisao>>(`${base}/revisoes/`, {
      params: { documento__obra: obra, ordering: '-enviado_em', page: pagina },
    })
    .then((r) => r.data)

export const publicarRevisao = (id: number) =>
  apiClient.post<Revisao>(`${base}/revisoes/${id}/publicar/`).then((r) => r.data)

/**
 * Publica a revisão mais recente de cada documento **sem vigente** da obra.
 *
 * Existe porque o acervo histórico entra todo em rascunho e publicar prancha a
 * prancha não é fluxo — é 141 cliques. Não troca vigente por vigente: só alcança
 * documento que ainda não tem desenho valendo em campo.
 */
export const publicarPendentes = (obra: number) =>
  apiClient
    .post<{
      publicadas: number
      documentos: { documento: string; revisao: string }[]
      ignorados: { documento: string; motivo: string }[]
    }>(`${base}/revisoes/publicar-pendentes/`, { obra })
    .then((r) => r.data)

export const reprocessarRevisao = (id: number) =>
  apiClient
    .post<{ detail: string; agendadas: unknown[] }>(`${base}/revisoes/${id}/reprocessar/`)
    .then((r) => r.data)

export const criarDocumento = (dados: Partial<Documento>) =>
  apiClient.post<Documento>(`${base}/documentos/`, dados).then((r) => r.data)

// ---------------------------------------------------------------------------
// PRA.9b — o vocabulário de disciplinas é do cliente
// ---------------------------------------------------------------------------

/** Catálogo completo: as 13 embutidas **mais** as que esta empresa criou. */
export const listarDisciplinas = () =>
  apiClient.get<DisciplinaCatalogo[]>(`${base}/disciplinas/`).then((r) => r.data)

/** O `codigo` sai do nome no servidor — quem cria não precisa saber o que é slug. */
export const criarDisciplina = (dados: { nome: string; cor?: string; ordem?: number }) =>
  apiClient.post<DisciplinaCatalogo>(`${base}/disciplinas/`, dados).then((r) => r.data)

export const atualizarDisciplina = (id: number, dados: Partial<DisciplinaCatalogo>) =>
  apiClient.patch<DisciplinaCatalogo>(`${base}/disciplinas/${id}/`, dados).then((r) => r.data)

/** Apagar não toca em prancha: o documento guarda o código, e volta a exibi-lo cru. */
export const excluirDisciplina = (id: number) =>
  apiClient.delete(`${base}/disciplinas/${id}/`).then(() => undefined)

// **`enviarPrancha` e `adivinharDisciplinas` saíram na PRA.9d**, com o upload
// avulso que era o único cliente das duas. O acervo entra por um caminho só — o
// wizard de arquivos do `funcoesimpexp` —, e o palpite de disciplina que a
// segunda servia agora é feito no servidor, na montagem da linha de conferência
// (`impexp.dados_do_arquivo`). Não ficaram como no-op: função que ninguém chama é
// mais difícil de achar que um erro de compilação, e essa é a mesma lição que o
// D70 deixou ao apagar a `mediaUrl` em vez de a esvaziar.

/** Reclassifica a prancha — a lista inteira, principal primeiro. */
export const definirDisciplinasDoDocumento = (documento: number, codigos: string[]) =>
  apiClient
    .patch<Documento>(`${base}/documentos/${documento}/`, { codigos_disciplina: codigos })
    .then((r) => r.data)

/**
 * **Atualizar o arquivo** de uma prancha que já existe — a entrega seguinte.
 *
 * O rótulo não é digitado: sai do nome do arquivo quando ele traz um, e senão é o
 * seguinte ao maior que já existe. Nasce em rascunho como toda revisão — trocar o
 * desenho que o campo executa continua sendo `revisao.publicar`.
 */
export function atualizarPrancha(dados: {
  documento: number
  arquivo: File
  observacao?: string
}) {
  const corpo = new FormData()
  corpo.append('arquivo', dados.arquivo)
  if (dados.observacao) corpo.append('observacao', dados.observacao)
  return apiClient
    .post<Revisao>(`${base}/documentos/${dados.documento}/atualizar/`, corpo)
    .then((r) => r.data)
}

/** Upload é multipart: o arquivo é o corpo, e formato/tamanho/hash saem dele. */
export function enviarRevisao(dados: {
  documento: number
  revisao: string
  arquivo: File
  data_emissao?: string
  observacao?: string
}) {
  const corpo = new FormData()
  corpo.append('documento', String(dados.documento))
  corpo.append('revisao', dados.revisao)
  corpo.append('arquivo', dados.arquivo)
  if (dados.data_emissao) corpo.append('data_emissao', dados.data_emissao)
  if (dados.observacao) corpo.append('observacao', dados.observacao)
  return apiClient.post<Revisao>(`${base}/revisoes/`, corpo).then((r) => r.data)
}

/**
 * O download autenticado **subiu para `@/lib/arquivo` no D70**, quando RH,
 * cliente, obra, diário e ERP passaram a precisar exatamente do mesmo: o token
 * vive em memória, então nenhuma URL gateada pode ir num `<a href>`.
 *
 * Reexportado daqui porque as telas do módulo o importam por este caminho, e
 * trocar cinco imports para provar um ponto não melhora nada.
 */
export { baixarArquivo, baixarParaDisco } from '@/lib/arquivo'

async function salvarBlob(blob: Blob, nome: string) {
  const objeto = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objeto
  link.download = nome.replace(/[^\w.-]+/g, '_')
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objeto)
}

// ---------------------------------------------------------------------------
// PRA.3 — marcar e medir
// ---------------------------------------------------------------------------
export const listarMarcacoes = (params: Record<string, unknown>) =>
  apiClient.get<Paginado<Marcacao>>(`${base}/marcacoes/`, { params }).then((r) => r.data)

export const criarMarcacao = (dados: {
  revisao: number
  /** Em qual folha o pino foi fincado. `null` onde não há folha (PDF, 3D). */
  desenho?: number | null
  titulo: string
  descricao?: string
  tipo?: string
  prioridade?: string
  responsavel?: number | null
  responsavel_email?: string
  prazo?: string | null
  ancora?: Ponto
}) => apiClient.post<Marcacao>(`${base}/marcacoes/`, dados).then((r) => r.data)

export const atualizarMarcacao = (id: number, dados: Partial<Marcacao>) =>
  apiClient.patch<Marcacao>(`${base}/marcacoes/${id}/`, dados).then((r) => r.data)

export const comentarMarcacao = (id: number, texto: string) =>
  apiClient
    .post<ComentarioMarcacao>(`${base}/marcacoes/${id}/comentar/`, { texto })
    .then((r) => r.data)

/** Verbo de alçada — exige `prancheta.marcacao.resolver`, que o campo não tem. */
export const mudarSituacaoMarcacao = (id: number, situacao: string) =>
  apiClient
    .post<Marcacao>(`${base}/marcacoes/${id}/situacao/`, { situacao })
    .then((r) => r.data)

/**
 * Anexa o recorte da tela. O snapshot é **opcional por desenho**: a captura
 * acontece no navegador e falha em aparelho velho — e um ponto de vista sem
 * imagem ainda é válido no BCF. Bloquear a marcação por causa da foto perderia
 * o apontamento para salvar o enfeite.
 */
export function anexarPontoDeVista(id: number, snapshot: Blob | null) {
  const corpo = new FormData()
  if (snapshot) corpo.append('snapshot', snapshot, 'snapshot.png')
  return apiClient
    .post<PontoDeVista>(`${base}/marcacoes/${id}/ponto-de-vista/`, corpo)
    .then((r) => r.data)
}

export const criarMedicao = (dados: {
  revisao: number
  /** Em qual folha a medida foi tirada — é ela que define a régua aplicada. */
  desenho?: number | null
  tipo: 'distancia' | 'area'
  pontos: Ponto[]
  marcacao?: number | null
  rotulo?: string
}) => apiClient.post<Medicao>(`${base}/medicoes/`, dados).then((r) => r.data)

export const listarMedicoes = (revisao: number) =>
  apiClient
    .get<Paginado<Medicao>>(`${base}/medicoes/`, { params: { revisao } })
    .then((r) => r.data)

export const excluirMedicao = (id: number) =>
  apiClient.delete(`${base}/medicoes/${id}/`).then(() => undefined)

/**
 * Define a régua **de uma folha**. `distancia_real` é quanto medem os dois pontos.
 *
 * É por desenho e não por revisão porque as coordenadas são normalizadas pela
 * largura da folha: uma régua só descreveria no máximo uma delas, e em silêncio
 * para as outras.
 */
export const calibrarDesenho = (
  id: number,
  dados: { a: Ponto; b: Ponto; distancia_real: number; unidade?: string },
) => apiClient.post<Desenho>(`${base}/desenhos/${id}/calibrar/`, dados).then((r) => r.data)

/** Dá nome a uma folha. Nome vazio devolve o rótulo automático (`Desenho N`). */
export const renomearDesenho = (id: number, nome: string) =>
  apiClient.post<Desenho>(`${base}/desenhos/${id}/renomear/`, { nome }).then((r) => r.data)

/**
 * Exporta o `.bcfzip` com **os mesmos filtros da listagem** — o que a tela
 * mostra é o que o arquivo leva. Atrás da parede comercial do formato `bcf`
 * (402), não de permissão: marcar vem com o módulo, atravessar para o software
 * do projetista é o que o plano vende.
 */
export async function exportarBcf(params: Record<string, unknown>, nome: string) {
  const resposta = await apiClient.get(`${base}/marcacoes/bcf/`, {
    params,
    responseType: 'blob',
  })
  await salvarBlob(resposta.data as Blob, nome)
}

export function importarBcf(revisao: number, arquivo: File) {
  const corpo = new FormData()
  corpo.append('revisao', String(revisao))
  corpo.append('arquivo', arquivo)
  return apiClient
    .post<ResumoImportacaoBcf>(`${base}/marcacoes/importar-bcf/`, corpo)
    .then((r) => r.data)
}

/**
 * Sobe este arquivo na fila — **à frente só dos da própria empresa** (D98).
 *
 * A rota é do `nucleo` e não da Prancheta porque a frota é da plataforma: a
 * Prancheta é a primeira cliente, não a dona. Importação de acervo e ortofoto do
 * Maps chamarão exatamente isto quando entrarem na mesma fila.
 */
export const priorizarNaFila = (tarefaId: number) =>
  apiClient
    .post<FilaDaConversao>(`/api/frota/tarefas/${tarefaId}/priorizar/`)
    .then((r) => r.data)
