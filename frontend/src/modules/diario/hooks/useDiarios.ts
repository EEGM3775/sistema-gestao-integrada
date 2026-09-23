import { useState, useEffect, useCallback, useMemo } from 'react'
import apiClient from '@/api/apiClient'
import type { DiarioObra } from '@/types'

import { contemSemAcento } from '@/utils/texto'

interface Filters {
  obraId?: number | null
  search?: string
}

export function useDiarios(filters: Filters = {}) {
  const [raw, setRaw]         = useState<DiarioObra[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const obraId = filters.obraId ?? null

  const fetch = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = {}
    if (obraId) params['obra'] = String(obraId)
    apiClient.get('/diario/diarios/', { params })
      .then(r => setRaw(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar os diários'))
      .finally(() => setLoading(false))
  }, [obraId])

  useEffect(() => { fetch() }, [fetch])

  const data = useMemo(() => {
    if (!filters.search) return raw
    // Sem acento dos dois lados — ver .
    const q = filters.search
    return raw.filter(d =>
      contemSemAcento(d.condicoes_climaticas ?? '', q) ||
      contemSemAcento(d.descricao ?? '', q) ||
      d.entradas.some(e => contemSemAcento(e.texto, q))
    )
  }, [raw, filters.search])

  return { data, loading, error, refetch: fetch }
}
