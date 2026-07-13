import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import type { Empreendimento, Cliente, Fornecedor } from '@/types'

/**
 * Opções de selects de entidade (empreendimento/cliente/fornecedor) — cacheadas
 * pelo React Query e compartilhadas entre `FilterBar` e os formulários de
 * lançamento (`ContaPagarForm`/`ContaReceberForm`). `enabled` evita buscar
 * listas que a tela não usa.
 *
 * `refetchOnMount: 'always'` (D3): os cadastros de cliente/fornecedor/empreendimento
 * vivem em outros módulos e não invalidam este cache. Sem revalidar ao montar, um
 * cliente recém-criado só entrava no fluxo de cobrança após um refresh do browser.
 * Como o form/FilterBar remonta ao abrir, revalidar no mount traz o registro novo.
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
    staleTime: 30_000,
    refetchOnMount: 'always',
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
    staleTime: 30_000,
    refetchOnMount: 'always',
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
    staleTime: 30_000,
    refetchOnMount: 'always',
  })
  return { data: q.data, isLoading: q.isLoading }
}
