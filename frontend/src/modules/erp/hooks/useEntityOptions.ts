import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import type { Empreendimento, Cliente, Fornecedor } from '@/types'

/**
 * Opções de selects de entidade (empreendimento/cliente/fornecedor) — cacheadas
 * pelo React Query e compartilhadas entre `FilterBar` e os formulários de
 * lançamento (`ContaPagarForm`/`ContaReceberForm`). `enabled` evita buscar
 * listas que a tela não usa.
 */

export interface EntityOption { id: number; label: string }

interface EntityOptionsResult { data?: EntityOption[]; isLoading: boolean }

export function useEmpreendimentoOptions(enabled: boolean): EntityOptionsResult {
  const q = useQuery({
    queryKey: ['erp', 'filter-options', 'empreendimentos'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results?: Empreendimento[] } | Empreendimento[]>('/empreendimentos/')
      const list = Array.isArray(data) ? data : (data.results ?? [])
      return list.map((e): EntityOption => ({ id: e.empreendimento_id, label: e.empreendimento }))
    },
    enabled,
    staleTime: 5 * 60_000,
  })
  return { data: q.data, isLoading: q.isLoading }
}

export function useClienteOptions(enabled: boolean): EntityOptionsResult {
  const q = useQuery({
    queryKey: ['erp', 'filter-options', 'clientes'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results?: Cliente[] } | Cliente[]>('/clientes/')
      const list = Array.isArray(data) ? data : (data.results ?? [])
      return list.map((c): EntityOption => ({ id: c.cliente_id, label: c.nome_completo }))
    },
    enabled,
    staleTime: 5 * 60_000,
  })
  return { data: q.data, isLoading: q.isLoading }
}

export function useFornecedorOptions(enabled: boolean): EntityOptionsResult {
  const q = useQuery({
    queryKey: ['erp', 'filter-options', 'fornecedores'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results?: Fornecedor[] } | Fornecedor[]>('/fornecedores/')
      const list = Array.isArray(data) ? data : (data.results ?? [])
      return list.map((f): EntityOption => ({ id: f.fornecedor_id, label: f.razao_social }))
    },
    enabled,
    staleTime: 5 * 60_000,
  })
  return { data: q.data, isLoading: q.isLoading }
}
