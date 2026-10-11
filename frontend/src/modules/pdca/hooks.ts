import { useMemo } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api/pdcaApi'
import * as montagem from './api/montagemApi'
import { antecedencias, suprimentos, type AntecedenciaDeCompra } from './api/suprimentosApi'
import { pdcaKeys } from './api/queryKeys'
import type {
  Atividade, CausaNaoCumprimento, Cronograma, ItemContrato, ItemProgramacao,
  JulgamentoDeItem, LocalObra, Restricao,
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

/** O plano que o posto **Plano** abre — que não é o mesmo da execução.
 *
 *  A Semana e o Hoje trabalham sobre o vigente (o combinado). Quem planeja
 *  trabalha sobre o **rascunho em montagem**: depois de replanejar, abrir o
 *  vigente congelado fazia a pessoa achar que a versão nova não existia,
 *  replanejar de novo e juntar rascunhos (achado no teste do dono, 09/10/2026).
 *  Padrão: o rascunho mais novo, se for mais novo que o vigente; senão, o
 *  vigente. `escolhido` (do seletor de versão) vence o padrão. */
export function usePlanoEmEdicao(obraId: number | undefined, escolhido: number | null) {
  const consulta = useCronogramasDaObra(obraId)
  const lista = useMemo(
    () => [...(consulta.data ?? [])].sort((a, b) => b.versao - a.versao),
    [consulta.data],
  )
  const vigente = lista.find((c) => c.status === 'vigente')
  const rascunho = lista.find((c) => c.status === 'rascunho')
  const padrao = rascunho && (!vigente || rascunho.versao > vigente.versao) ? rascunho : (vigente ?? rascunho)
  const plano = lista.find((c) => c.cronograma_id === escolhido) ?? padrao
  return { ...consulta, plano, vigente, rascunho, planos: lista }
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

/** Criar locais em lote (um, ou "Trecho 1…N") e remover — a árvore e o Gantt
 *  (local da atividade) recarregam juntos. */
export function useEditarLocais(obraId: number) {
  const qc = useQueryClient()
  const recarregar = () => {
    qc.invalidateQueries({ queryKey: pdcaKeys.locais(obraId) })
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
  }
  return {
    criar: useMutation({
      mutationFn: async (lista: Partial<LocalObra>[]) => {
        for (const corpo of lista) await api.locais.criar({ ...corpo, obra: obraId })
      },
      onSettled: recarregar,
    }),
    remover: useMutation({ mutationFn: (id: number) => api.locais.remover(id), onSettled: recarregar }),
  }
}

/** A fila "comprar até DD/MM" do plano — insumo, quantidade, a comprar. */
export function useNecessidadeDeMaterial(cronogramaId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.suprimentos(cronogramaId ?? 0),
    queryFn: () => suprimentos.necessidade(cronogramaId as number),
    enabled: cronogramaId != null && ativo,
  })
}

/** O dinheiro dos quatro módulos dentro do plano, por etapa e atividade. */
export function useCustoDoPlano(cronogramaId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.custo(cronogramaId ?? 0),
    queryFn: () => suprimentos.custo(cronogramaId as number),
    enabled: cronogramaId != null && ativo,
  })
}

/** Gerar a demanda muda o "em demanda" da fila — e a fila do Suprimentos. */
export function useGerarDemandaDoPlano(cronogramaId: number | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (corpo: { insumos?: string[]; ate?: string | null }) =>
      suprimentos.gerarDemanda(cronogramaId as number, corpo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
      qc.invalidateQueries({ queryKey: ['scm'] })
    },
  })
}

export function useAntecedencias(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.antecedencias(obraId ?? 0),
    queryFn: () => antecedencias.listar(obraId as number),
    enabled: obraId != null,
  })
}

export function useDefinirAntecedencia(obraId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ item, dias, existente }: { item: number | null; dias: number | null; existente?: AntecedenciaDeCompra }) =>
      antecedencias.definir(obraId, item, dias, existente),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: pdcaKeys.antecedencias(obraId) })
      qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
    },
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

/** Descarta um rascunho (o vigente o servidor recusa — é substituído, não apagado). */
export function useDescartarRascunho() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.cronogramas.descartar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() }),
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

export function useRestricoesDaAtividade(atividadeId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.restricoesDaAtividade(atividadeId ?? 0),
    queryFn: () => api.restricoes.daAtividade(atividadeId as number),
    enabled: atividadeId != null,
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
    // Remover a restrição que uma ocorrência abriu libera a frente — e é o
    // que destrava o encerramento dela no posto da segurança.
    qc.invalidateQueries({ queryKey: pdcaKeys.seguranca.raiz() })
    qc.invalidateQueries({ queryKey: pdcaKeys.qualidade.raiz() })
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

export function usePedirMaterialDaSemana(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: number) => api.itensProgramacao.pedirMaterial(itemId),
    onSuccess: () => { invalidar(); qc.invalidateQueries({ queryKey: ['sil'] }) },
  })
}

export function useReabrirRestricao(obraId: number | undefined) {
  const invalidar = useInvalidarSemana(obraId)
  return useMutation({
    mutationFn: (id: number) => api.restricoes.reabrir(id),
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

/* --- MEDIÇÃO: o contrato, o boletim e o dinheiro ------------------------- */

/** B3 — a carteira de contratos com saldo **e** a fila do dinheiro, numa
 *  leitura. É o que a página do posto pede ao abrir. */
export function usePostoDaMedicao(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.medicao.posto(obraId ?? 0),
    queryFn: () => api.posto.medicao(obraId as number),
    enabled: obraId != null,
    placeholderData: keepPreviousData,
  })
}

export function useCriarContrato(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (corpo: Record<string, unknown>) => api.contratos.criar(corpo),
    onSuccess: invalidar,
  })
}

export function useItensDoContrato(contratoId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.medicao.itensDoContrato(contratoId ?? 0),
    queryFn: () => api.itensDeContrato.listar(contratoId as number),
    enabled: contratoId != null && ativo,
  })
}

/** A ficha do contrato. Mora sob a raiz da medição: todo gesto do dinheiro a
 *  invalida junto (`useInvalidarDinheiro`). */
export function useFichaDoContrato(contratoId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.medicao.ficha(contratoId ?? 0),
    queryFn: () => api.contratos.ficha(contratoId as number),
    enabled: contratoId != null && ativo,
  })
}

export function useContratoObra(contratoId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: [...pdcaKeys.medicao.ficha(contratoId ?? 0), 'cadastro'] as const,
    queryFn: () => api.contratos.obter(contratoId as number),
    enabled: contratoId != null && ativo,
  })
}

export function useBoletins(contratoId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.medicao.boletins(contratoId ?? 0),
    queryFn: () => api.medicoes.doContrato(contratoId as number),
    enabled: contratoId != null,
  })
}

/** A grade de um boletim aberto. **Uma chamada, uma verdade** — traz
 *  contratado, aditivos, acumulado anterior, proposta, saldo, a memória de
 *  cálculo de cada linha e os totais congelados. */
export function useContextoDaMedicao(medicaoId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.medicao.contexto(medicaoId ?? 0),
    queryFn: () => api.medicoes.contexto(medicaoId as number),
    enabled: medicaoId != null,
  })
}

/** O documento inteiro (deduções, título do ERP, assinaturas). Separado do
 *  contexto porque a grade e o documento mudam em momentos diferentes. */
export function useDocumentoDaMedicao(medicaoId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.medicao.documento(medicaoId ?? 0),
    queryFn: () => api.medicoes.obter(medicaoId as number),
    enabled: medicaoId != null,
  })
}

export function useAditivos(contratoId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.medicao.aditivos(contratoId ?? 0),
    queryFn: () => api.aditivos.doContrato(contratoId as number),
    enabled: contratoId != null && ativo,
  })
}

export function useLiberacoes(contratoId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.medicao.liberacoes(contratoId ?? 0),
    queryFn: () => api.liberacoes.doContrato(contratoId as number),
    enabled: contratoId != null && ativo,
  })
}

/** A prévia — o que se mediria neste período, **sem gravar nada**.
 *
 *  Só busca quando alguém pediu (`ativo`): rodar a proposta a cada tecla do
 *  seletor de período faria o servidor recalcular o avanço da obra inteira a
 *  cada dígito. */
export function usePrevia(
  contratoId: number | undefined, inicio: string, fim: string, ativo: boolean,
) {
  return useQuery({
    queryKey: pdcaKeys.medicao.previa(contratoId ?? 0, inicio, fim),
    queryFn: () =>
      api.contratos.propostaDeMedicao(contratoId as number, inicio, fim),
    enabled: contratoId != null && !!inicio && !!fim && ativo,
  })
}

/** **Um só invalidador para o dinheiro inteiro**, e é deliberado.
 *
 *  Submeter um boletim muda o saldo do contrato (o medido sai do rascunho e
 *  entra na escada), a fila do posto, a fila do dia da obra e a carteira da
 *  diretoria. Aprovar muda tudo isso **e gera um título no ERP**. Invalidar só
 *  a chave que o verbo tocou mostraria o saldo velho ao lado do boletim novo —
 *  e, na medição, os dois números na mesma tela.
 *
 *  Por **prefixo**, como o da semana: a mesma medição aparece no documento, na
 *  grade, na lista do contrato e na fila, e quem a submete não conhece as
 *  quatro chaves. */
function useInvalidarDinheiro(obraId: number | undefined) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: pdcaKeys.medicao.raiz() })
    if (obraId != null) qc.invalidateQueries({ queryKey: pdcaKeys.hoje(obraId) })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'hoje'] })
    qc.invalidateQueries({ queryKey: pdcaKeys.carteira() })
  }
}

export function useSalvarItemDoContrato(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, corpo }: { id: number; corpo: Partial<ItemContrato> }) =>
      api.itensDeContrato.atualizar(id, corpo),
    onSuccess: invalidar,
  })
}

export function useCriarItemDoContrato(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (corpo: Partial<ItemContrato>) =>
      api.itensDeContrato.criar(corpo),
    onSuccess: invalidar,
  })
}

export function useRemoverItemDoContrato(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (id: number) => api.itensDeContrato.remover(id),
    onSuccess: invalidar,
  })
}

export function useAbrirMedicao(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (corpo: Parameters<typeof api.medicoes.abrir>[0]) =>
      api.medicoes.abrir(corpo),
    onSuccess: invalidar,
  })
}

export function useSalvarGrade(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, linhas }: {
      id: number
      linhas: Parameters<typeof api.medicoes.linhas>[1]
    }) => api.medicoes.linhas(id, linhas),
    onSuccess: invalidar,
  })
}

export function useSalvarDeducoes(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, deducoes }: {
      id: number
      deducoes: Parameters<typeof api.medicoes.deducoes>[1]
    }) => api.medicoes.deducoes(id, deducoes),
    onSuccess: invalidar,
  })
}

export function useSalvarCabecalho(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, corpo }: {
      id: number
      corpo: { custo_reembolsavel?: string | null; observacao?: string }
    }) => api.medicoes.cabecalho(id, corpo),
    onSuccess: invalidar,
  })
}

export function useSubmeterMedicao(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, observacao }: { id: number; observacao?: string }) =>
      api.medicoes.submeter(id, observacao ?? ''),
    onSuccess: invalidar,
  })
}

export function useAtestarMedicao(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, aprovar, observacao }: {
      id: number; aprovar: boolean; observacao?: string
    }) => api.medicoes.atestar(id, { aprovar, observacao }),
    onSuccess: invalidar,
  })
}

export function useCancelarMedicao(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.medicoes.cancelar(id, motivo),
    onSuccess: invalidar,
  })
}

export function useRetificarMedicao(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.medicoes.retificar(id, motivo),
    onSuccess: invalidar,
  })
}

export function useAbrirAditivo(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (corpo: Parameters<typeof api.aditivos.abrir>[0]) =>
      api.aditivos.abrir(corpo),
    onSuccess: invalidar,
  })
}

/** **Grava o aditivo inteiro** — abre (novo) ou reescreve cabeçalho e linhas
 *  (rascunho). Um gesto só na tela, como salvar um contrato. */
export function useSalvarAditivo(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: async ({ id, contrato, cabecalho, itens }: {
      id: number | null
      contrato: number
      cabecalho: import('./api/pdcaApi').CabecalhoDoAditivo
      itens: import('./types').LinhaDeAditivoEntrada[]
    }) => {
      if (id == null) return api.aditivos.abrir({ contrato, ...cabecalho, itens })
      await api.aditivos.cabecalho(id, cabecalho)
      await api.aditivos.itens(id, itens)
      return api.aditivos.obter(id)
    },
    onSuccess: invalidar,
  })
}

export function useExcluirAditivo(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (id: number) => api.aditivos.excluir(id),
    onSuccess: invalidar,
  })
}

export function useCancelarAditivo(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.aditivos.cancelar(id, motivo),
    onSuccess: invalidar,
  })
}

export function useSubmeterAditivo(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (id: number) => api.aditivos.submeter(id),
    onSuccess: invalidar,
  })
}

export function useAtestarAditivo(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, aprovar, observacao }: {
      id: number; aprovar: boolean; observacao?: string
    }) => api.aditivos.atestar(id, { aprovar, observacao }),
    onSuccess: invalidar,
  })
}

export function useLiberarRetencao(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: ({ id, corpo }: {
      id: number
      corpo: { valor: string; data: string; condicao_atendida: string }
    }) => api.contratos.liberarRetencao(id, corpo),
    onSuccess: invalidar,
  })
}

/* --- QUALIDADE (F.5) ----------------------------------------------------- */

/** O que um verbo da qualidade toca, **tudo de uma vez**: a NC aparece no
 *  cartão da semana, na fila do dia, na carteira e na frente de campo; gerar
 *  restrição a partir dela trava o quadro. Invalidar só a chave do verbo
 *  deixaria o posto dizendo uma coisa e o `HOJE` outra. */
function useInvalidarQualidade() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: pdcaKeys.qualidade.raiz() })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'hoje'] })
    qc.invalidateQueries({ queryKey: pdcaKeys.carteira() })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'minhas-frentes'] })
    qc.invalidateQueries({ queryKey: pdcaKeys.semana.raiz() })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'restricoes'] })
  }
}

export function usePostoDaQualidade(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.posto(obraId ?? 0),
    queryFn: () => api.posto.qualidade(obraId as number),
    enabled: obraId != null,
    placeholderData: keepPreviousData,
  })
}

export function useNcs(obraId: number | undefined, status: string, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.ncs(obraId ?? 0, status),
    queryFn: () => api.ncs.daObra(obraId as number, status ? { status } : {}),
    enabled: obraId != null && ativo,
  })
}

export function useNc(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.nc(id ?? 0),
    queryFn: () => api.ncs.obter(id as number),
    enabled: id != null,
  })
}

export function useFichas(obraId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.fichas(obraId ?? 0),
    queryFn: () => api.verificacoes.daObra(obraId as number),
    enabled: obraId != null && ativo,
  })
}

export function useFicha(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.ficha(id ?? 0),
    queryFn: () => api.verificacoes.obter(id as number),
    enabled: id != null,
  })
}

export function useItensDaFicha(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.itensDaFicha(id ?? 0),
    queryFn: () => api.verificacoes.itens(id as number),
    enabled: id != null,
  })
}

export function useModelos(todos: boolean, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.modelos(todos),
    queryFn: () => api.modelos.listar(todos ? {} : { ativo: true }),
    enabled: ativo,
  })
}

export function useModelo(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.qualidade.modelo(id ?? 0),
    queryFn: () => api.modelos.obter(id as number),
    enabled: id != null,
  })
}

/** Uma mutação da qualidade: o verbo e o invalidador único. */
function useVerboDaQualidade<A, R>(verbo: (args: A) => Promise<R>) {
  const invalidar = useInvalidarQualidade()
  return useMutation({ mutationFn: verbo, onSuccess: invalidar })
}

export const useAplicarFicha = () =>
  useVerboDaQualidade((corpo: Parameters<typeof api.verificacoes.aplicar>[0]) =>
    api.verificacoes.aplicar(corpo))

export const useResponderItem = () =>
  useVerboDaQualidade(({ id, corpo, foto }: {
    id: number
    corpo: Parameters<typeof api.verificacoes.responder>[1]
    foto?: File | null
  }) => api.verificacoes.responder(id, corpo, foto))

export const useConcluirFicha = () =>
  useVerboDaQualidade((id: number) => api.verificacoes.concluir(id))

export const useAbrirNcsDosReprovados = () =>
  useVerboDaQualidade((id: number) => api.verificacoes.abrirNcs(id))

export const useAbrirNc = () =>
  useVerboDaQualidade(({ corpo, foto }: {
    corpo: Parameters<typeof api.ncs.abrir>[0]; foto?: File | null
  }) => api.ncs.abrir(corpo, foto))

export const useCriarPlanoDeAcao = () =>
  useVerboDaQualidade((corpo: Parameters<typeof api.planosAcao.criar>[0]) =>
    api.planosAcao.criar(corpo))

export const useConcluirPlanoDeAcao = () =>
  useVerboDaQualidade((id: number) => api.planosAcao.concluir(id))

export const useRegistrarEficacia = () =>
  useVerboDaQualidade(({ id, corpo }: {
    id: number; corpo: Parameters<typeof api.ncs.eficacia>[1]
  }) => api.ncs.eficacia(id, corpo))

export const useEncerrarNc = () =>
  useVerboDaQualidade(({ id, nota }: { id: number; nota: string }) =>
    api.ncs.encerrar(id, nota))

export const useCancelarNc = () =>
  useVerboDaQualidade(({ id, motivo }: { id: number; motivo: string }) =>
    api.ncs.cancelar(id, motivo))

export const useGerarRestricaoDaNc = () =>
  useVerboDaQualidade(({ id, corpo }: {
    id: number; corpo: Parameters<typeof api.ncs.gerarRestricao>[1]
  }) => api.ncs.gerarRestricao(id, corpo))

export const useCriarModelo = () =>
  useVerboDaQualidade((corpo: Parameters<typeof api.modelos.criar>[0]) =>
    api.modelos.criar(corpo))

export const useAtualizarModelo = () =>
  useVerboDaQualidade(({ id, corpo }: {
    id: number; corpo: Parameters<typeof api.modelos.atualizar>[1]
  }) => api.modelos.atualizar(id, corpo))

export const useExcluirModelo = () =>
  useVerboDaQualidade((id: number) => api.modelos.excluir(id))

export const useDuplicarModelo = () =>
  useVerboDaQualidade(({ id, codigo, nome }: { id: number; codigo: string; nome?: string }) =>
    api.modelos.duplicar(id, codigo, nome))

export const useCriarItemDoModelo = () =>
  useVerboDaQualidade((corpo: Parameters<typeof api.modelos.criarItem>[0]) =>
    api.modelos.criarItem(corpo))

export const useAtualizarItemDoModelo = () =>
  useVerboDaQualidade(({ id, corpo }: {
    id: number; corpo: Parameters<typeof api.modelos.atualizarItem>[1]
  }) => api.modelos.atualizarItem(id, corpo))

export const useExcluirItemDoModelo = () =>
  useVerboDaQualidade((id: number) => api.modelos.excluirItem(id))

/* --- SEGURANÇA (F.5) ----------------------------------------------------- */

function useInvalidarSeguranca() {
  const qc = useQueryClient()
  const qualidade = useInvalidarQualidade()
  return () => {
    qc.invalidateQueries({ queryKey: pdcaKeys.seguranca.raiz() })
    qualidade()
  }
}

export function usePostoDaSeguranca(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.seguranca.posto(obraId ?? 0),
    queryFn: () => api.posto.seguranca(obraId as number),
    enabled: obraId != null,
    placeholderData: keepPreviousData,
  })
}

export function useOcorrencias(obraId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.seguranca.ocorrencias(obraId ?? 0),
    queryFn: () => api.ocorrencias.daObra(obraId as number),
    enabled: obraId != null && ativo,
  })
}

export function useOcorrencia(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.seguranca.ocorrencia(id ?? 0),
    queryFn: () => api.ocorrencias.obter(id as number),
    enabled: id != null,
  })
}

export function useDdsDaObra(obraId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: pdcaKeys.seguranca.dds(obraId ?? 0),
    queryFn: () => api.dds.daObra(obraId as number),
    enabled: obraId != null && ativo,
  })
}

export function useDds(id: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.seguranca.umDds(id ?? 0),
    queryFn: () => api.dds.obter(id as number),
    enabled: id != null,
  })
}

/** Só dispara para quem tem `sil.epi.view` e o SIL contratado — sem isso a
 *  resposta seria 403, e a tela declara a indisponibilidade em vez de pedir. */
export function useEpiVencido(obraId: number | undefined, pode: boolean) {
  return useQuery({
    queryKey: pdcaKeys.seguranca.epi(obraId ?? 0),
    queryFn: () => api.ocorrencias.epiVencido(obraId as number),
    enabled: obraId != null && pode,
    retry: false,
  })
}

function useVerboDaSeguranca<A, R>(verbo: (args: A) => Promise<R>) {
  const invalidar = useInvalidarSeguranca()
  return useMutation({ mutationFn: verbo, onSuccess: invalidar })
}

export const useRegistrarOcorrencia = () =>
  useVerboDaSeguranca((corpo: Parameters<typeof api.ocorrencias.registrar>[0]) =>
    api.ocorrencias.registrar(corpo))

export const useClassificarOcorrencia = () =>
  useVerboDaSeguranca(({ id, corpo }: {
    id: number; corpo: Parameters<typeof api.ocorrencias.classificar>[1]
  }) => api.ocorrencias.classificar(id, corpo))

export const useRegistrarCat = () =>
  useVerboDaSeguranca(({ id, corpo }: {
    id: number; corpo: Parameters<typeof api.ocorrencias.cat>[1]
  }) => api.ocorrencias.cat(id, corpo))

export const useInterditarFrente = () =>
  useVerboDaSeguranca(({ id, prazo }: { id: number; prazo?: string | null }) =>
    api.ocorrencias.interditar(id, prazo))

export const useInvestigarOcorrencia = () =>
  useVerboDaSeguranca((id: number) => api.ocorrencias.investigar(id))

export const useEncerrarOcorrencia = () =>
  useVerboDaSeguranca(({ id, nota }: { id: number; nota: string }) =>
    api.ocorrencias.encerrar(id, nota))

export const useAnexarNaOcorrencia = () =>
  useVerboDaSeguranca((corpo: Parameters<typeof api.ocorrencias.anexar>[0]) =>
    api.ocorrencias.anexar(corpo))

export const useAbrirDds = () =>
  useVerboDaSeguranca((corpo: Parameters<typeof api.dds.abrir>[0]) => api.dds.abrir(corpo))

export const useRegistrarPresenca = () =>
  useVerboDaSeguranca(({ id, participantes }: {
    id: number; participantes: Parameters<typeof api.dds.presenca>[1]
  }) => api.dds.presenca(id, participantes))

export const useEncerrarDds = () =>
  useVerboDaSeguranca(({ id, publicar }: { id: number; publicar: boolean }) =>
    api.dds.encerrar(id, publicar))


/* --- PLANO: as etapas da obra (a montagem em si mora em `montagem.ts`) --- */


export function useEtapasDaObra(obraId: number | undefined) {
  return useQuery({
    queryKey: [...pdcaKeys.raiz, 'etapas', obraId ?? 0],
    queryFn: () => montagem.etapasDaObra.listar(obraId as number),
    enabled: obraId != null,
  })
}

export function useCriarEtapa(obraId: number | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ nome, ordem }: { nome: string; ordem: number }) =>
      montagem.etapasDaObra.criar(obraId as number, nome, ordem),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'etapas', obraId ?? 0] }),
  })
}

/** As equipes da obra — as colunas do quadro da semana. */
export function useEquipesDaObra(obraId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.equipes(obraId ?? 0),
    queryFn: () => api.equipes.daObra(obraId as number),
    enabled: obraId != null,
  })
}

export function useCriarEquipe(obraId: number | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (corpo: Parameters<typeof api.equipes.criar>[0]) => api.equipes.criar(corpo),
    onSuccess: () => {
      if (obraId != null) qc.invalidateQueries({ queryKey: pdcaKeys.equipes(obraId) })
    },
  })
}

/** O avanço físico-financeiro do plano — previsto × realizado × planejado. */
export function useAvancoFisicoFinanceiro(cronogramaId: number | undefined) {
  return useQuery({
    queryKey: pdcaKeys.cronogramas.avanco(cronogramaId ?? 0),
    queryFn: () => api.cronogramas.avancoFisicoFinanceiro(cronogramaId as number),
    enabled: cronogramaId != null,
  })
}

/** Rascunho → vigente. */
export function useAtivarContrato(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({ mutationFn: (id: number) => api.contratos.ativar(id), onSuccess: invalidar })
}

export function useFontesDaPlanilha(contratoId: number | undefined, ativo = true) {
  return useQuery({
    queryKey: [...pdcaKeys.medicao.raiz(), 'fontes-da-planilha', contratoId ?? 0],
    queryFn: () => api.contratos.fontesDaPlanilha(contratoId as number),
    enabled: contratoId != null && ativo,
  })
}

export function useIncluirNaPlanilha(obraId: number | undefined) {
  const invalidar = useInvalidarDinheiro(obraId)
  return useMutation({
    mutationFn: (v: { id: number; linhas: import('./types').LinhaParaPlanilha[] }) =>
      api.contratos.incluirNaPlanilha(v.id, v.linhas),
    onSuccess: invalidar,
  })
}
