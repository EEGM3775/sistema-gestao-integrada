import apiClient from '@/api/apiClient'

/** O estado de um item, do ponto de vista de quem olha a página. */
export type EstadoLixo = 'no_lixo' | 'restaurado' | 'purgado'

export interface ItemDoLixo {
  lixo_id: number
  /** `app_label.model` — a chave de filtro. */
  modelo: string
  /** "Obra", "Cliente" — o `verbose_name` do modelo, vindo do servidor. */
  modelo_rotulo: string
  alvo_id: number
  rotulo: string
  excluido_em: string
  excluido_por_nome: string
  motivo: string
  purgar_em: string
  /** `null` quando o item já saiu da lixeira — não há relógio correndo. */
  dias_para_purga: number | null
  estado: EstadoLixo
  restaurado_em: string | null
  restaurado_por_nome: string | null
  purgado_em: string | null
  purgado_por_nome: string | null
  /** Por que a purga não conseguiu apagar. Vazio é o caso normal. */
  falha_na_purga: string
}

export interface ResumoDoLixo {
  total: number
  vencidos_nao_purgados: number
  com_falha: number
  por_tipo: { modelo: string; quantidade: number }[]
}

export interface Paginado<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

type Params = Record<string, unknown>

export const listar = async (params: Params = {}) =>
  (await apiClient.get<Paginado<ItemDoLixo>>('lixo/', { params })).data

export const resumo = async () =>
  (await apiClient.get<ResumoDoLixo>('lixo/resumo/')).data

export const restaurar = async (id: number) =>
  (await apiClient.post<ItemDoLixo>(`lixo/${id}/restaurar/`)).data

export const purgar = async (id: number) =>
  (await apiClient.post<ItemDoLixo>(`lixo/${id}/purgar/`)).data
