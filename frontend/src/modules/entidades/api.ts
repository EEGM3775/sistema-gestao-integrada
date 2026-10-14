import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'

export type PapelEntidade =
  | 'matriz' | 'filial' | 'spe' | 'scp' | 'patrimonio_afetacao' | 'consorcio' | 'pessoa_fisica' | 'outra'

export const PAPEIS: { valor: PapelEntidade; rotulo: string; ajuda: string }[] = [
  { valor: 'matriz', rotulo: 'Matriz', ajuda: 'A empresa principal da conta.' },
  { valor: 'filial', rotulo: 'Filial', ajuda: 'Mesmo CNPJ-raiz da matriz, outro estabelecimento (/0002).' },
  { valor: 'spe', rotulo: 'SPE', ajuda: 'Sociedade de Propósito Específico: uma empresa só para um empreendimento.' },
  { valor: 'scp', rotulo: 'SCP', ajuda: 'Sociedade em Conta de Participação: um sócio assina, os outros entram com capital.' },
  { valor: 'patrimonio_afetacao', rotulo: 'Patrimônio de afetação', ajuda: 'A incorporação segregada (RET), com CNPJ próprio.' },
  { valor: 'consorcio', rotulo: 'Consórcio', ajuda: 'Empresas reunidas para uma obra ou empreendimento.' },
  { valor: 'pessoa_fisica', rotulo: 'Pessoa física', ajuda: 'O construtor que trabalha no próprio CPF.' },
  { valor: 'outra', rotulo: 'Outra', ajuda: 'Sócio externo, contratante, parceiro de permuta.' },
]

export interface EmpreendimentoDaEntidade {
  empreendimento: number
  nome: string
  como: 'propria' | 'participacao'
  cota: string | null
  administradora: boolean
}

export interface Entidade {
  entidade_id: number
  tipo_pessoa: 'PJ' | 'PF'
  documento: string
  nome: string
  nome_fantasia: string
  papel: PapelEntidade
  papel_nome: string
  externa: boolean
  matriz: number | null
  matriz_nome: string
  cliente: number | null
  cliente_nome: string
  inscricao_estadual: string
  inscricao_municipal: string
  endereco: string
  cidade: string
  estado: string
  ativa: boolean
  empreendimentos: EmpreendimentoDaEntidade[]
}

export type EntidadeEntrada = Partial<Omit<Entidade, 'entidade_id' | 'papel_nome' | 'matriz_nome' | 'cliente_nome' | 'empreendimentos'>>

export interface EntidadeResumo {
  entidade: number
  nome: string
  papel: PapelEntidade
  papel_nome: string
  documento: string
}

export interface ContextoEntidades {
  modo_simples: boolean
  matriz: number
  sem_recorte: boolean
  entidades: EntidadeResumo[]
}

export interface Participacao {
  participacao_id: number
  empreendimento: number
  empreendimento_nome: string
  entidade: number
  entidade_nome: string
  entidade_externa: boolean
  cota: string
  administradora: boolean
}

export interface AcessoEntidade {
  concessao_id: number
  usuario: number
  usuario_nome: string
  entidade: number
  entidade_nome: string
  incluir_filiais: boolean
  concedido_em: string
}

interface Pagina<T> { results?: T[] }
const lista = <T,>(dados: T[] | Pagina<T>): T[] => (Array.isArray(dados) ? dados : dados.results ?? [])

export const entidadesKeys = {
  all: ['entidades'] as const,
  lista: (filtro: string) => ['entidades', 'lista', filtro] as const,
  contexto: ['entidades', 'contexto'] as const,
  participacoes: (empreendimentoId: number) => ['entidades', 'participacoes', empreendimentoId] as const,
  acessos: (entidadeId: number) => ['entidades', 'acessos', entidadeId] as const,
}

export function useEntidades(filtro: '' | 'grupo' | 'externas' = '', habilitado = true) {
  return useQuery({
    queryKey: entidadesKeys.lista(filtro),
    queryFn: async () => {
      const params = filtro === 'grupo' ? { externa: false } : filtro === 'externas' ? { externa: true } : {}
      return lista((await apiClient.get<Entidade[] | Pagina<Entidade>>('entidades/', { params })).data)
    },
    enabled: habilitado,
  })
}

/** O que a barra de entidade precisa: há recorte? quais a pessoa alcança? */
export function useContextoEntidades() {
  return useQuery({
    queryKey: entidadesKeys.contexto,
    queryFn: async () => (await apiClient.get<ContextoEntidades>('entidades/contexto/')).data,
    staleTime: 60_000,
  })
}

export function useSalvarEntidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, dados }: { id?: number; dados: EntidadeEntrada }) =>
      (id
        ? await apiClient.patch<Entidade>(`entidades/${id}/`, dados)
        : await apiClient.post<Entidade>('entidades/', dados)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: entidadesKeys.all }),
  })
}

export function useExcluirEntidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => { await apiClient.delete(`entidades/${id}/`) },
    onSuccess: () => qc.invalidateQueries({ queryKey: entidadesKeys.all }),
  })
}

export function useParticipacoes(empreendimentoId: number) {
  return useQuery({
    queryKey: entidadesKeys.participacoes(empreendimentoId),
    queryFn: async () => lista((await apiClient.get<Participacao[] | Pagina<Participacao>>(
      'participacoes-empreendimentos/', { params: { empreendimento: empreendimentoId } },
    )).data),
    enabled: empreendimentoId > 0,
  })
}

export function useSalvarParticipacao(empreendimentoId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, dados }: { id?: number; dados: Partial<Participacao> }) =>
      (id
        ? await apiClient.patch(`participacoes-empreendimentos/${id}/`, dados)
        : await apiClient.post('participacoes-empreendimentos/', { ...dados, empreendimento: empreendimentoId })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: entidadesKeys.all }),
  })
}

export function useExcluirParticipacao() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => { await apiClient.delete(`participacoes-empreendimentos/${id}/`) },
    onSuccess: () => qc.invalidateQueries({ queryKey: entidadesKeys.all }),
  })
}

export function useAcessosDaEntidade(entidadeId: number, habilitado: boolean) {
  return useQuery({
    queryKey: entidadesKeys.acessos(entidadeId),
    queryFn: async () => lista((await apiClient.get<AcessoEntidade[] | Pagina<AcessoEntidade>>(
      'acessos-entidades/', { params: { entidade: entidadeId } },
    )).data),
    enabled: habilitado && entidadeId > 0,
  })
}

export function useConcederAcesso() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (dados: { usuario: number; entidade: number; incluir_filiais: boolean }) =>
      (await apiClient.post('acessos-entidades/', dados)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: entidadesKeys.all }),
  })
}

export function useRevogarAcesso() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => { await apiClient.delete(`acessos-entidades/${id}/`) },
    onSuccess: () => qc.invalidateQueries({ queryKey: entidadesKeys.all }),
  })
}
