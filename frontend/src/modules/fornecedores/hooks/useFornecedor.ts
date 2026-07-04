import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type {
  Fornecedor, FornecedorFormData,
  DadoBancarioFornecedor, DadoBancarioFornecedorFormData,
  ProdutoServicoFornecedor, ProdutoServicoFormData,
} from '@/types'

export function useFornecedor(fornecedorId: number) {
  const [data, setData]                       = useState<Fornecedor | null>(null)
  const [dadosBancarios, setDadosBancarios]   = useState<DadoBancarioFornecedor[]>([])
  const [produtos, setProdutos]               = useState<ProdutoServicoFornecedor[]>([])
  const [loading, setLoading]                 = useState(true)
  const [error, setError]                     = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!fornecedorId) return
    setLoading(true)
    setError(null)
    Promise.all([
      apiClient.get(`/fornecedores/${fornecedorId}/`),
      apiClient.get('/dados-bancarios-fornecedores/', { params: { fornecedor: fornecedorId } }),
      apiClient.get('/produtos-servicos-fornecedores/', { params: { fornecedor: fornecedorId } }),
    ])
      .then(([f, db, ps]) => {
        setData(f.data)
        setDadosBancarios(db.data.results ?? db.data)
        setProdutos(ps.data.results ?? ps.data)
      })
      .catch(() => setError('Erro ao carregar fornecedor'))
      .finally(() => setLoading(false))
  }, [fornecedorId])

  useEffect(() => { fetch() }, [fetch])

  // ── Fornecedor CRUD ───────────────────────────────────────────────────────

  const updateFornecedor = async (formData: FornecedorFormData) => {
    const r = await apiClient.patch(`/fornecedores/${fornecedorId}/`, formData)
    setData(r.data)
    return r.data as Fornecedor
  }

  const deleteFornecedor = async () => {
    await apiClient.delete(`/fornecedores/${fornecedorId}/`)
  }

  // ── Dados Bancários ───────────────────────────────────────────────────────

  const createDadoBancario = async (formData: DadoBancarioFornecedorFormData) => {
    const r = await apiClient.post('/dados-bancarios-fornecedores/', formData)
    setDadosBancarios(prev => [...prev, r.data])
    return r.data as DadoBancarioFornecedor
  }

  const updateDadoBancario = async (id: number, formData: DadoBancarioFornecedorFormData) => {
    const r = await apiClient.patch(`/dados-bancarios-fornecedores/${id}/`, formData)
    setDadosBancarios(prev => prev.map(d => d.id === id ? r.data : d))
    return r.data as DadoBancarioFornecedor
  }

  const deleteDadoBancario = async (id: number) => {
    await apiClient.delete(`/dados-bancarios-fornecedores/${id}/`)
    setDadosBancarios(prev => prev.filter(d => d.id !== id))
  }

  // ── Produtos / Serviços ───────────────────────────────────────────────────

  const createProduto = async (formData: ProdutoServicoFormData) => {
    const r = await apiClient.post('/produtos-servicos-fornecedores/', formData)
    setProdutos(prev => [...prev, r.data])
    return r.data as ProdutoServicoFornecedor
  }

  const updateProduto = async (id: number, formData: ProdutoServicoFormData) => {
    const r = await apiClient.patch(`/produtos-servicos-fornecedores/${id}/`, formData)
    setProdutos(prev => prev.map(p => p.id === id ? r.data : p))
    return r.data as ProdutoServicoFornecedor
  }

  const deleteProduto = async (id: number) => {
    await apiClient.delete(`/produtos-servicos-fornecedores/${id}/`)
    setProdutos(prev => prev.filter(p => p.id !== id))
  }

  return {
    data, dadosBancarios, produtos,
    loading, error, refetch: fetch,
    updateFornecedor, deleteFornecedor,
    createDadoBancario, updateDadoBancario, deleteDadoBancario,
    createProduto, updateProduto, deleteProduto,
  }
}

export async function createFornecedor(formData: FornecedorFormData): Promise<Fornecedor> {
  const r = await apiClient.post('/fornecedores/', formData)
  return r.data
}
