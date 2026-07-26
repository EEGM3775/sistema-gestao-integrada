import apiClient from '@/api/apiClient'
import type {
  ArvoreResposta, BancoPreco, BancoResumo, BaseReferencial, BaseResumo, CatalogoItem,
  ComponenteBancoPreco, ComponenteReferencia, ComposicaoBDI, ComposicaoReferenciaResposta,
  ControleLinha, ControleResposta, Cronograma, CurvaABC,
  CurvaS, CustoPorCategoria, EtapaOpt, InsumoReferencia, ItemAdotado,
  ItemBancoPreco, ItemOrcado,
  MemoriaCalculo, MemorialNBR, ObraOpt, Orcamento, Paginated, ParametroObra,
  ParcelaEtapa, PastaComposicao, PavimentoObra, PrecoReal, PreviaReprecificacao, Reprecificacao,
  ResultadoAdocaoLote, ResumoDuplicata, RevisaoOrcamento, StatusModulo,
  UnidadeAutonoma,
} from '../types'

type Params = Record<string, unknown>

function recurso<T, P>(caminho: string) {
  return {
    listar: async (params: Params = {}) =>
      (await apiClient.get<Paginated<T>>(`orcamento/${caminho}/`, { params })).data,
    todos: async (params: Params = {}) => {
      const { data } = await apiClient.get<Paginated<T> | T[]>(`orcamento/${caminho}/`, { params: { ...params, page_size: 500 } })
      return Array.isArray(data) ? data : data.results
    },
    obter: async (id: number) => (await apiClient.get<T>(`orcamento/${caminho}/${id}/`)).data,
    criar: async (payload: P) => (await apiClient.post<T>(`orcamento/${caminho}/`, payload)).data,
    atualizar: async (id: number, payload: Partial<P>) =>
      (await apiClient.patch<T>(`orcamento/${caminho}/${id}/`, payload)).data,
    remover: async (id: number) => { await apiClient.delete(`orcamento/${caminho}/${id}/`) },
  }
}
export type Recurso<T, P> = ReturnType<typeof recurso<T, P>>

export const orcamentos = recurso<Orcamento, Partial<Orcamento>>('orcamentos')
export const itens = recurso<ItemOrcado, Partial<ItemOrcado>>('itens')
export const revisoes = recurso<RevisaoOrcamento, Partial<RevisaoOrcamento>>('revisoes')
export const bdis = recurso<ComposicaoBDI, Partial<ComposicaoBDI>>('bdi')
export const parcelas = recurso<ParcelaEtapa, Partial<ParcelaEtapa>>('parcelas')
export const parametricos = recurso<ParametroObra, Partial<ParametroObra>>('parametricos')
export const pavimentos = recurso<PavimentoObra, Partial<PavimentoObra>>('pavimentos')
export const unidades = recurso<UnidadeAutonoma, Partial<UnidadeAutonoma>>('unidades')
export const memoriais = recurso<MemorialNBR, Partial<MemorialNBR>>('memoriais')
export const bases = recurso<BaseReferencial, never>('bases')
export const referencias = recurso<InsumoReferencia, never>('referencias')

export const getStatusModulo = async () =>
  (await apiClient.get<StatusModulo>('orcamento/status/')).data

export const getBasesResumo = async () =>
  (await apiClient.get<BaseResumo[]>('orcamento/bases-resumo/')).data

/** A view devolve `{composicao, componentes}`; a tela só lista os componentes. */
export const getComposicaoReferencia = async (referenciaId: number): Promise<ComponenteReferencia[]> => {
  const { data } = await apiClient.get<ComposicaoReferenciaResposta>(
    `orcamento/referencias/${referenciaId}/composicao/`,
  )
  return data?.componentes ?? []
}

export const adotarReferencia = async (referenciaId: number) =>
  (await apiClient.post<ItemAdotado & { tipo: string; componentes: number }>(
    `orcamento/referencias/${referenciaId}/adotar/`,
  )).data

export const adotarLote = async (referencias: number[]) =>
  (await apiClient.post<ResultadoAdocaoLote>('orcamento/referencias/adotar-lote/', { referencias })).data

export const getArvore = async (orcamentoId: number) =>
  (await apiClient.get<ArvoreResposta>(`orcamento/orcamentos/${orcamentoId}/arvore/`)).data

export const recalcular = async (orcamentoId: number) =>
  (await apiClient.post<Orcamento>(`orcamento/orcamentos/${orcamentoId}/recalcular/`)).data

export const aprovar = async (orcamentoId: number) =>
  (await apiClient.post<Orcamento>(`orcamento/orcamentos/${orcamentoId}/aprovar/`)).data

export const revisar = async (orcamentoId: number, body: { tipo: string; motivo: string }) =>
  (await apiClient.post<Orcamento>(`orcamento/orcamentos/${orcamentoId}/revisar/`, body)).data

export const getCurvaABC = async (orcamentoId: number) =>
  (await apiClient.get<CurvaABC>(`orcamento/orcamentos/${orcamentoId}/curva-abc/`)).data

export const getPorCategoria = async (orcamentoId: number) =>
  (await apiClient.get<CustoPorCategoria>(`orcamento/orcamentos/${orcamentoId}/por-categoria/`)).data

export const getCronograma = async (orcamentoId: number) =>
  (await apiClient.get<Cronograma>(`orcamento/orcamentos/${orcamentoId}/cronograma/`)).data

export const distribuirCronograma = async (
  orcamentoId: number, body: { inicio: string; fim: string; etapa?: number | null },
) => (await apiClient.post<Cronograma>(`orcamento/orcamentos/${orcamentoId}/distribuir-cronograma/`, body)).data

export const getCurvaS = async (orcamentoId: number) =>
  (await apiClient.get<CurvaS>(`orcamento/orcamentos/${orcamentoId}/curva-s/`)).data

export const criarItemDoCatalogo = async (body: {
  orcamento: number; item: number; quantidade: string
  pai?: number | null; etapa?: number | null; ordem?: number
}) => (await apiClient.post<ItemOrcado>('orcamento/itens/do-catalogo/', body)).data

export const explodirItem = async (itemOrcadoId: number) =>
  (await apiClient.post<MemoriaCalculo>(`orcamento/itens/${itemOrcadoId}/explodir/`)).data

export const getMemoria = async (itemOrcadoId: number) =>
  (await apiClient.get<MemoriaCalculo>(`orcamento/itens/${itemOrcadoId}/memoria/`)).data

export const getPrecoReal = async (itemOrcadoId: number) =>
  (await apiClient.get<PrecoReal>(`orcamento/itens/${itemOrcadoId}/preco-real/`)).data

export const aplicarPrecoReal = async (itemOrcadoId: number, origem: 'scm' | 'sil') =>
  (await apiClient.post<ItemOrcado>(`orcamento/itens/${itemOrcadoId}/aplicar-preco-real/`, { origem })).data

/** A view devolve `{obras, nota_realizado}`, não uma lista: desembrulha aqui e
 *  carimba a nota em cada linha (as telas consomem uma lista só). */
export const getControle = async (obra?: number): Promise<ControleLinha[]> => {
  const { data } = await apiClient.get<ControleResposta>('orcamento/controle/', {
    params: obra ? { obra } : {},
  })
  return (data?.obras ?? []).map(linha => ({ ...linha, nota_realizado: data.nota_realizado }))
}

export const getQuadrosNBR = async (obra: number) =>
  (await apiClient.get<Record<string, unknown>>('orcamento/nbr12721/', { params: { obra } })).data

export const compararParametrico = async (parametroId: number) =>
  (await apiClient.get<Record<string, unknown>>(`orcamento/parametricos/${parametroId}/comparar/`)).data

export async function listarObras() {
  const { data } = await apiClient.get<Paginated<ObraOpt> | ObraOpt[]>('obras/', { params: { page_size: 200 } })
  return Array.isArray(data) ? data : data.results
}

export async function listarEtapas(obra: number) {
  const { data } = await apiClient.get<Paginated<EtapaOpt> | EtapaOpt[]>('etapas-obras/', { params: { obra, page_size: 200 } })
  return Array.isArray(data) ? data : data.results
}

export async function buscarNoCatalogo(busca: string) {
  const { data } = await apiClient.get<Paginated<CatalogoItem> | CatalogoItem[]>('catalogo/itens/', {
    params: { search: busca, page_size: 40, ativo: true },
  })
  return Array.isArray(data) ? data : data.results
}

export async function criarItemNoCatalogo(payload: {
  codigo_interno: string; descricao: string; unidade: string; categoria: string; tipo: string
}) {
  const { data } = await apiClient.post<CatalogoItem>('catalogo/itens/', payload)
  return data
}

// --- ORC.5b ---

export const bancos = recurso<BancoPreco, Partial<BancoPreco>>('bancos')
export const pastas = recurso<PastaComposicao, Partial<PastaComposicao>>('pastas')
export const itensBanco = recurso<ItemBancoPreco, Partial<ItemBancoPreco>>('itens-banco')
export const componentesBanco = recurso<ComponenteBancoPreco, Partial<ComponenteBancoPreco>>('componentes-banco')
export const reprecificacoes = recurso<Reprecificacao, never>('reprecificacoes')

export const getBancosResumo = async () =>
  (await apiClient.get<BancoResumo[]>('orcamento/bancos/resumo/')).data

export const travarBanco = async (id: number) =>
  (await apiClient.post<BancoPreco>(`orcamento/bancos/${id}/travar/`)).data

export const destravarBanco = async (id: number) =>
  (await apiClient.post<BancoPreco>(`orcamento/bancos/${id}/destravar/`)).data

export const adotarDoBanco = async (bancoId: number, itens: number[]) =>
  (await apiClient.post<{ adotados: number[]; criados: number }>(
    `orcamento/bancos/${bancoId}/adotar-lote/`, { itens },
  )).data

export const copiarDaBasePublica = async (
  bancoId: number, referencias: number[], comComposicao = true,
) => (await apiClient.post<{ criados: number; total_itens: number }>(
  `orcamento/bancos/${bancoId}/copiar-da-base/`,
  { referencias, com_composicao: comComposicao },
)).data

export const getComposicaoBanco = async (itemId: number) =>
  (await apiClient.get<ComponenteBancoPreco[]>(`orcamento/itens-banco/${itemId}/composicao/`)).data

export const duplicarItemBanco = async (itemId: number, bancoDestino: number, codigo?: string) =>
  (await apiClient.post<ItemBancoPreco>(
    `orcamento/itens-banco/${itemId}/duplicar/`, { banco_destino: bancoDestino, codigo },
  )).data

// A importação de preço saiu daqui no **IE.1**: virou a declaração
// `orcamento.banco_preco` e roda pelo motor de plataforma. O cliente é
// `@/components/malha/impexp/api`, compartilhado com todo módulo.

export const duplicarOrcamento = async (
  id: number, body: { obra?: number | null; descricao?: string },
) => (await apiClient.post<ResumoDuplicata>(`orcamento/orcamentos/${id}/duplicar/`, body)).data

export const copiarItens = async (
  destinoId: number, body: { itens: number[]; pai?: number | null },
) => (await apiClient.post<{ copiadas: number; linhas_sem_etapa: number; valor_total: string }>(
  `orcamento/orcamentos/${destinoId}/copiar-itens/`, body,
)).data

export const gerarPreviaReprecificacao = async (
  orcamentoId: number,
  body: { base_destino?: number | null; banco_destino?: number | null; somente_ate?: string | null },
) => (await apiClient.post<PreviaReprecificacao>(
  `orcamento/orcamentos/${orcamentoId}/reprecificar/`, body,
)).data

export const getHistoricoReprecificacao = async (orcamentoId: number) =>
  (await apiClient.get<Reprecificacao[]>(
    `orcamento/orcamentos/${orcamentoId}/reprecificacoes/`,
  )).data

export const aplicarReprecificacao = async (loteId: number, linhas?: number[]) =>
  (await apiClient.post<PreviaReprecificacao>(
    `orcamento/reprecificacoes/${loteId}/aplicar/`, { linhas },
  )).data

export const desfazerReprecificacao = async (loteId: number) =>
  (await apiClient.post<Reprecificacao>(`orcamento/reprecificacoes/${loteId}/desfazer/`)).data

/** Baixa a peça exportada respeitando o auth do apiClient (não é link direto). */
export async function baixarExportacao(
  orcamentoId: number,
  params: { formato?: 'xlsx' | 'pdf'; nivel?: 'analitico' | 'sintetico'; peca?: string },
) {
  const resposta = await apiClient.get(`orcamento/orcamentos/${orcamentoId}/exportar/`, {
    params, responseType: 'blob',
  })
  const cabecalho = String(resposta.headers['content-disposition'] ?? '')
  const casado = /filename="?([^";]+)"?/.exec(cabecalho)
  const nome = casado?.[1] ?? `orcamento-${orcamentoId}.${params.formato ?? 'xlsx'}`
  const url = URL.createObjectURL(resposta.data as Blob)
  const link = document.createElement('a')
  link.href = url
  link.download = nome
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  return nome
}
