import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api/pdcaApi'
import { pdcaKeys } from './api/queryKeys'
import type {
  AplicacaoDeModelo, Apontamento, Atividade, Calendario, Cronograma, EdicaoEmLote,
  ExcecaoCalendario, Granularidade, LinhaDeApontamento, Precedencia,
} from './types'

type Params = Record<string, unknown>

export function useStatusModulo() {
  return useQuery({ queryKey: pdcaKeys.status(), queryFn: api.getStatusModulo, retry: false })
}

export function useCronogramas(params: Params = {}) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.lista(params),
    queryFn: () => api.cronogramas.listar(params),
    placeholderData: keepPreviousData,
  })
}

export function useGantt(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.gantt(id ?? 0),
    queryFn: () => api.cronogramas.gantt(id as number),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })
}

export function useObras() {
  return useQuery({
    queryKey: pdcaKeys.obras(),
    queryFn: async () => {
      const dados = await api.obras.listar()
      return Array.isArray(dados) ? dados : dados.results
    },
  })
}

export function useCalendarios(params: Params = {}) {
  return useQuery({
    queryKey: pdcaKeys.calendarios(params),
    queryFn: async () => (await api.calendarios.listar({ page_size: 200, ...params })).results,
  })
}

/** Toda mutação do plano invalida o Gantt inteiro: o CPM recalcula datas de
 *  atividades que a tela não tocou, e atualizar só a linha editada deixaria as
 *  outras mostrando a data anterior — dado errado com cara de certo. */
function useInvalidarGantt(cronogramaId: number | undefined) {
  const qc = useQueryClient()
  return () => {
    if (cronogramaId != null) qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.gantt(cronogramaId) })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'cronogramas'] })
  }
}

export function useCriarCronograma() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<Cronograma>) => api.cronogramas.criar(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'cronogramas'] }),
  })
}

export function useCalcularCpm(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: () => api.cronogramas.calcular(cronogramaId as number),
    onSuccess: invalidar,
  })
}

export function usePublicar(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: () => api.cronogramas.publicar(cronogramaId as number),
    onSuccess: invalidar,
  })
}

export function useReplanejar(cronogramaId: number | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (motivo: string) => api.cronogramas.replanejar(cronogramaId as number, motivo),
    onSuccess: () => qc.invalidateQueries({ queryKey: pdcaKeys.raiz }),
  })
}

export function useSalvarAtividade(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: Partial<Atividade> }) =>
      id ? api.atividades.atualizar(id, payload) : api.atividades.criar(payload),
    onSuccess: invalidar,
  })
}

export function useExcluirAtividade(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({ mutationFn: (id: number) => api.atividades.excluir(id), onSuccess: invalidar })
}

export function useReprogramar(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number; nao_comecar_antes_de?: string | null; duracao_dias?: number }) =>
      api.atividades.reprogramar(id, payload),
    onSuccess: invalidar,
  })
}

export function useSalvarPrecedencia(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: (payload: Partial<Precedencia>) => api.precedencias.criar(payload),
    onSuccess: invalidar,
  })
}

export function useExcluirPrecedencia(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({ mutationFn: (id: number) => api.precedencias.excluir(id), onSuccess: invalidar })
}

// ---------------------------------------------------------------------------
// As duas leituras que o backend já servia sem tela
// ---------------------------------------------------------------------------

/** O desvio contra a linha de base. Vem no payload do Gantt também, mas aqui
 *  ele é buscado sozinho: o painel de base é aberto por quem quer **conferir**,
 *  e recarregá-lo não deve arrastar as centenas de atividades junto. */
export function useLinhaDeBase(cronogramaId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.base(cronogramaId ?? 0),
    queryFn: () => api.cronogramas.linhaDeBase(cronogramaId as number),
    enabled: cronogramaId != null && ativo,
  })
}

export function useCobertura(cronogramaId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.cobertura(cronogramaId ?? 0),
    queryFn: () => api.cronogramas.cobertura(cronogramaId as number),
    enabled: cronogramaId != null && ativo,
  })
}

export function useAtualizarPrecedencia(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<Precedencia> }) =>
      api.precedencias.atualizar(id, payload),
    onSuccess: invalidar,
  })
}

// ---------------------------------------------------------------------------
// Vínculos com outros módulos
// ---------------------------------------------------------------------------
//
// `retry: false` nos quatro **de propósito**: o erro esperado aqui é 403 (o
// tenant não contratou o Orçamento, o usuário não tem o RH), e repetir três
// vezes uma negativa que não vai mudar só atrasa a mensagem que a tela precisa
// dar. A tela lê `isError` e mostra o cadeado com o motivo.

const desembrulhar = <T,>(dados: { results: T[] } | T[]): T[] =>
  Array.isArray(dados) ? dados : dados.results

export function useLocaisDaObra(obra: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.vinculos.locais(obra ?? 0),
    queryFn: async () => (await api.vinculos.locais(obra as number)).results,
    enabled: obra != null,
    retry: false,
  })
}

export function useEtapasDaObra(obra: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.vinculos.etapas(obra ?? 0),
    queryFn: async () => desembrulhar(await api.vinculos.etapas(obra as number)),
    enabled: obra != null,
    retry: false,
  })
}

export function useOrcamentosDaObra(obra: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.vinculos.orcamentos(obra ?? 0),
    queryFn: async () => desembrulhar(await api.vinculos.orcamentos(obra as number)),
    enabled: obra != null,
    retry: false,
  })
}

export function useItensOrcados(orcamento: number | undefined, busca: string) {
  return useQuery({
    queryKey: pdcaKeys.vinculos.itens(orcamento ?? 0, busca),
    queryFn: async () => (await api.vinculos.itens(orcamento as number, busca)).results,
    enabled: orcamento != null,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useResponsaveis(busca: string, ativo: boolean) {
  return useQuery({
    queryKey: pdcaKeys.vinculos.responsaveis(busca),
    queryFn: async () => desembrulhar(await api.vinculos.responsaveis(busca)),
    enabled: ativo,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

/**
 * Escrita **em lote** — muitas células numa requisição.
 *
 * Colar 200 linhas de planilha e renumerar 400 códigos são gestos que o
 * planejador faz sem pensar, e cada um deles valia N requisições: N idas de
 * rede, N autenticações, e — pior — um plano em estado intermediário visível
 * para quem estivesse olhando a mesma obra no meio do caminho. O endpoint
 * `lote/` aplica tudo dentro de uma transação, e a tela invalida **uma** vez.
 *
 * O teto por chamada é do dono (`payment/planos.py` §5.5e) e chega à tela pelo
 * `status/` do módulo — quem fatia em blocos é quem chama, com o número que
 * vale hoje em vez de uma cópia envelhecendo no bundle.
 */
export function useEscritaEmLote(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: (edicoes: EdicaoEmLote[]) =>
      api.cronogramas.lote(cronogramaId as number, edicoes),
    onSuccess: invalidar,
  })
}

export function useRenumerarEap(cronogramaId: number | undefined) {
  const invalidar = useInvalidarGantt(cronogramaId)
  return useMutation({
    mutationFn: (simular: boolean) =>
      api.cronogramas.renumerarEap(cronogramaId as number, simular),
    // Simular não muda nada: invalidar ali faria a grade inteira recarregar
    // para responder uma pergunta.
    onSuccess: resultado => { if (!resultado.simulado) invalidar() },
  })
}

// ---------------------------------------------------------------------------
// Plano modelo — a biblioteca de padrões da empresa (PDCA.1b)
// ---------------------------------------------------------------------------

export function useModelos(ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.modelos(),
    queryFn: async () => (await api.cronogramas.modelos()).results,
    enabled: ativo,
  })
}

/** Marcar e desmarcar invalidam a **biblioteca** e a listagem, não o Gantt: o
 *  plano não muda de forma ao virar padrão, muda de papel. */
function useInvalidarBiblioteca() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.modelos() })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'cronogramas'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'cronograma'] })
  }
}

export function useMarcarModelo() {
  const invalidar = useInvalidarBiblioteca()
  return useMutation({
    mutationFn: ({ id, nome }: { id: number; nome: string }) =>
      api.cronogramas.marcarModelo(id, nome),
    onSuccess: invalidar,
  })
}

export function useDesmarcarModelo() {
  const invalidar = useInvalidarBiblioteca()
  return useMutation({
    mutationFn: (id: number) => api.cronogramas.desmarcarModelo(id),
    onSuccess: invalidar,
  })
}

export function useAplicarModelo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AplicacaoDeModelo }) =>
      api.cronogramas.aplicarModelo(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: pdcaKeys.raiz }),
  })
}

// ---------------------------------------------------------------------------
// Expediente — calendários e as exceções que fogem da regra
// ---------------------------------------------------------------------------

export function useExpediente() {
  return useQuery({
    queryKey: pdcaKeys.expediente.lista(),
    queryFn: async () => (await api.calendarios.listar({ page_size: 200 })).results,
  })
}

export function useCalendario(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.expediente.detalhe(id ?? 0),
    queryFn: () => api.calendarios.detalhar(id as number),
    enabled: id != null,
  })
}

export function useSalvarCalendario() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: Partial<Calendario> }) =>
      id ? api.calendarios.atualizar(id, payload) : api.calendarios.criar(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'expediente'] })
      qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'calendarios'] })
    },
  })
}

export function useExcluirCalendario() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.calendarios.excluir(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'expediente'] }),
  })
}

export function useExcecoes(calendario: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.expediente.excecoes(calendario ?? 0),
    queryFn: async () => (await api.excecoes.listar(calendario as number)).results,
    enabled: calendario != null,
  })
}

export function useSalvarExcecao(calendario: number | undefined) {
  const qc = useQueryClient()
  const invalidar = () => {
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'expediente'] })
  }
  return useMutation({
    mutationFn: (payload: Partial<ExcecaoCalendario>) =>
      api.excecoes.criar({ calendario, ...payload }),
    onSuccess: invalidar,
  })
}

export function useExcluirExcecao() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.excecoes.excluir(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'expediente'] }),
  })
}

/** A prova do expediente: quantos dias úteis há numa janela, quais feriados
 *  caem nela e se a base deles está sincronizada. É o que transforma a tela de
 *  configuração em algo conferível. */
export function useDiasUteis(id: number | undefined, inicio: string, fim: string) {
  return useQuery({
    queryKey: pdcaKeys.expediente.diasUteis(id ?? 0, inicio, fim),
    queryFn: () => api.calendarios.diasUteis(id as number, inicio, fim),
    enabled: id != null && !!inicio && !!fim,
    placeholderData: keepPreviousData,
  })
}

// ---------------------------------------------------------------------------
// PDCA.2 — o avanço apontado
// ---------------------------------------------------------------------------

/** Toda escrita de avanço invalida **três** coisas, e nenhuma é opcional: o
 *  avanço em si, a curva S (que é ele no tempo) e o Gantt (que carrega o avanço
 *  junto das datas para a barra mostrar o executado dentro do previsto).
 *  Invalidar só a primeira deixaria a curva do lado mostrando o número de antes
 *  — dado errado com cara de certo, na mesma tela. */
function useInvalidarAvanco(cronogramaId: number | undefined) {
  const qc = useQueryClient()
  return () => {
    if (cronogramaId == null) return
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.avanco(cronogramaId) })
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.gantt(cronogramaId) })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'cronograma', cronogramaId, 'curva'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'apontamentos'] })
  }
}

export function useAvanco(cronogramaId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.avanco(cronogramaId ?? 0),
    queryFn: () => api.cronogramas.avanco(cronogramaId as number),
    enabled: cronogramaId != null && ativo,
  })
}

export function useCurvaS(
  cronogramaId: number | undefined, granularidade: Granularidade, ativo = true,
) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.curva(cronogramaId ?? 0, granularidade),
    queryFn: () => api.cronogramas.curvaS(cronogramaId as number, granularidade),
    enabled: cronogramaId != null && ativo,
    placeholderData: keepPreviousData,
  })
}

export function useApontamentos(params: Params, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.apontamentos(params),
    queryFn: () => api.apontamentos.listar(params),
    enabled: ativo,
    placeholderData: keepPreviousData,
  })
}

export function useApontar(cronogramaId: number | undefined) {
  const invalidar = useInvalidarAvanco(cronogramaId)
  return useMutation({
    mutationFn: (payload: Partial<Apontamento>) => api.apontamentos.criar(payload),
    onSuccess: invalidar,
  })
}

/** O lote é o gesto da segunda-feira de manhã: as frentes ativas apontadas de
 *  uma vez. O teto por chamada é do dono e chega pelo `status/` do módulo. */
export function useApontarEmLote(cronogramaId: number | undefined) {
  const invalidar = useInvalidarAvanco(cronogramaId)
  return useMutation({
    mutationFn: (linhas: LinhaDeApontamento[]) =>
      api.apontamentos.lote(cronogramaId as number, linhas),
    onSuccess: invalidar,
  })
}

export function useEstornar(cronogramaId: number | undefined) {
  const invalidar = useInvalidarAvanco(cronogramaId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.apontamentos.estornar(id, motivo),
    onSuccess: invalidar,
  })
}
