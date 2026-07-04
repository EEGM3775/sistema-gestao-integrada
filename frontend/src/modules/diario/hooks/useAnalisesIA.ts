import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type {
  AnaliseDocumentoResumo,
  AnaliseDocumentoDetalhes,
  DocumentosAnaliseResponse,
} from '@/types'

interface Filters {
  obraId?: number | null
  status?: string
}

export function useAnalisesIA(filters: Filters = {}) {
  const [data, setData]       = useState<AnaliseDocumentoResumo[]>([])
  const [total, setTotal]     = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const obraId = filters.obraId ?? null
  const status = filters.status ?? ''

  const fetch = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = {}
    if (obraId) params['obra'] = String(obraId)
    if (status) params['status'] = status
    apiClient.get<DocumentosAnaliseResponse>('/diario/documentos-com-analise/', { params })
      .then(r => {
        setData(r.data.documentos ?? [])
        setTotal(r.data.total ?? 0)
      })
      .catch(() => setError('Erro ao carregar as análises de IA'))
      .finally(() => setLoading(false))
  }, [obraId, status])

  useEffect(() => { fetch() }, [fetch])

  return { data, total, loading, error, refetch: fetch }
}

export async function getAnaliseDetalhes(documentoId: number) {
  const r = await apiClient.get<AnaliseDocumentoDetalhes>(`/diario/documento-analise/${documentoId}/`)
  return r.data
}

export async function reprocessarAnalise(documentoId: number, tipoAnalise = 'completa') {
  const r = await apiClient.post('/diario/reprocessar-analise/', {
    documento_id: documentoId,
    tipo_analise: tipoAnalise,
  })
  return r.data
}
