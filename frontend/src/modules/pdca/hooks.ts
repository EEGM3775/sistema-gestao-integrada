import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api/pdcaApi'
import { pdcaKeys } from './api/queryKeys'
import type {
  AplicacaoDeModelo, Apontamento, Atividade, Calendario, Contrato, Cronograma,
  EdicaoEmLote, ExcecaoCalendario, Granularidade, ItemDeContrato,
  LinhaDeApontamento, LinhaDeAditivo, LinhaDeDeducao, LinhaParaApi, Precedencia,
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

// ---------------------------------------------------------------------------
// PDCA.3 — contrato, medição e retenção
// ---------------------------------------------------------------------------

export function useContratos(params: Params = {}, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.contratos.lista(params),
    queryFn: () => api.contratos.listar({ page_size: 100, ...params }),
    enabled: ativo,
    placeholderData: keepPreviousData,
  })
}

export function useContrato(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.contratos.detalhe(id ?? 0),
    queryFn: () => api.contratos.obter(id as number),
    enabled: id != null,
  })
}

/**
 * As frentes do **plano vigente** da obra, para o vínculo do item de contrato.
 *
 * Só do vigente, e só as **folhas**: medir contra uma sintética somaria o
 * avanço dos filhos duas vezes, e medir contra um plano em rascunho amarraria o
 * contrato a uma versão que ainda vai mudar.
 */
export function useAtividadesDoContrato(obraId: number | undefined) {
  return useQuery({
    queryKey: [...pdcaKeys.raiz, 'vinculos', 'atividades', obraId ?? 0],
    queryFn: async () => {
      const planos = await api.cronogramas.listar({
        obra: obraId, status: 'vigente', page_size: 1,
      })
      const vigente = planos.results?.[0]
      if (!vigente) return []
      const gantt = await api.cronogramas.gantt(vigente.cronograma_id)
      return (gantt.atividades ?? []).filter(a => !a.tem_filhos)
    },
    enabled: obraId != null,
  })
}

export function useItensDoContrato(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.contratos.itens(id ?? 0),
    queryFn: async () => (await api.itensContrato.listar(id as number)).results,
    enabled: id != null,
  })
}

export function useSaldoDoContrato(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.contratos.saldo(id ?? 0),
    queryFn: () => api.contratos.saldo(id as number),
    enabled: id != null,
  })
}

/** A prévia da medição. `enabled` só com as duas datas: pedir a proposta com
 *  metade do período traria uma janela que ninguém escolheu. */
export function useProposta(id: number | undefined, inicio: string, fim: string) {
  return useQuery({
    queryKey: pdcaKeys.contratos.proposta(id ?? 0, inicio, fim),
    queryFn: () => api.contratos.proposta(id as number, inicio, fim),
    enabled: id != null && !!inicio && !!fim,
    placeholderData: keepPreviousData,
  })
}

export function useMedicoes(params: Params = {}, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.medicoes.lista(params),
    queryFn: () => api.medicoes.listar({ page_size: 100, ...params }),
    enabled: ativo,
    placeholderData: keepPreviousData,
  })
}

export function useMedicao(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.medicoes.detalhe(id ?? 0),
    queryFn: () => api.medicoes.obter(id as number),
    enabled: id != null,
  })
}

/**
 * Toda escrita de medição invalida o **contrato inteiro**, e não só a medição.
 *
 * O motivo é o §4.9: saldo, retenção e acumulado não são colunas — são somas
 * feitas na leitura sobre todas as medições. Invalidar só o documento editado
 * deixaria o cabeçalho do contrato mostrando o saldo anterior ao lado da grade
 * já atualizada, que é dado errado com cara de certo.
 */
function useInvalidarContrato(contratoId: number | undefined) {
  const qc = useQueryClient()
  return () => {
    if (contratoId != null) {
      qc.invalidateQueries({ queryKey: pdcaKeys.contratos.detalhe(contratoId) })
      qc.invalidateQueries({ queryKey: pdcaKeys.contratos.saldo(contratoId) })
      qc.invalidateQueries({ queryKey: pdcaKeys.contratos.retencao(contratoId) })
    }
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'medicoes'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'medicao'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'liberacoes'] })
  }
}

export function useCriarContrato() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<Contrato>) => api.contratos.criar(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'contratos'] }),
  })
}

export function useAtualizarContrato(id: number | undefined) {
  const invalidar = useInvalidarContrato(id)
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<Contrato>) =>
      api.contratos.atualizar(id as number, payload),
    onSuccess: () => {
      invalidar()
      qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'contratos'] })
    },
  })
}

export function useExcluirContrato() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.contratos.excluir(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'contratos'] }),
  })
}

function useInvalidarItens(contratoId: number | undefined) {
  const qc = useQueryClient()
  const invalidarContrato = useInvalidarContrato(contratoId)
  return () => {
    if (contratoId != null) {
      qc.invalidateQueries({ queryKey: pdcaKeys.contratos.itens(contratoId) })
    }
    // A planilha contratual é o denominador do saldo — mexer nela muda o
    // cabeçalho, e a prévia de qualquer período passa a valer outra coisa.
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'contrato'] })
    invalidarContrato()
  }
}

export function useCriarItemDeContrato(contratoId: number | undefined) {
  const invalidar = useInvalidarItens(contratoId)
  return useMutation({
    mutationFn: (payload: Partial<ItemDeContrato>) => api.itensContrato.criar(payload),
    onSuccess: invalidar,
  })
}

export function useAtualizarItemDeContrato(contratoId: number | undefined) {
  const invalidar = useInvalidarItens(contratoId)
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<ItemDeContrato> }) =>
      api.itensContrato.atualizar(id, payload),
    onSuccess: invalidar,
  })
}

export function useExcluirItemDeContrato(contratoId: number | undefined) {
  const invalidar = useInvalidarItens(contratoId)
  return useMutation({
    mutationFn: (id: number) => api.itensContrato.excluir(id),
    onSuccess: invalidar,
  })
}

/**
 * **A grade da medição — uma chamada, uma verdade.**
 *
 * Substituiu a aritmética que a página fazia: ela montava
 * `saldo = contratado − já medido` a partir de uma prévia que só era buscada
 * quando *não* havia medição aberta, e quem entrasse pelo link direto de um
 * boletim via "já medido" **negativo**, saldo acima do contratado e a trava de
 * excesso desligada. Agora o contexto vem pronto do servidor.
 */
export function useContextoDeMedicao(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.medicoes.contexto(id ?? 0),
    queryFn: () => api.medicoes.contexto(id as number),
    enabled: id != null,
  })
}

/** De quando a próxima medição deveria falar — encadeada na anterior. */
export function usePeriodoSugerido(contratoId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.contratos.periodo(contratoId ?? 0),
    queryFn: () => api.contratos.periodoSugerido(contratoId as number),
    enabled: contratoId != null,
  })
}

/** O cabeçalho do rascunho — custo reembolsável e observação. */
export function useSalvarCabecalho(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, ...payload }: {
      id: number; custo_reembolsavel?: string | null; observacao?: string
    }) => api.medicoes.cabecalho(id, payload),
    onSuccess: invalidar,
  })
}

/** As deduções do rascunho — o que sai do bruto e **não volta**. */
export function useSalvarDeducoes(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, deducoes }: { id: number; deducoes: LinhaDeDeducao[] }) =>
      api.medicoes.deducoes(id, deducoes),
    onSuccess: invalidar,
  })
}

// ---------------------------------------------------------------------------
// PDCA.4 — aditivo
// ---------------------------------------------------------------------------

export function useAditivos(params: Params = {}, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.aditivos.lista(params),
    queryFn: () => api.aditivos.listar({ page_size: 100, ...params }),
    enabled: ativo,
    placeholderData: keepPreviousData,
  })
}

export function useAditivo(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.aditivos.detalhe(id ?? 0),
    queryFn: () => api.aditivos.obter(id as number),
    enabled: id != null,
  })
}

/**
 * Toda escrita de aditivo invalida o **contrato inteiro**, e mais do que a
 * medição: o aditivo aprovado muda a *régua* — o contratado atual, o preço
 * vigente, a planilha (item novo) e até a vigência. Invalidar só o documento
 * deixaria a grade de medição medindo contra o saldo de ontem.
 */
function useInvalidarAditivo(contratoId: number | undefined) {
  const qc = useQueryClient()
  const invalidarContrato = useInvalidarContrato(contratoId)
  return () => {
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'aditivos'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'aditivo'] })
    if (contratoId != null) {
      qc.invalidateQueries({ queryKey: pdcaKeys.contratos.itens(contratoId) })
    }
    invalidarContrato()
  }
}

export function useAbrirAditivo(contratoId: number | undefined) {
  const invalidar = useInvalidarAditivo(contratoId)
  return useMutation({
    mutationFn: (payload: {
      contrato: number
      objeto: string
      justificativa: string
      data_assinatura?: string | null
      nova_data_fim?: string | null
      itens?: LinhaDeAditivo[]
    }) => api.aditivos.abrir(payload),
    onSuccess: invalidar,
  })
}

export function useSalvarItensDoAditivo(contratoId: number | undefined) {
  const invalidar = useInvalidarAditivo(contratoId)
  return useMutation({
    mutationFn: ({ id, itens }: { id: number; itens: LinhaDeAditivo[] }) =>
      api.aditivos.itens(id, itens),
    onSuccess: invalidar,
  })
}

export function useSubmeterAditivo(contratoId: number | undefined) {
  const invalidar = useInvalidarAditivo(contratoId)
  return useMutation({
    mutationFn: (id: number) => api.aditivos.submeter(id),
    onSuccess: invalidar,
  })
}

export function useAtestarAditivo(contratoId: number | undefined) {
  const invalidar = useInvalidarAditivo(contratoId)
  return useMutation({
    mutationFn: ({ id, aprovar, observacao }: {
      id: number; aprovar: boolean; observacao?: string
    }) => api.aditivos.atestar(id, aprovar, observacao ?? ''),
    onSuccess: invalidar,
  })
}

export function useCancelarAditivo(contratoId: number | undefined) {
  const invalidar = useInvalidarAditivo(contratoId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo?: string }) =>
      api.aditivos.cancelar(id, motivo ?? ''),
    onSuccess: invalidar,
  })
}

export function useExcluirAditivo(contratoId: number | undefined) {
  const invalidar = useInvalidarAditivo(contratoId)
  return useMutation({
    mutationFn: (id: number) => api.aditivos.excluir(id),
    onSuccess: invalidar,
  })
}

export function useAbrirMedicao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: (payload: {
      contrato: number; inicio: string; fim: string
      linhas?: LinhaParaApi[]
      custo_reembolsavel?: string | null
      observacao?: string
    }) => api.medicoes.abrir(payload),
    onSuccess: invalidar,
  })
}

export function useSalvarLinhas(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, linhas }: { id: number; linhas: LinhaParaApi[] }) =>
      api.medicoes.linhas(id, linhas),
    onSuccess: invalidar,
  })
}

export function useSubmeterMedicao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, observacao }: { id: number; observacao?: string }) =>
      api.medicoes.submeter(id, observacao ?? ''),
    onSuccess: invalidar,
  })
}

export function useAtestarMedicao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, aprovar, observacao }: {
      id: number; aprovar: boolean; observacao?: string
    }) => api.medicoes.atestar(id, aprovar, observacao ?? ''),
    onSuccess: invalidar,
  })
}

export function useRetificarMedicao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.medicoes.retificar(id, motivo),
    onSuccess: invalidar,
  })
}

export function useCancelarMedicao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo?: string }) =>
      api.medicoes.cancelar(id, motivo ?? ''),
    onSuccess: invalidar,
  })
}

export function useExcluirMedicao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: (id: number) => api.medicoes.excluir(id),
    onSuccess: invalidar,
  })
}

export function useRetencao(contratoId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.contratos.retencao(contratoId ?? 0),
    queryFn: () => api.contratos.retencao(contratoId as number),
    enabled: contratoId != null,
  })
}

export function useLiberarRetencao(contratoId: number | undefined) {
  const invalidar = useInvalidarContrato(contratoId)
  return useMutation({
    mutationFn: (payload: { valor: string; data: string; condicao_atendida: string }) =>
      api.contratos.liberarRetencao(contratoId as number, payload),
    onSuccess: invalidar,
  })
}

export function useLiberacoes(params: Params = {}, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.liberacoes(params),
    queryFn: async () => (await api.liberacoes.listar(params)).results,
    enabled: ativo,
  })
}

/** Busca server-side, como todo select novo desde o F2. A normalização de forma
 *  (lista crua × página) mora no cliente de API — ver a nota lá. */
export function useFornecedoresOpt(busca: string, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.vinculos.fornecedores(busca),
    queryFn: () => api.fornecedoresOpt(busca),
    enabled: ativo,
    placeholderData: keepPreviousData,
  })
}
