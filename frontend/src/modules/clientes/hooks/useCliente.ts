import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type {
  Cliente, ClienteFormData,
  ClienteEmpreendimento, ClienteEmpreendimentoFormData,
  ContratoCliente, ContratoClienteFormData,
  DocumentoCliente, DadoBancarioCliente, DadoBancarioClienteFormData,
} from '@/types'

export function useCliente(clienteId: number) {
  const [data, setData]                       = useState<Cliente | null>(null)
  const [aquisicoes, setAquisicoes]           = useState<ClienteEmpreendimento[]>([])
  const [contratos, setContratos]             = useState<ContratoCliente[]>([])
  const [documentos, setDocumentos]           = useState<DocumentoCliente[]>([])
  const [dadosBancarios, setDadosBancarios]   = useState<DadoBancarioCliente[]>([])
  const [loading, setLoading]                 = useState(true)
  const [error, setError]                     = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!clienteId) return
    setLoading(true)
    setError(null)
    Promise.all([
      apiClient.get(`/clientes/${clienteId}/`),
      apiClient.get('/clientes-empreendimentos/', { params: { cliente: clienteId } }),
      apiClient.get('/contratos-clientes/',       { params: { cliente: clienteId } }),
      apiClient.get('/documentos-clientes/',      { params: { cliente: clienteId } }),
      apiClient.get('/dados-bancarios-clientes/', { params: { cliente: clienteId } }),
    ])
      .then(([c, a, co, d, db]) => {
        setData(c.data)
        setAquisicoes(a.data.results ?? a.data)
        setContratos(co.data.results ?? co.data)
        setDocumentos(d.data.results ?? d.data)
        setDadosBancarios(db.data.results ?? db.data)
      })
      .catch(() => setError('Erro ao carregar cliente'))
      .finally(() => setLoading(false))
  }, [clienteId])

  useEffect(() => { fetch() }, [fetch])

  // ── Cliente CRUD ──────────────────────────────────────────────────────────

  const updateCliente = async (formData: ClienteFormData) => {
    const r = await apiClient.patch(`/clientes/${clienteId}/`, formData)
    setData(r.data)
    return r.data as Cliente
  }

  const deleteCliente = async () => {
    await apiClient.delete(`/clientes/${clienteId}/`)
  }

  // ── Aquisições ────────────────────────────────────────────────────────────

  const createAquisicao = async (formData: ClienteEmpreendimentoFormData) => {
    const r = await apiClient.post('/clientes-empreendimentos/', formData)
    setAquisicoes(prev => [...prev, r.data])
    return r.data as ClienteEmpreendimento
  }

  const updateAquisicao = async (id: number, formData: ClienteEmpreendimentoFormData) => {
    const r = await apiClient.patch(`/clientes-empreendimentos/${id}/`, formData)
    setAquisicoes(prev => prev.map(a => a.cliente_empreendimento_id === id ? r.data : a))
    return r.data as ClienteEmpreendimento
  }

  const deleteAquisicao = async (id: number) => {
    await apiClient.delete(`/clientes-empreendimentos/${id}/`)
    setAquisicoes(prev => prev.filter(a => a.cliente_empreendimento_id !== id))
  }

  // ── Contratos ─────────────────────────────────────────────────────────────

  const createContrato = async (formData: ContratoClienteFormData) => {
    const r = await apiClient.post('/contratos-clientes/', formData)
    setContratos(prev => [...prev, r.data])
    return r.data as ContratoCliente
  }

  const updateContrato = async (id: number, formData: ContratoClienteFormData) => {
    const r = await apiClient.patch(`/contratos-clientes/${id}/`, formData)
    setContratos(prev => prev.map(c => c.contrato_cliente_id === id ? r.data : c))
    return r.data as ContratoCliente
  }

  const deleteContrato = async (id: number) => {
    await apiClient.delete(`/contratos-clientes/${id}/`)
    setContratos(prev => prev.filter(c => c.contrato_cliente_id !== id))
  }

  // ── Documentos ────────────────────────────────────────────────────────────

  const uploadDocumento = async (form: FormData) => {
    const r = await apiClient.post('/documentos-clientes/', form)
    setDocumentos(prev => [...prev, r.data])
    return r.data as DocumentoCliente
  }

  const deleteDocumento = async (id: number) => {
    await apiClient.delete(`/documentos-clientes/${id}/`)
    setDocumentos(prev => prev.filter(d => d.documento_cliente_id !== id))
  }

  // ── Dados Bancários ───────────────────────────────────────────────────────

  const createDadoBancario = async (formData: DadoBancarioClienteFormData) => {
    const r = await apiClient.post('/dados-bancarios-clientes/', formData)
    setDadosBancarios(prev => [...prev, r.data])
    return r.data as DadoBancarioCliente
  }

  const updateDadoBancario = async (id: number, formData: DadoBancarioClienteFormData) => {
    const r = await apiClient.patch(`/dados-bancarios-clientes/${id}/`, formData)
    setDadosBancarios(prev => prev.map(d => d.id === id ? r.data : d))
    return r.data as DadoBancarioCliente
  }

  const deleteDadoBancario = async (id: number) => {
    await apiClient.delete(`/dados-bancarios-clientes/${id}/`)
    setDadosBancarios(prev => prev.filter(d => d.id !== id))
  }

  return {
    data, aquisicoes, contratos, documentos, dadosBancarios,
    loading, error, refetch: fetch,
    updateCliente, deleteCliente,
    createAquisicao, updateAquisicao, deleteAquisicao,
    createContrato, updateContrato, deleteContrato,
    uploadDocumento, deleteDocumento,
    createDadoBancario, updateDadoBancario, deleteDadoBancario,
  }
}

export async function createCliente(formData: ClienteFormData): Promise<Cliente> {
  const r = await apiClient.post('/clientes/', formData)
  return r.data
}
