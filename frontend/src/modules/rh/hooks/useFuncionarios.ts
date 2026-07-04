import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type { Funcionario, FuncionarioFormData } from '@/types'

export function useFuncionarios() {
  const [funcionarios, setFuncionarios] = useState<Funcionario[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchFuncionarios = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.get('/funcionarios/')
      const data = res.data
      setFuncionarios(Array.isArray(data) ? data : data.results ?? [])
    } catch {
      setError('Erro ao carregar funcionários')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchFuncionarios() }, [fetchFuncionarios])

  return { funcionarios, loading, error, refetch: fetchFuncionarios }
}

export async function createFuncionario(fd: FuncionarioFormData): Promise<Funcionario> {
  const res = await apiClient.post('/funcionarios/', fd)
  return res.data
}
