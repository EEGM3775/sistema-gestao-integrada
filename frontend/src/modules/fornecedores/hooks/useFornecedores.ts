import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type { Fornecedor } from '@/types'

interface Filters {
  search?: string
}

export function useFornecedores(filters: Filters = {}) {
  const [data, setData]       = useState<Fornecedor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const fetch = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = {}
    if (filters.search) params.search = filters.search
    apiClient.get('/fornecedores/', { params })
      .then(r => setData(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar fornecedores'))
      .finally(() => setLoading(false))
  }, [filters.search])

  useEffect(() => { fetch() }, [fetch])

  return { data, loading, error, refetch: fetch }
}
