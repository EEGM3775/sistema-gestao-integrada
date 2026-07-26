import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api/orcamentoApi'
import { orcKeys } from './api/queryKeys'
import type {
  ArvoreResposta, BancoPreco as Banco, ItemBancoPreco as ItemBanco, ItemOrcado, Orcamento,
  ParcelaEtapa, PastaComposicao as Pasta,
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

export function useBasesResumo() {
  return useQuery({ queryKey: orcKeys.basesResumo(), queryFn: api.getBasesResumo })
}

export function useReferencias(params: Params, habilitado = true) {
  return useQuery({
    queryKey: orcKeys.referencias.list(params),
    queryFn: () => api.referencias.listar(params),
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

export function useCurvaS(id: number | undefined) {
  return useQuery({
    queryKey: orcKeys.curvaS(id ?? 0),
    queryFn: () => api.getCurvaS(id as number),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })
}

export function useControle(obra?: number) {
  return useQuery({
    queryKey: orcKeys.controle(obra),
    queryFn: () => api.getControle(obra),
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
      qc.invalidateQueries({ queryKey: orcKeys.orcamentos.all })
    },
  })
}

export const useAdotar = () => useVerbo((id: number) => api.adotarReferencia(id))
export const useAdotarLote = () => useVerbo((ids: number[]) => api.adotarLote(ids))

export const useDistribuirCronograma = () =>
  useVerbo((v: { id: number; inicio: string; fim: string; etapa?: number | null }) =>
    api.distribuirCronograma(v.id, { inicio: v.inicio, fim: v.fim, etapa: v.etapa }))
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
