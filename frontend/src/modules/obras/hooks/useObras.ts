import { useState, useEffect, useCallback, useMemo } from 'react'
import apiClient from '@/api/apiClient'
import type { Obra, StatusObra } from '@/types'
import { contemSemAcento } from '@/utils/texto'

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
      // Sem acento dos dois lados (`utils/texto.ts`): quem digita "fundacao" ou
      // "Edificio Acai" tem de achar "Fundação" e "Edifício Açaí". Comparar com
      // acento faz a obra existir e a busca dizer que não.
      const q = filters.search
      list = list.filter(o =>
        contemSemAcento(o.nome_obra, q) ||
        contemSemAcento(o.endereco, q)
      )
    }
    return list
  }, [raw, filters.search, filters.status])

  return { data, loading, error, refetch: fetch }
}
