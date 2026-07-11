import { useState, useEffect, useCallback } from 'react'
import iamAdminClient from '@/api/iamAdminClient'
import type { UsuarioAdmin, Perfil } from '../types'

const listOf = <T,>(data: unknown): T[] =>
  Array.isArray(data) ? (data as T[]) : ((data as { results?: T[] })?.results ?? [])

export function useUsuarios() {
  const [usuarios, setUsuarios] = useState<UsuarioAdmin[]>([])
  const [perfis, setPerfis] = useState<Perfil[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [us, pf] = await Promise.all([
        iamAdminClient.get('/usuarios/'),
        iamAdminClient.get('/perfis/'),
      ])
      setUsuarios(listOf<UsuarioAdmin>(us.data).sort((a, b) => a.username.localeCompare(b.username)))
      setPerfis(listOf<Perfil>(pf.data).sort((a, b) => a.nome.localeCompare(b.nome)))
    } catch {
      setError('Erro ao carregar usuários. Você precisa ser administrador do tenant.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  // Atribui o conjunto de papéis a um usuário (PATCH parcial no UsuarioViewSet).
  const setPerfisDoUsuario = async (id: string, perfilIds: number[]) => {
    const res = await iamAdminClient.patch(`/usuarios/${id}/`, { perfis: perfilIds })
    setUsuarios(prev => prev.map(u => (u.id === id ? { ...u, ...res.data } : u)))
  }

  return { usuarios, perfis, loading, error, setPerfisDoUsuario, refetch: fetchAll }
}
