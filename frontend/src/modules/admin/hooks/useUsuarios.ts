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
      setError('Erro ao carregar usuários. Exige administrador do tenant.')
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

  // Reset de senha pelo admin: exige a senha ATUAL do usuário (a recuperação sem
  // a antiga é etapa futura). O backend verifica a senha atual, aplica a nova e
  // encerra todas as sessões do usuário.
  const resetSenha = async (id: string, senhaAtual: string, novaSenha: string) => {
    await iamAdminClient.post(`/usuarios/${id}/redefinir-senha/`, {
      senha_atual: senhaAtual,
      nova_senha: novaSenha,
    })
  }

  // Para quem perdeu o celular e os códigos de recuperação: apaga o segundo
  // fator do usuário e encerra as sessões dele. O backend registra quem fez e
  // avisa o usuário por e-mail.
  const redefinirSegundoFator = async (id: string) => {
    await iamAdminClient.post(`/usuarios/${id}/redefinir-segundo-fator/`, {})
    setUsuarios(prev => prev.map(u => (u.id === id ? { ...u, segundo_fator_ativo: false } : u)))
  }

  return {
    usuarios, perfis, loading, error, setPerfisDoUsuario, resetSenha, redefinirSegundoFator,
    refetch: fetchAll,
  }
}
