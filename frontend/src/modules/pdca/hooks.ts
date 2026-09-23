import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api/pdcaApi'
import { pdcaKeys } from './api/queryKeys'
import type {
  Atividade, CausaNaoCumprimento, Cronograma, ItemProgramacao,
  JulgamentoDeItem, Restricao,
} from './types'

export function useStatusModulo() {
  return useQuery({ queryKey: pdcaKeys.status(), queryFn: api.getStatusModulo, retry: false })
}

export function useObras() {
  return useQuery({ queryKey: pdcaKeys.obras(), queryFn: api.listarObras })
}

/* --- O cockpit ---------------------------------------------------------- */

/** B1 — a carteira. Uma leitura por abertura da porta de fora. */
export function useCarteira() {
  return useQuery({
    queryKey: pdcaKeys.carteira(),
    queryFn: () => api.cockpit.carteira(),
  })
}

/** B2 + B6 — fila, pulso e o que mudou, numa chamada. */
export function useHoje(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.hoje(obraId ?? 0),
    queryFn: () => api.cockpit.hoje(obraId as number),
    enabled: obraId != null,
  })
}

/** B4 — a busca única.
 *
 *  **O piso de duas letras é do servidor**, e a tela lê a resposta em vez de
 *  reimplementar a condição (convenções §11): abaixo dele o `enabled` nem
 *  dispara, e a frase que aparece é a que a API devolveria. */
export function useBusca(termo: string, obraId: number | undefined) {
  const limpo = termo.trim()
  return useQuery({
    queryKey: pdcaKeys.busca(limpo, obraId),
    queryFn: () => api.cockpit.busca(limpo, obraId),
    enabled: limpo.length >= 2,
    placeholderData: keepPreviousData,
  })
}

export function useCronogramasDaObra(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.daObra(obraId ?? 0),
    queryFn: () => api.cronogramas.listar({ obra: obraId }),
    enabled: obraId != null,
  })
}

/** O plano que a obra mostra por padrão: o vigente; na falta dele, o rascunho
 *  de maior versão. Obra sem plano nenhum devolve `undefined`, e a tela oferece
 *  o caminho de criar — estado vazio que pede ação traz o botão. */
export function usePlanoCorrente(obraId: number | undefined) {
  const consulta = useCronogramasDaObra(obraId)
  const lista = consulta.data ?? []
  const vigente = lista.find((c) => c.status === 'vigente')
  const rascunho = [...lista]
    .filter((c) => c.status === 'rascunho')
    .sort((a, b) => b.versao - a.versao)[0]
  return { ...consulta, plano: vigente ?? rascunho, planos: lista }
}

export function useGantt(cronogramaId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.gantt(cronogramaId ?? 0),
    queryFn: () => api.cronogramas.gantt(cronogramaId as number),
    enabled: cronogramaId != null,
    placeholderData: keepPreviousData,
  })
}

export function useLinhaDeBalanco(cronogramaId: number | undefined, ativo: boolean) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.balanco(cronogramaId ?? 0),
    queryFn: () => api.cronogramas.linhaDeBalanco(cronogramaId as number),
    enabled: cronogramaId != null && ativo,
  })
}

export function useLocais(obraId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.locais(obraId ?? 0),
    queryFn: () => api.locais.listar(obraId as number),
    enabled: obraId != null && ativo,
  })
}

export function useCalendarios(obraId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.calendarios(obraId ?? 0),
    queryFn: () => api.calendarios.listar(obraId as number),
    enabled: obraId != null && ativo,
  })
}

function useInvalidarPlano(cronogramaId: number | undefined) {
  const qc = useQueryClient()
  return () => {
    if (cronogramaId != null) {
      qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.gantt(cronogramaId) })
      qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.balanco(cronogramaId) })
    }
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
  }
}

export function useSalvarAtividade(cronogramaId: number | undefined) {
  const invalidar = useInvalidarPlano(cronogramaId)
  return useMutation({
    mutationFn: ({ id, corpo }: { id: number; corpo: Partial<Atividade> }) =>
      api.atividades.atualizar(id, corpo),
    onSuccess: invalidar,
  })
}

export function useCalcularPlano(cronogramaId: number | undefined) {
  const invalidar = useInvalidarPlano(cronogramaId)
  return useMutation({
    mutationFn: (id: number) => api.cronogramas.calcular(id),
    onSuccess: invalidar,
  })
}

export function usePublicarPlano(cronogramaId: number | undefined) {
  const invalidar = useInvalidarPlano(cronogramaId)
  return useMutation({
    mutationFn: (id: number) => api.cronogramas.publicar(id),
    onSuccess: invalidar,
  })
}

export function useReplanejar(cronogramaId: number | undefined) {
  const invalidar = useInvalidarPlano(cronogramaId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.cronogramas.replanejar(id, motivo),
    onSuccess: invalidar,
  })
}

export function useCriarPlano() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (corpo: Partial<Cronograma>) => api.cronogramas.criar(corpo),
    onSuccess: () => qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() }),
  })
}


/* --- SEMANA: o Last Planner ---------------------------------------------- */

/** A programação daquela semana, **sem abri-la**.
 *
 *  Abrir é escrita (semeia o catálogo de causas e cria o documento), e uma
 *  leitura não pode ter esse efeito: navegar seis semanas para trás criaria
 *  seis programações vazias que ninguém pediu. Quem abre é o botão. */
export function useSemana(obraId: number | undefined, inicio: string) {
  return useQuery({
    queryKey: pdcaKeys.semana.daObra(obraId ?? 0, inicio),
    queryFn: () => api.programacoes.daSemana(obraId as number, inicio),
    enabled: obraId != null && !!inicio,
    placeholderData: keepPreviousData,
  })
}

export function useItensDaSemana(programacaoId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.semana.itens(programacaoId ?? 0),
    queryFn: () => api.itensProgramacao.listar(programacaoId as number),
    enabled: programacaoId != null,
  })
}

/** A área de rascunho. Só busca enquanto o quadro aceita cartão novo — pedir
 *  candidatos de uma semana já comprometida seria oferecer o que a regra do
 *  método recusa. */
export function useCandidatos(programacaoId: number | undefined, ativo: boolean) {
  return useQuery({
    queryKey: pdcaKeys.semana.candidatos(programacaoId ?? 0),
    queryFn: () => api.programacoes.candidatos(programacaoId as number),
    enabled: programacaoId != null && ativo,
  })
}

export function useRestricoes(obraId: number | undefined, status = 'aberta') {
  return useQuery({
    queryKey: pdcaKeys.restricoes(obraId ?? 0, status),
    queryFn: () => api.restricoes.listar(obraId as number, status),
    enabled: obraId != null,
  })
}

export function useCatalogoDeCausas(ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.catalogoDeCausas(),
    queryFn: () => api.causas.listar(),
    enabled: ativo,
    staleTime: 5 * 60 * 1000,
  })
}

export function useSeriePpc(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.semana.ppc(obraId ?? 0),
    queryFn: () => api.programacoes.ppc(obraId as number),
    enabled: obraId != null,
  })
}

export function useRankingDeCausas(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.semana.causas(obraId ?? 0),
    queryFn: () => api.programacoes.ranking(obraId as number),
    enabled: obraId != null,
  })
}

/** **Um só invalidador para a semana inteira**, e é deliberado: encerrar mexe
 *  no PPC, no ranking, nos cartões, na semana seguinte (pelo arrasto), na fila
 *  do cockpit **e na frente de quem está no canteiro**. Invalidar só o que o
 *  verbo tocou faria a tela mostrar o índice novo ao lado da série velha — ou,
 *  pior, o encarregado destravar um serviço no celular e a trava continuar lá.
 *
 *  Por **prefixo**, e não por chave exata: a mesma trava aparece na esteira da
 *  obra e na frente de uma pessoa, e quem a remove nem sempre sabe as duas
 *  chaves. Uma lista que deixa de ser recarregada porque o invalidador não
 *  conhecia o consumidor é a forma de erro que só aparece na mão do usuário. */
function useInvalidarSemana(obraId: number | undefined) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: pdcaKeys.semana.raiz() })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'restricoes'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'minhas-frentes'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'hoje'] })
    if (obraId != null) qc.invalidateQueries({ queryKey: pdcaKeys.hoje(obraId) })
    qc.invalidateQueries({ queryKey: pdcaKeys.carteira() })
  }
}

export function useAbrirSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (semana: string) =>
      api.programacoes.abrir(obraId as number, semana),
    onSuccess: invalidar,
  })
}

export function usePuxarParaOQuadro(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (corpo: Partial<ItemProgramacao>) =>
      api.itensProgramacao.criar(corpo),
    onSuccess: invalidar,
  })
}

export function useSalvarCompromisso(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, corpo }: { id: number; corpo: Partial<ItemProgramacao> }) =>
      api.itensProgramacao.atualizar(id, corpo),
    onSuccess: invalidar,
  })
}

export function useDevolverCompromisso(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (id: number) => api.itensProgramacao.remover(id),
    onSuccess: invalidar,
  })
}

export function useComprometerSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (id: number) => api.programacoes.comprometer(id),
    onSuccess: invalidar,
  })
}

export function useJulgarSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, julgamentos }: { id: number; julgamentos: JulgamentoDeItem[] }) =>
      api.programacoes.julgar(id, julgamentos),
    onSuccess: invalidar,
  })
}

export function useEncerrarSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, motivo, arrastar }:
    { id: number; motivo?: string; arrastar?: boolean }) =>
      api.programacoes.encerrar(id, { motivo, arrastar }),
    onSuccess: invalidar,
  })
}

export function useReabrirSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.programacoes.reabrir(id, motivo),
    onSuccess: invalidar,
  })
}

export function useArrastarPendentes(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (id: number) => api.programacoes.arrastar(id),
    onSuccess: invalidar,
  })
}

export function useCriarRestricao(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (corpo: Partial<Restricao>) => api.restricoes.criar(corpo),
    onSuccess: invalidar,
  })
}

export function useRemoverRestricao(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, nota }: { id: number; nota: string }) =>
      api.restricoes.remover(id, nota),
    onSuccess: invalidar,
  })
}

export function useGerarDemandaDeCompra(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, quantidade, unidade }:
    { id: number; quantidade?: string | null; unidade?: string }) =>
      api.restricoes.gerarDemanda(id, { quantidade, unidade }),
    onSuccess: invalidar,
  })
}

/** A ata da reunião. `PATCH` existe **só** para ela — o resto do documento da
 *  semana muda por verbo, que é a mesma forma da medição e do aditivo. */
export function useAnotarSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: ({ id, nota }: { id: number; nota: string }) =>
      api.programacoes.anotar(id, nota),
    onSuccess: invalidar,
  })
}

export function useCriarCausa() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (corpo: Partial<CausaNaoCumprimento>) => api.causas.criar(corpo),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: pdcaKeys.catalogoDeCausas() }),
  })
}

/* --- CAMPO: a frente de quem está no canteiro ---------------------------- */

/** B5 — o que está no meu nome, nesta semana, em qualquer obra. */
export function useMinhasFrentes(
  { como, obraId }: { como?: string; obraId?: number } = {},
) {
  return useQuery({
    queryKey: pdcaKeys.minhasFrentes(como ?? '', obraId),
    queryFn: () => api.cockpit.minhasFrentes({ como, obraId }),
  })
}

/** O que já foi apontado nesta atividade dentro da semana — é o que permite ao
 *  campo estornar o próprio erro num toque em vez de pedir ao escritório. */
export function useApontamentosDaSemana(
  atividade: number | undefined, de: string, ate: string,
) {
  return useQuery({
    queryKey: [...pdcaKeys.raiz, 'apontamentos', atividade ?? 0, de, ate] as const,
    queryFn: () => api.apontamentos.doItem(atividade as number, de, ate),
    enabled: atividade != null && !!de && !!ate,
  })
}

/** **Invalida a frente, a semana e o pulso**: o apontamento do campo é o número
 *  que o cartão do quadro mostra ao lado do prometido, que o avanço do plano
 *  soma e que o pulso da obra publica. Qualquer um deles ficaria velho se só a
 *  tela que escreveu recarregasse. */
function useInvalidarApontamento() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'apontamentos'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'minhas-frentes'] })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'hoje'] })
    qc.invalidateQueries({ queryKey: pdcaKeys.semana.raiz() })
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
    qc.invalidateQueries({ queryKey: pdcaKeys.carteira() })
  }
}

export function useApontar() {
  const invalidar = useInvalidarApontamento()
  return useMutation({
    mutationFn: (corpo: Parameters<typeof api.apontamentos.criar>[0]) =>
      api.apontamentos.criar(corpo),
    onSuccess: invalidar,
  })
}

export function useEstornarApontamento() {
  const invalidar = useInvalidarApontamento()
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.apontamentos.estornar(id, motivo),
    onSuccess: invalidar,
  })
}
