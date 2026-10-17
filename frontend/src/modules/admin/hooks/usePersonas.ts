import { useState, useEffect, useCallback } from 'react'
import iamAdminClient from '@/api/iamAdminClient'
import type { Perfil, PerfilFormData, CatalogoResposta } from '../types'

const listOf = <T,>(data: unknown): T[] =>
  Array.isArray(data) ? (data as T[]) : ((data as { results?: T[] })?.results ?? [])

export function usePersonas() {
  const [perfis, setPerfis] = useState<Perfil[]>([])
  const [catalogo, setCatalogo] = useState<CatalogoResposta | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [pf, cat] = await Promise.all([
        iamAdminClient.get('/perfis/'),
        iamAdminClient.get('/catalogo-permissoes/'),
      ])
      setPerfis(listOf<Perfil>(pf.data).sort((a, b) => a.nome.localeCompare(b.nome)))
      setCatalogo(cat.data)
    } catch {
      setError('Erro ao carregar papéis e permissões. Exige administrador do tenant.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const createPerfil = async (fd: PerfilFormData): Promise<Perfil> => {
    const res = await iamAdminClient.post('/perfis/', fd)
    setPerfis(prev => [...prev, res.data].sort((a, b) => a.nome.localeCompare(b.nome)))
    return res.data
  }

  const updatePerfil = async (id: number, fd: PerfilFormData) => {
    const res = await iamAdminClient.patch(`/perfis/${id}/`, fd)
    setPerfis(prev => prev.map(p => (p.id === id ? res.data : p)))
  }

  const deletePerfil = async (id: number) => {
    await iamAdminClient.delete(`/perfis/${id}/`)
    setPerfis(prev => prev.filter(p => p.id !== id))
  }

  return { perfis, catalogo, loading, error, createPerfil, updatePerfil, deletePerfil, refetch: fetchAll }
}
