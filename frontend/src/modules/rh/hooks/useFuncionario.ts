import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type {
  Funcionario, FuncionarioFormData,
  DadoMedicoFuncionario, DadoMedicoFormData,
  ASOFuncionario, ASOFuncionarioFormData,
  DocumentoFuncionario,
  DadoBancarioFuncionario, DadoBancarioFuncionarioFormData,
  PagamentoFuncionario, PagamentoFormData,
  FolhaPagamento, FolhaPagamentoFormData,
} from '@/types'

export function useFuncionario(funcionarioId: number) {
  const [data, setData]                       = useState<Funcionario | null>(null)
  const [dadoMedico, setDadoMedico]           = useState<DadoMedicoFuncionario | null>(null)
  const [asos, setAsos]                       = useState<ASOFuncionario[]>([])
  const [documentos, setDocumentos]           = useState<DocumentoFuncionario[]>([])
  const [dadosBancarios, setDadosBancarios]   = useState<DadoBancarioFuncionario[]>([])
  const [pagamentos, setPagamentos]           = useState<PagamentoFuncionario[]>([])
  const [folhas, setFolhas]                   = useState<FolhaPagamento[]>([])
  const [loading, setLoading]                 = useState(true)
  const [error, setError]                     = useState<string | null>(null)
  // flags de acesso restrito (403)
  const [acessoMedicoNegado, setAcessoMedicoNegado]           = useState(false)
  const [acessoFinanceiroNegado, setAcessoFinanceiroNegado]   = useState(false)

  const fetchAll = useCallback(async () => {
    if (!funcionarioId) return
    setLoading(true)
    setError(null)

    const [fRes, dmRes, asoRes, docRes, dbRes, pagRes, folhaRes] = await Promise.allSettled([
      apiClient.get(`/funcionarios/${funcionarioId}/`),
      apiClient.get('/dados-medicos-funcionarios/', { params: { funcionario: funcionarioId } }),
      apiClient.get('/asos-funcionarios/', { params: { funcionario: funcionarioId } }),
      apiClient.get('/documentos-funcionarios/', { params: { funcionario: funcionarioId } }),
      apiClient.get('/dados-bancarios-funcionarios/', { params: { funcionario: funcionarioId } }),
      apiClient.get('/pagamentos-funcionarios/', { params: { funcionario: funcionarioId } }),
      apiClient.get('/folhas-pagamento/', { params: { funcionario: funcionarioId } }),
    ])

    if (fRes.status === 'fulfilled') {
      setData(fRes.value.data)
    } else {
      setError('Funcionário não encontrado')
    }

    if (dmRes.status === 'fulfilled') {
      const list = dmRes.value.data.results ?? dmRes.value.data
      setDadoMedico(Array.isArray(list) ? (list[0] ?? null) : null)
      setAcessoMedicoNegado(false)
    } else {
      const status = (dmRes.reason as { response?: { status?: number } })?.response?.status
      setAcessoMedicoNegado(status === 403)
    }

    if (asoRes.status === 'fulfilled') {
      const list = asoRes.value.data.results ?? asoRes.value.data
      setAsos(Array.isArray(list) ? list : [])
    }

    if (docRes.status === 'fulfilled') {
      const list = docRes.value.data.results ?? docRes.value.data
      setDocumentos(Array.isArray(list) ? list : [])
    }

    if (dbRes.status === 'fulfilled') {
      const list = dbRes.value.data.results ?? dbRes.value.data
      setDadosBancarios(Array.isArray(list) ? list : [])
      setAcessoFinanceiroNegado(false)
    } else {
      const status = (dbRes.reason as { response?: { status?: number } })?.response?.status
      setAcessoFinanceiroNegado(status === 403)
    }

    if (pagRes.status === 'fulfilled') {
      const list = pagRes.value.data.results ?? pagRes.value.data
      setPagamentos(Array.isArray(list) ? list : [])
    }

    if (folhaRes.status === 'fulfilled') {
      const list = folhaRes.value.data.results ?? folhaRes.value.data
      setFolhas(Array.isArray(list) ? list : [])
    }

    setLoading(false)
  }, [funcionarioId])

  useEffect(() => { fetchAll() }, [fetchAll])

  // ── Funcionário ──────────────────────────────────────────────────────────────

  const updateFuncionario = async (fd: FuncionarioFormData) => {
    const res = await apiClient.patch(`/funcionarios/${funcionarioId}/`, fd)
    setData(res.data)
  }

  const deleteFuncionario = async () => {
    await apiClient.delete(`/funcionarios/${funcionarioId}/`)
  }

  // ── Documentos ───────────────────────────────────────────────────────────────

  const uploadDocumento = async (fd: FormData) => {
    fd.append('funcionario', String(funcionarioId))
    const res = await apiClient.post('/documentos-funcionarios/', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    setDocumentos(prev => [res.data, ...prev])
  }

  const deleteDocumento = async (id: number) => {
    await apiClient.delete(`/documentos-funcionarios/${id}/`)
    setDocumentos(prev => prev.filter(d => d.documento_id !== id))
  }

  // ── Dado Médico (1-to-1) ─────────────────────────────────────────────────────

  const saveDadoMedico = async (fd: DadoMedicoFormData) => {
    if (dadoMedico) {
      const res = await apiClient.patch(`/dados-medicos-funcionarios/${dadoMedico.id}/`, fd)
      setDadoMedico(res.data)
    } else {
      const res = await apiClient.post('/dados-medicos-funcionarios/', { ...fd, funcionario: funcionarioId })
      setDadoMedico(res.data)
    }
  }

  // ── ASOs (múltiplos por funcionário — um por exame ocupacional) ──────────────

  const buildASOBody = (fd: ASOFuncionarioFormData, arquivo: File | null): FormData | ASOFuncionarioFormData => {
    if (!arquivo) return fd
    const body = new FormData()
    Object.entries(fd).forEach(([k, v]) => body.append(k, String(v ?? '')))
    body.append('arquivo', arquivo)
    return body
  }

  const createASO = async (fd: ASOFuncionarioFormData, arquivo: File | null = null) => {
    const body = buildASOBody({ ...fd, funcionario: funcionarioId }, arquivo)
    const res = await apiClient.post('/asos-funcionarios/', body, arquivo
      ? { headers: { 'Content-Type': 'multipart/form-data' } }
      : undefined)
    setAsos(prev => [res.data, ...prev])
  }

  const updateASO = async (id: number, fd: ASOFuncionarioFormData, arquivo: File | null = null) => {
    const body = buildASOBody(fd, arquivo)
    const res = await apiClient.patch(`/asos-funcionarios/${id}/`, body, arquivo
      ? { headers: { 'Content-Type': 'multipart/form-data' } }
      : undefined)
    setAsos(prev => prev.map(a => a.aso_id === id ? res.data : a))
  }

  const deleteASO = async (id: number) => {
    await apiClient.delete(`/asos-funcionarios/${id}/`)
    setAsos(prev => prev.filter(a => a.aso_id !== id))
  }

  // ── Dados Bancários ──────────────────────────────────────────────────────────

  const createDadoBancario = async (fd: DadoBancarioFuncionarioFormData) => {
    const res = await apiClient.post('/dados-bancarios-funcionarios/', { ...fd, funcionario: funcionarioId })
    setDadosBancarios(prev => [...prev, res.data])
  }

  const updateDadoBancario = async (id: number, fd: DadoBancarioFuncionarioFormData) => {
    const res = await apiClient.patch(`/dados-bancarios-funcionarios/${id}/`, fd)
    setDadosBancarios(prev => prev.map(d => d.id === id ? res.data : d))
  }

  const deleteDadoBancario = async (id: number) => {
    await apiClient.delete(`/dados-bancarios-funcionarios/${id}/`)
    setDadosBancarios(prev => prev.filter(d => d.id !== id))
  }

  // ── Pagamentos ───────────────────────────────────────────────────────────────

  const createPagamento = async (fd: PagamentoFormData) => {
    const res = await apiClient.post('/pagamentos-funcionarios/', { ...fd, funcionario: funcionarioId })
    setPagamentos(prev => [res.data, ...prev])
  }

  const updatePagamento = async (id: number, fd: PagamentoFormData) => {
    const res = await apiClient.patch(`/pagamentos-funcionarios/${id}/`, fd)
    setPagamentos(prev => prev.map(p => p.id === id ? res.data : p))
  }

  const deletePagamento = async (id: number) => {
    await apiClient.delete(`/pagamentos-funcionarios/${id}/`)
    setPagamentos(prev => prev.filter(p => p.id !== id))
  }

  // ── Folha de Pagamento ───────────────────────────────────────────────────────

  const createFolha = async (fd: FolhaPagamentoFormData, holerite: File | null = null) => {
    let res
    if (holerite) {
      const body = new FormData()
      Object.entries({ ...fd, funcionario: funcionarioId }).forEach(([k, v]) => body.append(k, String(v ?? '')))
      body.append('holerite', holerite)
      res = await apiClient.post('/folhas-pagamento/', body, { headers: { 'Content-Type': 'multipart/form-data' } })
    } else {
      res = await apiClient.post('/folhas-pagamento/', { ...fd, funcionario: funcionarioId })
    }
    setFolhas(prev => [res.data, ...prev])
  }

  const updateFolha = async (id: number, fd: FolhaPagamentoFormData, holerite: File | null = null) => {
    let res
    if (holerite) {
      const body = new FormData()
      Object.entries(fd).forEach(([k, v]) => body.append(k, String(v ?? '')))
      body.append('holerite', holerite)
      res = await apiClient.patch(`/folhas-pagamento/${id}/`, body, { headers: { 'Content-Type': 'multipart/form-data' } })
    } else {
      res = await apiClient.patch(`/folhas-pagamento/${id}/`, fd)
    }
    setFolhas(prev => prev.map(f => f.folha_id === id ? res.data : f))
  }

  const deleteFolha = async (id: number) => {
    await apiClient.delete(`/folhas-pagamento/${id}/`)
    setFolhas(prev => prev.filter(f => f.folha_id !== id))
  }

  return {
    data, dadoMedico, asos, documentos, dadosBancarios, pagamentos, folhas,
    loading, error, acessoMedicoNegado, acessoFinanceiroNegado,
    updateFuncionario, deleteFuncionario,
    uploadDocumento, deleteDocumento,
    saveDadoMedico,
    createASO, updateASO, deleteASO,
    createDadoBancario, updateDadoBancario, deleteDadoBancario,
    createPagamento, updatePagamento, deletePagamento,
    createFolha, updateFolha, deleteFolha,
  }
}
