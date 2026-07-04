import { useState, useEffect, useCallback, useMemo } from 'react'
import apiClient from '@/api/apiClient'
import type { Obra, StatusObra } from '@/types'

interface Filters {
  search?: string
  status?: StatusObra | ''
  empreendimentoId?: number | null
}

export function useObras(filters: Filters = {}) {
  const [raw, setRaw]         = useState<Obra[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const empreendimentoId = filters.empreendimentoId ?? null

  const fetch = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = {}
    if (empreendimentoId) params['empreendimento_id'] = String(empreendimentoId)
    apiClient.get('/obras/', { params })
      .then(r => setRaw(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar obras'))
      .finally(() => setLoading(false))
  }, [empreendimentoId])

  useEffect(() => { fetch() }, [fetch])

  const data = useMemo(() => {
    let list = raw
    if (filters.status) {
      list = list.filter(o => o.status_obra === filters.status)
    }
    if (filters.search) {
      const q = filters.search.toLowerCase()
      list = list.filter(o =>
        o.nome_obra.toLowerCase().includes(q) ||
        o.endereco.toLowerCase().includes(q)
      )
    }
    return list
  }, [raw, filters.search, filters.status])

  return { data, loading, error, refetch: fetch }
}
