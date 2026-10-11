import {
  keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient,
} from '@tanstack/react-query'
import * as api from './api/orcamentoApi'
import { orcKeys } from './api/queryKeys'
import type {
  ArvoreResposta, BancoPreco as Banco, ItemBancoPreco as ItemBanco, ItemOrcado, Orcamento,
  CurvaEtapa, ParcelaEtapa, PastaComposicao as Pasta,
  // ORC.7
  ComposicaoEncargos, LinhaMedicao,
  RegimeEncargos, RubricaEncargos, TipoMaoDeObra,
  // ORC.9
  TipoItemProprio,
  // ORC.8
  FonteOficial as FonteOficialTipo,
  // ORC.10
  InsumoEscrita, LinhaParaRestaurar,
} from './types'

type Params = Record<string, unknown>

export function useStatusModulo() {
  return useQuery({ queryKey: orcKeys.status(), queryFn: api.getStatusModulo, retry: false })
}

export function useOrcamentos(params: Params = {}) {
  return useQuery({
    queryKey: orcKeys.orcamentos.list(params),
    queryFn: () => api.orcamentos.listar(params),
    placeholderData: keepPreviousData,
  })
}

export function useOrcamento(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.orcamentos.detail(id ?? 0),
    queryFn: () => api.orcamentos.obter(id as number),
    enabled: id != null,
  })
}

export function useArvore(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.arvore(id ?? 0),
    queryFn: () => api.getArvore(id as number),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })
}

/** A composição de todas as linhas. Só sai do lugar quando a grade entra em
 *  **analítico** — em sintético ninguém olha insumo, e a analítica de uma obra
 *  inteira é maior que a planilha que a contém. */
export function useAnalitica(id: number | undefined, ativo: boolean) {
  return useQuery({
    queryKey: orcKeys.analitica(id ?? 0),
    queryFn: () => api.getAnalitica(id as number),
    enabled: id != null && ativo,
    placeholderData: keepPreviousData,
  })
}

/** Os tipos próprios da empresa. Lista curta (dezenas), sem paginação. */
export function useTiposItem(habilitado = true) {
  return useQuery({
    queryKey: orcKeys.tiposItem(),
    queryFn: api.listarTiposItem,
    enabled: habilitado,
  })
}

/** As naturezas e o padrão de flags de cada uma — o de-para é do backend.
 *  `staleTime` alto porque é tabela de domínio: muda quando o código muda. */
export function useNaturezasItem(habilitado = true) {
  return useQuery({
    queryKey: orcKeys.naturezasItem(),
    queryFn: api.listarNaturezasItem,
    enabled: habilitado,
    staleTime: 60 * 60 * 1000,
  })
}

export const useCriarTipoItem = () =>
  useVerbo((v: Partial<TipoItemProprio>) => api.criarTipoItem(v))
export const useAtualizarTipoItem = () =>
  useVerbo((v: { id: number; payload: Partial<TipoItemProprio> }) =>
    api.atualizarTipoItem(v.id, v.payload))
export const useRemoverTipoItem = () => useVerbo((id: number) => api.removerTipoItem(id))

export function useObras() {
  return useQuery({ queryKey: orcKeys.obras, queryFn: api.listarObras })
}

export function useEtapas(obra: number | undefined) {
  return useQuery({
    queryKey: orcKeys.etapas(obra ?? 0),
    queryFn: () => api.listarEtapas(obra as number),
    enabled: obra != null,
  })
}

/** O resumo das publicações — **seis telas do módulo** pedem este mesmo dado.
 *
 *  `staleTime` porque a resposta é cara e quase imóvel: ela agrega a base
 *  referencial inteira (com a SINAPI toda carregada, 1.460 publicações sobre
 *  16,8 milhões de linhas) e só muda quando o dono da plataforma carrega uma
 *  publicação nova — o que acontece uma vez por mês. Sem ele, o padrão do React
 *  Query refaz a consulta a cada montagem **e a cada foco da janela**: alternar
 *  para o navegador e voltar disparava a agregação de novo, que foi exatamente
 *  o travamento relatado ao abrir orçamento.
 *
 *  Não atrasa a carga nova: quem importa uma publicação invalida `orcKeys.all`,
 *  e invalidação vence `staleTime`. A única janela de defasagem é uma base
 *  carregada em OUTRA sessão — e essa a tela já mostrava com atraso. */
export function useBasesResumo() {
  return useQuery({
    queryKey: orcKeys.basesResumo(),
    queryFn: api.getBasesResumo,
    staleTime: 15 * 60 * 1000,
  })
}

export function useReferencias(params: Params, habilitado = true) {
  return useQuery({
    queryKey: orcKeys.referencias.list(params),
    queryFn: () => api.referencias.listar(params),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  })
}

/** A base referencial paginada **de verdade**.
 *
 *  Uma publicação da SINAPI tem ~12,5 mil linhas e o teto de página é 100
 *  (`PAGINA_MAXIMA["orcamento"]`). Buscar uma página só e parar ali fazia a tela
 *  parecer ter "algumas dezenas de itens" — o catálogo inteiro existia no banco
 *  e era inalcançável, porque não havia como pedir o item 101. "Refine a busca"
 *  não é navegação de catálogo: quem não sabe o nome exato precisa **percorrer**.
 */
export function useReferenciasInfinitas(params: Params, habilitado = true) {
  return useInfiniteQuery({
    queryKey: orcKeys.referencias.list({ ...params, modo: 'infinita' }),
    queryFn: ({ pageParam }) => api.referencias.listar({ ...params, page: pageParam }),
    initialPageParam: 1,
    // DRF devolve `next: null` na última — é ele quem diz se há mais, não uma
    // conta nossa de count/page_size, que erraria na última página.
    getNextPageParam: (ultima, todas) => (ultima.next ? todas.length + 1 : undefined),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  })
}

export function useComposicaoReferencia(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.composicaoRef(id ?? 0),
    queryFn: () => api.getComposicaoReferencia(id as number),
    enabled: id != null,
  })
}

export function useCurvaABC(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.curvaAbc(id ?? 0),
    queryFn: () => api.getCurvaABC(id as number),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })
}

export function usePorCategoria(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.porCategoria(id ?? 0),
    queryFn: () => api.getPorCategoria(id as number),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })
}

export function useCronograma(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.cronograma(id ?? 0),
    queryFn: () => api.getCronograma(id as number),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })
}

export function useMemoria(itemOrcadoId: number | undefined) {
  return useQuery({
    queryKey: orcKeys.memoria(itemOrcadoId ?? 0),
    queryFn: () => api.getMemoria(itemOrcadoId as number),
    enabled: itemOrcadoId != null,
  })
}

export function usePrecoReal(itemOrcadoId: number | undefined) {
  return useQuery({
    queryKey: orcKeys.precoReal(itemOrcadoId ?? 0),
    queryFn: () => api.getPrecoReal(itemOrcadoId as number),
    enabled: itemOrcadoId != null,
  })
}

export function useRevisoes(orcamentoId: number | undefined) {
  return useQuery({
    queryKey: orcKeys.revisoes.list({ orcamento: orcamentoId }),
    queryFn: () => api.revisoes.todos({ orcamento: orcamentoId }),
    enabled: orcamentoId != null,
  })
}

export function useBdis(orcamentoId: number | undefined) {
  return useQuery({
    queryKey: orcKeys.bdis.list({ orcamento: orcamentoId }),
    queryFn: () => api.bdis.todos({ orcamento: orcamentoId }),
    enabled: orcamentoId != null,
  })
}

export function useParametricos(obra?: number) {
  return useQuery({
    queryKey: orcKeys.parametricos.list({ obra }),
    queryFn: () => api.parametricos.todos(obra ? { obra } : {}),
  })
}

export function usePavimentos(obra: number | undefined) {
  return useQuery({
    queryKey: orcKeys.pavimentos.list({ obra }),
    queryFn: () => api.pavimentos.todos({ obra }),
    enabled: obra != null,
  })
}

export function useUnidades(obra: number | undefined) {
  return useQuery({
    queryKey: orcKeys.unidades.list({ obra }),
    queryFn: () => api.unidades.todos({ obra }),
    enabled: obra != null,
  })
}

export function useMemoriais(obra: number | undefined) {
  return useQuery({
    queryKey: orcKeys.memoriais.list({ obra }),
    queryFn: () => api.memoriais.todos({ obra }),
    enabled: obra != null,
  })
}

export function useQuadrosNBR(obra: number | undefined) {
  return useQuery({
    queryKey: orcKeys.nbr(obra ?? 0),
    queryFn: () => api.getQuadrosNBR(obra as number),
    enabled: obra != null,
  })
}

function useVerbo<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: orcKeys.all }) })
}

export const useCriarOrcamento = () => useVerbo((v: Partial<Orcamento>) => api.orcamentos.criar(v))
export const useAtualizarOrcamento = () =>
  useVerbo((v: { id: number; payload: Partial<Orcamento> }) => api.orcamentos.atualizar(v.id, v.payload))
export const useRemoverOrcamento = () => useVerbo((id: number) => api.orcamentos.remover(id))
export const useAprovar = () => useVerbo((id: number) => api.aprovar(id))
export const useRecalcular = () => useVerbo((id: number) => api.recalcular(id))
export const useRevisar = () =>
  useVerbo((v: { id: number; tipo: string; motivo: string }) => api.revisar(v.id, { tipo: v.tipo, motivo: v.motivo }))

export const useCriarItem = () => useVerbo((v: Partial<ItemOrcado>) => api.itens.criar(v))
export const useAtualizarItem = () =>
  useVerbo((v: { id: number; payload: Partial<ItemOrcado> }) => api.itens.atualizar(v.id, v.payload))
export const useRemoverItem = () => useVerbo((id: number) => api.itens.remover(id))
export const useItemDoCatalogo = () => useVerbo((v: Parameters<typeof api.criarItemDoCatalogo>[0]) => api.criarItemDoCatalogo(v))
export const useExplodir = () => useVerbo((id: number) => api.explodirItem(id))
export const useAplicarPrecoReal = () =>
  useVerbo((v: { id: number; origem: 'scm' | 'sil' }) => api.aplicarPrecoReal(v.id, v.origem))

/** Edição de célula da grade: a linha muda na tela no instante da tecla e o
 *  servidor confirma depois. Sem isso, digitar 300 quantidades seguidas fica
 *  refém do round-trip — e o total só é recalculado pelo backend, então a
 *  resposta ainda é a verdade final. */
export function useEditarCelula(orcamentoId: number | undefined) {
  const qc = useQueryClient()
  const chave = orcKeys.arvore(orcamentoId ?? 0)
  return useMutation({
    mutationFn: (v: { id: number; payload: Partial<ItemOrcado> }) => api.itens.atualizar(v.id, v.payload),
    onMutate: async v => {
      await qc.cancelQueries({ queryKey: chave })
      const anterior = qc.getQueryData<ArvoreResposta>(chave)
      if (anterior) {
        qc.setQueryData<ArvoreResposta>(chave, {
          ...anterior,
          itens: anterior.itens.map(i => (i.item_orcado_id === v.id ? { ...i, ...v.payload } : i)),
        })
      }
      return { anterior }
    },
    onError: (_erro, _v, ctx) => {
      if (ctx?.anterior) qc.setQueryData(chave, ctx.anterior)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: chave })
      qc.invalidateQueries({ queryKey: orcKeys.analitica(orcamentoId ?? 0) })
      qc.invalidateQueries({ queryKey: orcKeys.orcamentos.all })
    },
  })
}

export const useAdotar = () => useVerbo((id: number) => api.adotarReferencia(id))
export const useAdotarLote = () => useVerbo((ids: number[]) => api.adotarLote(ids))

export const useDistribuirCronograma = () =>
  useVerbo((v: { id: number; inicio: string; fim: string; curva?: CurvaEtapa; so_sem_plano?: boolean }) =>
    api.distribuirCronograma(v.id, { inicio: v.inicio, fim: v.fim, curva: v.curva, so_sem_plano: v.so_sem_plano }))
export const usePlanejarEtapa = () =>
  useVerbo((v: { id: number; grupo: number; inicio: string; termino: string; curva?: CurvaEtapa }) =>
    api.planejarEtapa(v.id, { grupo: v.grupo, inicio: v.inicio, termino: v.termino, curva: v.curva }))
export const useRemoverEtapaDoCronograma = () =>
  useVerbo((v: { id: number; grupo: number }) => api.removerEtapaDoCronograma(v.id, v.grupo))
export const useVincularEtapa = () =>
  useVerbo((v: { id: number; grupo: number; etapa: number | null }) => api.vincularEtapaDaObra(v.id, v.grupo, v.etapa))
export function useEtapasDaObra(obraId: number | undefined) {
  return useQuery({
    queryKey: ['orcamento', 'etapas-da-obra', obraId ?? 0],
    queryFn: () => api.getEtapasDaObra(obraId as number),
    enabled: obraId != null,
  })
}
export const useAtualizarParcela = () =>
  useVerbo((v: { id: number; payload: Partial<ParcelaEtapa> }) => api.parcelas.atualizar(v.id, v.payload))

// --- ORC.5b: bancos, importação, reprecificação, duplicação, exportação ---

export function useBancos(params: Params = {}) {
  return useQuery({
    queryKey: orcKeys.bancos.list(params),
    queryFn: () => api.bancos.todos(params),
    placeholderData: keepPreviousData,
  })
}

export function useBancosResumo() {
  return useQuery({ queryKey: orcKeys.bancosResumo(), queryFn: api.getBancosResumo })
}

export function useItensBanco(params: Params, habilitado = true) {
  return useQuery({
    queryKey: orcKeys.itensBanco.list(params),
    queryFn: () => api.itensBanco.listar(params),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  })
}

export function usePastas(banco: number | undefined) {
  return useQuery({
    queryKey: orcKeys.pastas.list({ banco }),
    queryFn: () => api.pastas.todos({ banco }),
    enabled: banco != null,
  })
}

export function useComposicaoBanco(itemId: number | undefined) {
  return useQuery({
    queryKey: orcKeys.composicaoBanco(itemId ?? 0),
    queryFn: () => api.getComposicaoBanco(itemId as number),
    enabled: itemId != null,
  })
}

export function useHistoricoReprecificacao(orcamentoId: number | undefined) {
  return useQuery({
    queryKey: orcKeys.historicoRepre(orcamentoId ?? 0),
    queryFn: () => api.getHistoricoReprecificacao(orcamentoId as number),
    enabled: orcamentoId != null,
  })
}

export const useCriarBanco = () => useVerbo((v: Partial<Banco>) => api.bancos.criar(v))
export const useAtualizarBanco = () =>
  useVerbo((v: { id: number; payload: Partial<Banco> }) => api.bancos.atualizar(v.id, v.payload))
export const useRemoverBanco = () => useVerbo((id: number) => api.bancos.remover(id))
export const useTravarBanco = () => useVerbo((id: number) => api.travarBanco(id))
export const useDestravarBanco = () => useVerbo((id: number) => api.destravarBanco(id))
export const useAdotarDoBanco = () =>
  useVerbo((v: { banco: number; itens: number[] }) => api.adotarDoBanco(v.banco, v.itens))
export const useCopiarDaBasePublica = () =>
  useVerbo((v: { banco: number; referencias: number[]; comComposicao?: boolean }) =>
    api.copiarDaBasePublica(v.banco, v.referencias, v.comComposicao ?? true))

export const useCriarItemBanco = () => useVerbo((v: Partial<ItemBanco>) => api.itensBanco.criar(v))
export const useAtualizarItemBanco = () =>
  useVerbo((v: { id: number; payload: Partial<ItemBanco> }) => api.itensBanco.atualizar(v.id, v.payload))
export const useRemoverItemBanco = () => useVerbo((id: number) => api.itensBanco.remover(id))
export const useCriarPasta = () => useVerbo((v: Partial<Pasta>) => api.pastas.criar(v))

export const useDuplicarOrcamento = () =>
  useVerbo((v: { id: number; obra?: number | null; descricao?: string }) =>
    api.duplicarOrcamento(v.id, { obra: v.obra, descricao: v.descricao }))
export const useCopiarItensParaOrcamento = () =>
  useVerbo((v: { destino: number; itens: number[]; pai?: number | null }) =>
    api.copiarItens(v.destino, { itens: v.itens, pai: v.pai }))

export const useGerarPreviaReprecificacao = () =>
  useVerbo((v: {
    orcamento: number; base_destino?: number | null
    banco_destino?: number | null; somente_ate?: string | null
  }) => api.gerarPreviaReprecificacao(v.orcamento, {
    base_destino: v.base_destino, banco_destino: v.banco_destino, somente_ate: v.somente_ate,
  }))
export const useAplicarReprecificacao = () =>
  useVerbo((v: { lote: number; linhas?: number[] }) => api.aplicarReprecificacao(v.lote, v.linhas))
export const useDesfazerReprecificacao = () => useVerbo((lote: number) => api.desfazerReprecificacao(lote))

// --- ORC.7: encargos analíticos e memória do quantitativo ---

export function useQuadrosEncargos(orcamento: number | undefined) {
  return useQuery({
    queryKey: orcKeys.encargos.list({ orcamento }),
    queryFn: () => api.encargos.todos({ orcamento }),
    enabled: orcamento != null,
  })
}

export function useQuadroEncargos(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.quadroEncargos(id ?? 0),
    queryFn: () => api.getQuadroEncargos(id as number),
    enabled: id != null,
  })
}

export function useMemoriaQuantitativo(itemOrcado: number | undefined) {
  return useQuery({
    queryKey: orcKeys.memoriaQuantitativo(itemOrcado ?? 0),
    queryFn: () => api.getMemoriaQuantitativo(itemOrcado as number),
    enabled: itemOrcado != null,
  })
}

export function useComposicaoNatureza(itemOrcado: number | undefined) {
  return useQuery({
    queryKey: orcKeys.composicaoNatureza(itemOrcado ?? 0),
    queryFn: () => api.getComposicaoNatureza(itemOrcado as number),
    enabled: itemOrcado != null,
  })
}

export function useCoberturaMedicao(orcamento: number | undefined) {
  return useQuery({
    queryKey: orcKeys.coberturaMedicao(orcamento ?? 0),
    queryFn: () => api.getCoberturaMedicao(orcamento as number),
    enabled: orcamento != null,
  })
}

export function useRelacaoInsumos(orcamento: number | undefined, categoria?: string) {
  return useQuery({
    queryKey: orcKeys.relacaoInsumos(orcamento ?? 0, categoria),
    queryFn: () => api.getRelacaoInsumos(orcamento as number, categoria),
    enabled: orcamento != null,
    placeholderData: keepPreviousData,
  })
}

export function useCurvaAbcInsumos(orcamento: number | undefined) {
  return useQuery({
    queryKey: orcKeys.curvaAbcInsumos(orcamento ?? 0),
    queryFn: () => api.getCurvaAbcInsumos(orcamento as number),
    enabled: orcamento != null,
  })
}

export function useDesembolsoInsumos(orcamento: number | undefined, categoria?: string) {
  return useQuery({
    queryKey: orcKeys.desembolsoInsumos(orcamento ?? 0, categoria),
    queryFn: () => api.getDesembolsoInsumos(orcamento as number, categoria),
    enabled: orcamento != null,
    placeholderData: keepPreviousData,
  })
}

/** A prévia só corre com competência escolhida — pedir sem ela devolveria 400 e
 *  encheria a tela de erro enquanto o usuário ainda está escolhendo o mês. */
export const useCriarQuadroEncargos = () =>
  useVerbo((v: { orcamento: number; tipo_mao_de_obra: TipoMaoDeObra; regime?: RegimeEncargos }) =>
    api.criarQuadroEncargos(v))
export const useAtualizarRubrica = () =>
  useVerbo((v: { id: number; payload: Partial<RubricaEncargos> }) =>
    api.rubricas.atualizar(v.id, v.payload))
export const useCriarRubrica = () => useVerbo((v: Partial<RubricaEncargos>) => api.rubricas.criar(v))
export const useRemoverRubrica = () => useVerbo((id: number) => api.rubricas.remover(id))
export const useAtualizarQuadroEncargos = () =>
  useVerbo((v: { id: number; payload: Partial<ComposicaoEncargos> }) =>
    api.encargos.atualizar(v.id, v.payload))
export const useRemoverQuadroEncargos = () => useVerbo((id: number) => api.encargos.remover(id))

export const useCriarMedicao = () => useVerbo((v: Partial<LinhaMedicao>) => api.medicoes.criar(v))
export const useAtualizarMedicao = () =>
  useVerbo((v: { id: number; payload: Partial<LinhaMedicao> }) => api.medicoes.atualizar(v.id, v.payload))
export const useRemoverMedicao = () => useVerbo((id: number) => api.medicoes.remover(id))
export const useMedicoesEmLote = () =>
  useVerbo((v: { item_orcado: number; linhas: Partial<LinhaMedicao>[]; substituir?: boolean }) =>
    api.salvarMedicoesEmLote(v))


export const useGerarDemandaDoOrcamento = () =>
  useVerbo((v: { orcamento: number; tipo?: 'material' | 'servico'; observacao?: string }) =>
    api.gerarDemandaDoOrcamento(v))

// ---------------------------------------------------------------------------
// ORC.8 — a carga da base oficial
// ---------------------------------------------------------------------------

/** O estado da carga, com **polling só enquanto há corrida rodando**.
 *
 *  A corrida leva minutos e a tela precisa mostrar o degrau ("baixando 7,2 MB",
 *  "gravando SP · onerado") — mas manter um intervalo aceso o resto do tempo
 *  seria uma chamada a cada poucos segundos, para sempre, na tela mais aberta do
 *  módulo. Daí o intervalo ser função do próprio dado.
 *
 *  `retry: false` porque **403 é resposta normal aqui**: quem não é dono da
 *  plataforma não vê o painel, e reenviar três vezes um pedido que vai ser
 *  negado só atrasa a tela de todo mundo.
 */
export function useEstadoDaCarga(ativo = true) {
  return useQuery({
    queryKey: orcKeys.estadoDaCarga(),
    queryFn: api.getEstadoDaCarga,
    enabled: ativo,
    retry: false,
    refetchInterval: q => (q.state.data?.em_andamento ? 3000 : false),
  })
}

export function useCargas(params: Params = {}, ativo = true) {
  return useQuery({
    queryKey: orcKeys.cargas.list(params),
    queryFn: () => api.listarCargas(params),
    enabled: ativo,
    retry: false,
    placeholderData: keepPreviousData,
  })
}

function useVerboDaCarga<T, R>(fn: (v: T) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation<R, Error, T>({
    mutationFn: fn,
    // Invalida a base inteira do módulo, e não só as chaves da carga: uma carga
    // concluída reescreve publicações, e é `bases-resumo` que a tela de bases lê.
    onSuccess: () => qc.invalidateQueries({ queryKey: orcKeys.all }),
  })
}

export const useSalvarFonteOficial = () =>
  useVerboDaCarga((v: { id?: number; payload: Partial<FonteOficialTipo> }) =>
    v.id ? api.fontesOficiais.atualizar(v.id, v.payload) : api.fontesOficiais.criar(v.payload))

/** ORC.8b — o menu de artefatos da fonte. Bate no site dela, então não é
 *  refeito sozinho: `staleTime` alto porque a página de um semestre da EMBASA
 *  não muda entre dois cliques, e uma lista de 76 links custa um download. */
export function useDocumentosDisponiveis(fonte: string, ativo = true) {
  return useQuery({
    queryKey: orcKeys.documentosDaFonte(fonte),
    queryFn: () => api.getDocumentosDisponiveis(fonte),
    enabled: ativo && !!fonte,
    retry: false,
    staleTime: 10 * 60 * 1000,
  })
}

export const useDispararCarga = () =>
  useVerboDaCarga((v: {
    fonte: string; competencia?: string; url?: string
    somente_resumo?: boolean; aceitar_sem_classe?: boolean
  }) => api.dispararCarga(v))

export const useEnviarArquivoDaCarga = () =>
  useVerboDaCarga((v: {
    fonte: string; competencia?: string; arquivo: File
    somente_resumo?: boolean; aceitar_sem_classe?: boolean
  }) => api.enviarArquivoDaCarga(v))

export const useRepetirCarga = () =>
  useVerboDaCarga((v: { id: number; aceitar_sem_classe?: boolean; somente_resumo?: boolean }) =>
    api.repetirCarga(v.id, { aceitar_sem_classe: v.aceitar_sem_classe, somente_resumo: v.somente_resumo }))

// --- ORC.10 — os verbos de edição da planilha ------------------------------
//
// Todos passam pelo `useVerbo`, que invalida a base inteira do módulo: mover
// uma etapa muda a EAP de tudo que pende dela, o total de dois ancestrais e o
// cabeçalho do orçamento — invalidar só a árvore deixaria o cockpit e o
// controle exibindo o total antigo até alguém recarregar.

export const useMoverItens = () =>
  useVerbo((v: Parameters<typeof api.moverItens>[0]) => api.moverItens(v))

export const useDuplicarItens = () =>
  useVerbo((v: { orcamento: number; itens: number[] }) => api.duplicarItens(v.orcamento, v.itens))

export const useExcluirItens = () =>
  useVerbo((v: { orcamento: number; itens: number[] }) => api.excluirItens(v.orcamento, v.itens))

export const useRestaurarItens = () =>
  useVerbo((v: { orcamento: number; linhas: LinhaParaRestaurar[] }) =>
    api.restaurarItens(v.orcamento, v.linhas))

export const useAplicarPercentual = () =>
  useVerbo((v: Parameters<typeof api.aplicarPercentual>[0]) => api.aplicarPercentual(v))

export const useArredondarItens = () =>
  useVerbo((v: Parameters<typeof api.arredondarItens>[0]) => api.arredondarItens(v))

export const useSubstituirTexto = () =>
  useVerbo((v: Parameters<typeof api.substituirTexto>[0]) => api.substituirTexto(v))

export const useRecomporLinha = () => useVerbo((id: number) => api.recomporLinha(id))

export const usePromoverComposicao = () =>
  useVerbo((v: { item: number; banco?: number | null }) =>
    api.promoverComposicao(v.item, v.banco ?? null))

// --- ORC.10c — a composição da linha ---------------------------------------

export const useCriarInsumo = () => useVerbo((v: InsumoEscrita) => api.criarInsumo(v))

export const useEditarInsumo = () =>
  useVerbo((v: { id: number; payload: Partial<InsumoEscrita> }) =>
    api.editarInsumo(v.id, v.payload))

export const useRemoverInsumo = () => useVerbo((id: number) => api.removerInsumo(id))

// --- ORC.10e — reabrir o aprovado ------------------------------------------

export const useDestravarOrcamento = () =>
  useVerbo((v: { id: number; motivo: string }) => api.destravarOrcamento(v.id, v.motivo))
