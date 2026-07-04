import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type { Cliente } from '@/types'

interface Filters {
  search?: string
  empreendimento?: number | ''
}

export function useClientes(filters: Filters = {}) {
  const [data, setData]       = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const fetch = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = {}
    if (filters.search)        params.search         = filters.search
    if (filters.empreendimento) params.empreendimento = String(filters.empreendimento)
    apiClient.get('/clientes/', { params })
      .then(r => setData(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar clientes'))
      .finally(() => setLoading(false))
  }, [filters.search, filters.empreendimento])

  useEffect(() => { fetch() }, [fetch])

  return { data, loading, error, refetch: fetch }
}
