import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type { Obra, EtapaObra, DocumentoObra, ObraFormData, EtapaObraFormData } from '@/types'

export function useObra(id: number | null) {
  const [data, setData]           = useState<Obra | null>(null)
  const [etapas, setEtapas]       = useState<EtapaObra[]>([])
  const [documentos, setDocumentos] = useState<DocumentoObra[]>([])
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    Promise.all([
      apiClient.get(`/obras/${id}/`),
      apiClient.get('/etapas-obras/', { params: { obra: id } }),
      apiClient.get('/documentos-obras/', { params: { obra: id } }),
    ])
      .then(([obraRes, etapasRes, docsRes]) => {
        setData(obraRes.data)
        setEtapas(etapasRes.data.results ?? etapasRes.data)
        setDocumentos(docsRes.data.results ?? docsRes.data)
      })
      .catch(() => setError('Erro ao carregar obra'))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => { fetch() }, [fetch])

  return { data, etapas, documentos, loading, error, refetch: fetch }
}

export async function createObra(payload: ObraFormData) {
  const r = await apiClient.post('/obras/', payload)
  return r.data as Obra
}

export async function updateObra(id: number, payload: Partial<ObraFormData>) {
  const r = await apiClient.patch(`/obras/${id}/`, payload)
  return r.data as Obra
}

export async function deleteObra(id: number) {
  await apiClient.delete(`/obras/${id}/`)
}

export async function createEtapa(payload: EtapaObraFormData) {
  const r = await apiClient.post('/etapas-obras/', payload)
  return r.data as EtapaObra
}

export async function updateEtapa(id: number, payload: Partial<EtapaObraFormData>) {
  const r = await apiClient.patch(`/etapas-obras/${id}/`, payload)
  return r.data as EtapaObra
}

export async function deleteEtapa(id: number) {
  await apiClient.delete(`/etapas-obras/${id}/`)
}
