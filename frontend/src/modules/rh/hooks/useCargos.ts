import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type { Cargo, CargoFormData } from '@/types'

export function useCargos() {
  const [cargos, setCargos] = useState<Cargo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchCargos = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.get('/cargos/')
      const data = res.data
      setCargos(Array.isArray(data) ? data : data.results ?? [])
    } catch {
      setError('Erro ao carregar cargos')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchCargos() }, [fetchCargos])

  const createCargo = async (fd: CargoFormData): Promise<Cargo> => {
    const res = await apiClient.post('/cargos/', fd)
    setCargos(prev => [...prev, res.data].sort((a, b) => a.nome_cargo.localeCompare(b.nome_cargo)))
    return res.data
  }

  const updateCargo = async (id: number, fd: CargoFormData) => {
    const res = await apiClient.patch(`/cargos/${id}/`, fd)
    setCargos(prev => prev.map(c => c.cargo_id === id ? res.data : c))
  }

  const deleteCargo = async (id: number) => {
    await apiClient.delete(`/cargos/${id}/`)
    setCargos(prev => prev.filter(c => c.cargo_id !== id))
  }

  return { cargos, loading, error, createCargo, updateCargo, deleteCargo, refetch: fetchCargos }
}
