import { useState, useEffect, useCallback, useMemo } from 'react'
import apiClient from '@/api/apiClient'
import type { Empreendimento, StatusEmpreendimento } from '@/types'

import { contemSemAcento } from '@/utils/texto'

interface Filters {
  search?: string
  status?: StatusEmpreendimento | ''
}

export function useEmpreendimentos(filters: Filters = {}) {
  const [raw, setRaw]         = useState<Empreendimento[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const fetch = useCallback(() => {
    setLoading(true)
    setError(null)
    // O backend ainda não tem SearchFilter — buscamos tudo e filtramos no cliente
    apiClient.get('/empreendimentos/')
      .then(r => setRaw(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar empreendimentos'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetch() }, [fetch])

  // Filtro client-side: busca em nome, razão social e CNPJ
  const data = useMemo(() => {
    let list = raw
    if (filters.status) {
      list = list.filter(e => e.status_empreendimento === filters.status)
    }
    if (filters.search) {
      const q      = filters.search
      const digits = q.replace(/\D/g, '')   // dígitos extraídos do termo buscado
      list = list.filter(e => {
        // Sem acento dos dois lados — ver .
        const byName = contemSemAcento(e.empreendimento, q) ||
                       contemSemAcento(e.razao_social, q)
        // CNPJ só é comparado se o termo de busca contiver pelo menos um dígito
        const byCNPJ = digits.length > 0 &&
                       e.cnpj.replace(/\D/g, '').includes(digits)
        return byName || byCNPJ
      })
    }
    return list
  }, [raw, filters.search, filters.status])

  return { data, loading, error, refetch: fetch }
}
