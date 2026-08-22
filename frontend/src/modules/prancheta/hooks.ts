import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api'
import type { Acervo } from './types'

export const pranchetaKeys = {
  acervo: (obra: number | null) => ['prancheta', 'acervo', obra] as const,
  disciplinas: ['prancheta', 'disciplinas'] as const,
  status: ['prancheta', 'status'] as const,
  revisoes: (documento: number | null) => ['prancheta', 'revisoes', documento] as const,
  historico: (obra: number | null, pagina: number) => ['prancheta', 'historico', obra, pagina] as const,
  marcacoes: (filtro: Record<string, unknown>) => ['prancheta', 'marcacoes', filtro] as const,
  medicoes: (revisao: number | null) => ['prancheta', 'medicoes', revisao] as const,
}

export const useAcervo = (obra: number | null) =>
  useQuery({
    queryKey: pranchetaKeys.acervo(obra),
    queryFn: () => api.carregarAcervo(obra as number),
    enabled: !!obra,
    /**
     * A conversão é assíncrona: quem acabou de subir um DXF vê `convertendo` e
     * precisa ver `pronta` sem apertar F5. 8 s é o meio-termo entre a fila do
     * Celery (segundos) e o celular do canteiro, onde cada refetch é dado móvel
     * — e o polling só existe **enquanto há algo convertendo**.
     */
    refetchInterval: (query) =>
      temConversaoEmAndamento(query.state.data) ? 8000 : false,
  })

function temConversaoEmAndamento(acervo?: Acervo): boolean {
  return (acervo?.disciplinas ?? []).some((grupo) =>
    grupo.documentos.some((d) => d.vigente?.conversao.estado === 'convertendo'),
  )
}

/**
 * O vocabulário de disciplinas — 13 embutidas + as desta empresa.
 *
 * Query própria, e não um recorte do acervo, porque o seletor do envio precisa
 * dela **antes** de haver acervo (obra nova, primeira prancha) e porque criar uma
 * disciplina tem de refletir na fileira sem esperar o acervo revalidar.
 */
export const useDisciplinas = (habilitado = true) =>
  useQuery({
    queryKey: pranchetaKeys.disciplinas,
    queryFn: api.listarDisciplinas,
    enabled: habilitado,
    staleTime: 60_000,
  })

/** Criar/editar/apagar disciplina mexe na fileira E nos rótulos do acervo. */
function useInvalidarDisciplinas() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: pranchetaKeys.disciplinas })
    qc.invalidateQueries({ queryKey: ['prancheta', 'acervo'] })
  }
}

export function useCriarDisciplina() {
  const invalidar = useInvalidarDisciplinas()
  return useMutation({ mutationFn: api.criarDisciplina, onSuccess: invalidar })
}

export function useAtualizarDisciplina() {
  const invalidar = useInvalidarDisciplinas()
  return useMutation({
    mutationFn: ({ id, ...dados }: { id: number } & Record<string, unknown>) =>
      api.atualizarDisciplina(id, dados),
    onSuccess: invalidar,
  })
}

export function useExcluirDisciplina() {
  const invalidar = useInvalidarDisciplinas()
  return useMutation({ mutationFn: api.excluirDisciplina, onSuccess: invalidar })
}

/**
 * Reclassificar a prancha — de dentro dela, que é onde se descobre o que ela é.
 *
 * Invalida o acervo inteiro e não só o documento: a prancha muda de **grupo** na
 * grade (pode entrar em dois), e a fileira de filtro reconta.
 */
export function useDisciplinasDoDocumento(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ documento, codigos }: { documento: number; codigos: string[] }) =>
      api.definirDisciplinasDoDocumento(documento, codigos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
    },
  })
}

/** O que ESTE plano abre — é quem diz se um formato aparece travado ou aberto. */
export const useStatusPrancheta = (habilitado: boolean) =>
  useQuery({
    queryKey: pranchetaKeys.status,
    queryFn: api.statusPrancheta,
    enabled: habilitado,
    retry: false,
  })

export const useRevisoes = (documento: number | null) =>
  useQuery({
    queryKey: pranchetaKeys.revisoes(documento),
    queryFn: () => api.listarRevisoes(documento as number),
    enabled: !!documento,
  })

/** Histórico de alterações da obra — só o responsável chega a esta tela. */
export const useHistoricoDaObra = (obra: number | null, pagina = 1) =>
  useQuery({
    queryKey: pranchetaKeys.historico(obra, pagina),
    queryFn: () => api.listarHistoricoDaObra(obra as number, pagina),
    enabled: !!obra,
  })

/** Publicar muda o que o campo executa — o acervo inteiro reflete isso. */
export function usePublicar(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.publicarRevisao(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
    },
  })
}

/**
 * Publicar em lote muda o acervo inteiro de uma vez — inclusive a fila do
 * cockpit, que é justamente de onde o botão é acionado. Invalida o mesmo
 * conjunto do `usePublicar`: a diferença entre os dois é o alcance, não o efeito.
 */
export function usePublicarPendentes(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.publicarPendentes(obra as number),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
    },
  })
}

export function useEnviarRevisao(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.enviarRevisao,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
    },
  })
}

// `useEnviarPrancha` saiu na PRA.9d junto com o upload avulso. Quem invalida o
// acervo depois de uma remessa agora é o `onConcluida` do wizard, na própria
// tela — o hook existia só para pendurar essa invalidação numa mutation que não
// existe mais.

/** A entrega seguinte de uma prancha viva — rótulo resolvido no servidor. */
export function useAtualizarPrancha(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.atualizarPrancha,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
    },
  })
}

export function useReprocessar(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.reprocessarRevisao(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
    },
  })
}

/**
 * Busca o arquivo gateado e devolve um object URL vivo enquanto o componente
 * viver. O `revoke` no cleanup não é higiene opcional: uma prancha de CAD tem
 * dezenas de MB, e navegar por dez delas sem soltar os blobs derruba a aba do
 * celular — que é justamente onde esta tela precisa aguentar.
 */
// ---------------------------------------------------------------------------
// PRA.3 — marcar e medir
// ---------------------------------------------------------------------------

/**
 * Marcações de um recorte (uma prancha, uma obra, "as minhas").
 *
 * O filtro é o mesmo objeto que a exportação BCF recebe — de propósito: o que a
 * tela mostra é o que o arquivo leva, e um segundo conjunto de regras seria
 * mais uma coisa para o usuário entender.
 */
export const useMarcacoes = (filtro: Record<string, unknown>, habilitado = true) =>
  useQuery({
    queryKey: pranchetaKeys.marcacoes(filtro),
    queryFn: () => api.listarMarcacoes(filtro),
    enabled: habilitado,
  })

export const useMedicoes = (revisao: number | null) =>
  useQuery({
    queryKey: pranchetaKeys.medicoes(revisao),
    queryFn: () => api.listarMedicoes(revisao as number),
    enabled: !!revisao,
  })

/**
 * Invalida tudo o que uma marcação toca. `acervo` entra porque a fila de decisão
 * do cockpit conta marcação aberta — sem isto, apontar um problema não mexeria
 * no contador que existe para mostrá-lo.
 */
function useInvalidarMarcacoes(obra: number | null) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['prancheta', 'marcacoes'] })
    qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
  }
}

export function useCriarMarcacao(obra: number | null) {
  const invalidar = useInvalidarMarcacoes(obra)
  return useMutation({ mutationFn: api.criarMarcacao, onSuccess: invalidar })
}

export function useComentar(obra: number | null) {
  const invalidar = useInvalidarMarcacoes(obra)
  return useMutation({
    mutationFn: ({ id, texto }: { id: number; texto: string }) =>
      api.comentarMarcacao(id, texto),
    onSuccess: invalidar,
  })
}

export function useMudarSituacao(obra: number | null) {
  const invalidar = useInvalidarMarcacoes(obra)
  return useMutation({
    mutationFn: ({ id, situacao }: { id: number; situacao: string }) =>
      api.mudarSituacaoMarcacao(id, situacao),
    onSuccess: invalidar,
  })
}

export function useCriarMedicao(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.criarMedicao,
    onSuccess: (medicao) => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.medicoes(medicao.revisao) })
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
    },
  })
}

/**
 * Calibrar muda o que TODA medida da prancha vale — então invalida as medições
 * junto, para as que ficaram para trás aparecerem marcadas como
 * `desatualizada` sem exigir F5.
 */
export function useCalibrar(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...dados }: Parameters<typeof api.calibrarDesenho>[1] & { id: number }) =>
      api.calibrarDesenho(id, dados),
    onSuccess: (desenho) => {
      qc.invalidateQueries({ queryKey: pranchetaKeys.medicoes(desenho.revisao) })
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
    },
  })
}

/**
 * Nomear uma folha invalida o acervo inteiro, e não só a revisão: o nome viaja
 * por herança para as revisões seguintes deste documento, então a lista lateral
 * de qualquer uma delas pode ter mudado.
 */
export function useRenomearDesenho(obra: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, nome }: { id: number; nome: string }) =>
      api.renomearDesenho(id, nome),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prancheta', 'revisoes'] })
      qc.invalidateQueries({ queryKey: pranchetaKeys.acervo(obra) })
    },
  })
}

export function useImportarBcf(obra: number | null) {
  const invalidar = useInvalidarMarcacoes(obra)
  return useMutation({
    mutationFn: ({ revisao, arquivo }: { revisao: number; arquivo: File }) =>
      api.importarBcf(revisao, arquivo),
    onSuccess: invalidar,
  })
}

/**
 * O hook do object URL subiu para `@/lib/arquivo` no D70 — a linha do tempo do
 * diário precisa do mesmo, e duas cópias de um efeito que revoga object URL é
 * como se vaza memória em uma delas. Reexportado para as telas do módulo.
 */
export { useArquivoBlob } from '@/lib/arquivo'
