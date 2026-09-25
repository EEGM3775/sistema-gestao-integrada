import apiClient from '@/api/apiClient'
import type {
  ArvoreResposta, BancoPreco, BancoResumo, BaseReferencial, BaseResumo, CatalogoItem,
  ComponenteBancoPreco, ComponenteReferencia, ComposicaoBDI, ComposicaoReferenciaResposta,
  ControleLinha, ControleResposta, Cronograma, CurvaABC, DivergenciaAdocao,
  CurvaS, CustoPorCategoria, EtapaOpt, InsumoReferencia, ItemAdotado,
  ItemBancoPreco, ItemOrcado, ItemOrcadoInsumo, InsumoEscrita, LinhaParaRestaurar, ResultadoExclusao,
  AnaliticaOrcamento, NaturezaComPadroes, TipoItemProprio,
  MemoriaCalculo, MemorialNBR, ObraOpt, Orcamento, Paginated, ParametroObra,
  ParcelaEtapa, PastaComposicao, PavimentoObra, PrecoReal, PreviaReprecificacao, Reprecificacao,
  ResultadoAdocaoLote, ResumoDuplicata, RevisaoOrcamento, StatusModulo,
  UnidadeAutonoma,
  // ORC.7
  CoberturaMedicao, ComposicaoEncargos, ComposicaoPorNatureza, CurvaABCInsumos,
  DemandaGerada, DesembolsoPorInsumo, FormulaReajuste, IndiceEconomico, LinhaMedicao,
  MemoriaFator, MemoriaQuantitativo, ParcelaFormulaReajuste, PreviaReajuste,
  // ORC.8
  CargaBase, DocumentosDaFonte, EstadoDaCarga, FonteOficial,
  QuadroEncargos, RegimeEncargos, RelacaoInsumos, ResultadoReajuste, RubricaEncargos,
  TipoMaoDeObra, ValorIndice,
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

export const getAnalitica = async (orcamentoId: number) =>
  (await apiClient.get<AnaliticaOrcamento>(`orcamento/orcamentos/${orcamentoId}/analitica/`)).data

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
  /** ORC.10a — a publicação de onde o item foi pescado. É dela que sai o preço
   *  da linha; omitir cai na publicação do cabeçalho do orçamento. */
  base?: number | null
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

// --- ORC.9: tipos próprios de item (catálogo, permissão `cadastro.tipo_item`) ---

export async function listarTiposItem() {
  const { data } = await apiClient.get<Paginated<TipoItemProprio> | TipoItemProprio[]>(
    'catalogo/tipos-item/',
  )
  return Array.isArray(data) ? data : data.results
}

export const listarNaturezasItem = async () =>
  (await apiClient.get<NaturezaComPadroes[]>('catalogo/tipos-item/naturezas/')).data

export const criarTipoItem = async (payload: Partial<TipoItemProprio>) =>
  (await apiClient.post<TipoItemProprio>('catalogo/tipos-item/', payload)).data

export const atualizarTipoItem = async (id: number, payload: Partial<TipoItemProprio>) =>
  (await apiClient.patch<TipoItemProprio>(`catalogo/tipos-item/${id}/`, payload)).data

export const removerTipoItem = async (id: number) => {
  await apiClient.delete(`catalogo/tipos-item/${id}/`)
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
  (await apiClient.post<{
    adotados: number[]; criados: number; divergentes: DivergenciaAdocao[]
  }>(
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

// --- ORC.7: encargos analíticos, memória do quantitativo e reajuste ---

export const encargos = recurso<ComposicaoEncargos, Partial<ComposicaoEncargos>>('encargos')
export const rubricas = recurso<RubricaEncargos, Partial<RubricaEncargos>>('rubricas-encargos')
export const medicoes = recurso<LinhaMedicao, Partial<LinhaMedicao>>('medicoes')
export const indices = recurso<IndiceEconomico, never>('indices')
export const formulasReajuste = recurso<FormulaReajuste, Partial<FormulaReajuste>>('formulas-reajuste')
export const parcelasReajuste =
  recurso<ParcelaFormulaReajuste, Partial<ParcelaFormulaReajuste>>('parcelas-reajuste')

/** Cria o quadro já com as rubricas do modelo de partida — o usuário não digita
 *  trinta linhas para chegar onde toda publicação já chega. */
export const criarQuadroEncargos = async (body: {
  orcamento: number; tipo_mao_de_obra: TipoMaoDeObra; regime?: RegimeEncargos
}) => (await apiClient.post<ComposicaoEncargos>('orcamento/encargos/do-modelo/', body)).data

export const getQuadroEncargos = async (id: number) =>
  (await apiClient.get<QuadroEncargos>(`orcamento/encargos/${id}/quadro/`)).data

export const recalcularEncargos = async (id: number) =>
  (await apiClient.post<QuadroEncargos>(`orcamento/encargos/${id}/recalcular/`)).data

export const getMemoriaQuantitativo = async (itemOrcadoId: number) =>
  (await apiClient.get<MemoriaQuantitativo>(
    `orcamento/itens/${itemOrcadoId}/memoria-quantitativo/`,
  )).data

export const getComposicaoNatureza = async (itemOrcadoId: number) =>
  (await apiClient.get<ComposicaoPorNatureza>(
    `orcamento/itens/${itemOrcadoId}/composicao-natureza/`,
  )).data

/** Grava várias parciais de uma vez — o caminho do colar do Excel. Uma a uma,
 *  cada parcial dispararia um recálculo da árvore inteira. */
export const salvarMedicoesEmLote = async (body: {
  item_orcado: number
  substituir?: boolean
  linhas: Partial<LinhaMedicao>[]
}) => (await apiClient.post<MemoriaQuantitativo>('orcamento/medicoes/em-lote/', body)).data

export const getCoberturaMedicao = async (orcamentoId: number) =>
  (await apiClient.get<CoberturaMedicao>(
    `orcamento/orcamentos/${orcamentoId}/cobertura-medicao/`,
  )).data

export const getRelacaoInsumos = async (orcamentoId: number, categoria?: string) =>
  (await apiClient.get<RelacaoInsumos>(
    `orcamento/orcamentos/${orcamentoId}/relacao-insumos/`,
    { params: categoria ? { categoria } : {} },
  )).data

export const getCurvaAbcInsumos = async (orcamentoId: number) =>
  (await apiClient.get<CurvaABCInsumos>(
    `orcamento/orcamentos/${orcamentoId}/curva-abc-insumos/`,
  )).data

export const getDesembolsoInsumos = async (orcamentoId: number, categoria?: string) =>
  (await apiClient.get<DesembolsoPorInsumo>(
    `orcamento/orcamentos/${orcamentoId}/desembolso-insumos/`,
    { params: categoria ? { categoria } : {} },
  )).data

export const getSerieIndice = async (indiceId: number) =>
  (await apiClient.get<{ indice: number; codigo: string; valores: ValorIndice[] }>(
    `orcamento/indices/${indiceId}/serie/`,
  )).data

export const getFatorReajuste = async (formulaId: number, competencia: string) =>
  (await apiClient.get<MemoriaFator>(
    `orcamento/formulas-reajuste/${formulaId}/fator/`, { params: { competencia } },
  )).data

export const getPreviaReajuste = async (formulaId: number, competencia: string) =>
  (await apiClient.get<PreviaReajuste>(
    `orcamento/formulas-reajuste/${formulaId}/previa/`, { params: { competencia } },
  )).data

export const aplicarReajuste = async (
  formulaId: number, body: { competencia: string; motivo?: string },
) => (await apiClient.post<ResultadoReajuste>(
  `orcamento/formulas-reajuste/${formulaId}/aplicar/`, body,
)).data

/** O seam do SCM: a relação de insumos vira demanda de compra em rascunho.
 *  O endpoint é **do SCM** — quem sabe o que é demanda é ele. */
export const gerarDemandaDoOrcamento = async (body: {
  orcamento: number; tipo?: 'material' | 'servico'; centro_custo?: number | null; observacao?: string
}) => (await apiClient.post<DemandaGerada>('scm/demandas/do-orcamento/', body)).data

// ---------------------------------------------------------------------------
// ORC.8 — a carga da base oficial. Todos exigem `is_platform_admin`: 403 aqui é
// resposta normal para quem não é dono da plataforma, e a tela usa isso para
// simplesmente não mostrar o painel, em vez de mostrá-lo quebrado.
// ---------------------------------------------------------------------------

export const fontesOficiais = recurso<FonteOficial, Partial<FonteOficial>>('fontes-oficiais')

export const getEstadoDaCarga = async () =>
  (await apiClient.get<EstadoDaCarga>('orcamento/cargas/estado/')).data

export const listarCargas = async (params: Params = {}) =>
  (await apiClient.get<Paginated<CargaBase>>('orcamento/cargas/', { params })).data

/** ORC.8b — o **menu** de artefatos que a fonte publica.
 *
 *  Existe porque "a publicação do mês" deixou de ser uma coisa só quando a
 *  EMBASA entrou: ela publica por semestre, e são 65 tabelas carregáveis —
 *  expansão, operação de água e de esgoto, cada uma por convenção coletiva.
 *  Bate no site da fonte, então a tela chama ao abrir a fonte, não a cada
 *  render. */
export const getDocumentosDisponiveis = async (fonte: string, competencia?: string) =>
  (await apiClient.get<DocumentosDaFonte>('orcamento/cargas/documentos-disponiveis/', {
    params: { fonte, ...(competencia ? { competencia } : {}) },
  })).data

export const dispararCarga = async (body: {
  fonte: string; competencia?: string; url?: string
  somente_resumo?: boolean; aceitar_sem_classe?: boolean
}) => (await apiClient.post<CargaBase>('orcamento/cargas/', body)).data

/** Plano B: o ZIP à mão, para o mês em que a Caixa muda o layout ou o WAF aperta. */
export const enviarArquivoDaCarga = async (body: {
  fonte: string; competencia?: string; arquivo: File
  somente_resumo?: boolean; aceitar_sem_classe?: boolean
}) => {
  const form = new FormData()
  form.append('fonte', body.fonte)
  form.append('arquivo', body.arquivo)
  if (body.competencia) form.append('competencia', body.competencia)
  if (body.somente_resumo) form.append('somente_resumo', 'true')
  if (body.aceitar_sem_classe) form.append('aceitar_sem_classe', 'true')
  return (await apiClient.post<CargaBase>('orcamento/cargas/enviar/', form)).data
}

/** A resposta à carga que parou perguntando (classe sem tradução). */
export const repetirCarga = async (
  cargaId: number, body: { aceitar_sem_classe?: boolean; somente_resumo?: boolean } = {},
) => (await apiClient.post<CargaBase>(`orcamento/cargas/${cargaId}/repetir/`, body)).data

// --- ORC.10 — os verbos de edição da planilha ------------------------------

/** Mover, indentar, desindentar e reordenar — com a subárvore junto.
 *
 *  Duas formas de pedir, porque são dois gestos: `operacao` é o do teclado
 *  (a seleção precisa ser de irmãos) e `pai` + `posicao` é o do arrastar. */
export const moverItens = async (body: {
  orcamento: number
  itens: number[]
  operacao?: 'indentar' | 'desindentar' | 'cima' | 'baixo'
  pai?: number | null
  posicao?: number | null
}) => (await apiClient.post<{ movidas: number }>('orcamento/itens/mover/', body)).data

export const duplicarItens = async (orcamento: number, itens: number[]) =>
  (await apiClient.post<{ criadas: number; itens: number[] }>(
    'orcamento/itens/duplicar/', { orcamento, itens },
  )).data

/** Exclui e devolve `desfazer` — sem esse retorno não haveria Ctrl+Z de exclusão. */
export const excluirItens = async (orcamento: number, itens: number[]) =>
  (await apiClient.post<ResultadoExclusao>(
    'orcamento/itens/excluir-lote/', { orcamento, itens },
  )).data

export const restaurarItens = async (orcamento: number, linhas: LinhaParaRestaurar[]) =>
  (await apiClient.post<{ restauradas: number; itens: number[] }>(
    'orcamento/itens/restaurar/', { orcamento, linhas },
  )).data

export const aplicarPercentual = async (body: {
  orcamento: number; itens: number[]; percentual: string
  campo?: 'custo_unitario' | 'quantidade'
}) => (await apiClient.post<{ afetadas: number }>('orcamento/itens/aplicar-percentual/', body)).data

export const arredondarItens = async (body: {
  orcamento: number; itens: number[]; casas: number
  campo?: 'custo_unitario' | 'quantidade'
}) => (await apiClient.post<{ afetadas: number }>('orcamento/itens/arredondar/', body)).data

export const substituirTexto = async (body: {
  orcamento: number; procurar: string; trocar_por: string; itens?: number[] | null
}) => (await apiClient.post<{ afetadas: number }>('orcamento/itens/substituir-texto/', body)).data

/** Refaz o custo unitário pela soma dos insumos que a linha tem agora. */
export const recomporLinha = async (itemOrcadoId: number) =>
  (await apiClient.post<MemoriaCalculo & { custo_unitario: string }>(
    `orcamento/itens/${itemOrcadoId}/recompor/`,
  )).data

export const promoverComposicao = async (itemOrcadoId: number, banco?: number | null) =>
  (await apiClient.post<{ banco: number; banco_nome: string; item_banco: number; codigo: string }>(
    `orcamento/itens/${itemOrcadoId}/promover-composicao/`, { banco: banco ?? null },
  )).data

// --- ORC.10c — a composição da linha, agora escrita ------------------------

export const criarInsumo = async (body: InsumoEscrita) =>
  (await apiClient.post<ItemOrcadoInsumo>('orcamento/insumos/', body)).data

export const editarInsumo = async (insumoId: number, body: Partial<InsumoEscrita>) =>
  (await apiClient.patch<ItemOrcadoInsumo>(`orcamento/insumos/${insumoId}/`, body)).data

export const removerInsumo = async (insumoId: number) => {
  await apiClient.delete(`orcamento/insumos/${insumoId}/`)
}

// --- ORC.10e — reabrir o aprovado -----------------------------------------

export const destravarOrcamento = async (orcamentoId: number, motivo: string) =>
  (await apiClient.post<Orcamento>(`orcamento/orcamentos/${orcamentoId}/destravar/`, { motivo })).data
