import apiClient from '@/api/apiClient'

/**
 * DMS — o registro de todo arquivo, dentro e fora do sistema.
 * Backend: `funcoesimpexp/arquivos.py` (`GET /api/impexp/arquivos/`).
 */

export interface ArquivoGuardado {
  recurso: string
  recurso_rotulo: string
  modulo: string
  especie: string
  chave: number
  nome: string
  titulo: string
  /** De qual obra, cliente ou funcionário. */
  onde: string
  quando: string | null
  /** A mesma URL da entrega (`/api/impexp/<recurso>/arquivo/<espécie>/<chave>/`). */
  link: string
}

export interface Guardados {
  arquivos: ArquivoGuardado[]
  por_recurso: { recurso: string; rotulo: string; modulo: string; total: number }[]
}

export interface Entrada {
  id: number
  recurso: string
  recurso_rotulo: string
  arquivo: string
  situacao: string
  status: string
  linhas: number
  aplicadas: number
  quem: string
  quando: string
}

export interface Saida {
  tipo: 'exportacao' | 'entrega'
  recurso: string
  recurso_rotulo: string
  descricao: string
  quem: string
  quando: string
}

export async function fetchGuardados(params: { busca?: string; recurso?: string }): Promise<Guardados> {
  const { data } = await apiClient.get<Guardados>('/impexp/arquivos/', {
    params: { lente: 'guardados', ...(params.busca ? { busca: params.busca } : {}), ...(params.recurso ? { recurso: params.recurso } : {}) },
  })
  return data
}

export async function fetchEntraram(): Promise<Entrada[]> {
  const { data } = await apiClient.get<{ entraram: Entrada[] }>('/impexp/arquivos/', { params: { lente: 'entraram' } })
  return data.entraram
}

export async function fetchSairam(): Promise<Saida[]> {
  const { data } = await apiClient.get<{ sairam: Saida[] }>('/impexp/arquivos/', { params: { lente: 'sairam' } })
  return data.sairam
}
