import { useState, useEffect, useCallback } from 'react'
import apiClient from '@/api/apiClient'
import type {
  Empreendimento,
  ContaBancariaEmpreendimento,
  ContaBancariaEmpreendimentoFormData,
  CustoEmpreendimento,
  CustoEmpreendimentoFormData,
  EmpreendimentoFormData,
} from '@/types'

export function useEmpreendimento(id: number | null) {
  const [data, setData]       = useState<Empreendimento | null>(null)
  const [contas, setContas]   = useState<ContaBancariaEmpreendimento[]>([])
  const [custos, setCustos]   = useState<CustoEmpreendimento[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    Promise.all([
      apiClient.get(`/empreendimentos/${id}/`),
      apiClient.get(`/contas-bancarias-empreendimentos/?empreendimento=${id}`),
      apiClient.get(`/custos-empreendimentos/?empreendimento=${id}`),
    ])
      .then(([eRes, contasRes, custosRes]) => {
        setData(eRes.data)
        setContas(contasRes.data.results ?? contasRes.data)
        setCustos(custosRes.data.results ?? custosRes.data)
      })
      .catch(() => setError('Erro ao carregar empreendimento'))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => { fetch() }, [fetch])

  return { data, contas, custos, loading, error, refetch: fetch }
}

export async function createEmpreendimento(payload: EmpreendimentoFormData) {
  const r = await apiClient.post('/empreendimentos/', payload)
  return r.data as Empreendimento
}

export async function updateEmpreendimento(id: number, payload: Partial<EmpreendimentoFormData>) {
  const r = await apiClient.patch(`/empreendimentos/${id}/`, payload)
  return r.data as Empreendimento
}

export async function deleteEmpreendimento(id: number) {
  await apiClient.delete(`/empreendimentos/${id}/`)
}

// ─── Contas bancárias ─────────────────────────────────────────────────────────

export async function createContaBancaria(payload: ContaBancariaEmpreendimentoFormData) {
  const r = await apiClient.post('/contas-bancarias-empreendimentos/', {
    ...payload,
    numero_agencia: payload.agencia,
    numero_conta: payload.conta,
  })
  return r.data as ContaBancariaEmpreendimento
}

export async function updateContaBancaria(id: number, payload: Partial<ContaBancariaEmpreendimentoFormData>) {
  const body: Record<string, unknown> = { ...payload }
  if (payload.agencia) body.numero_agencia = payload.agencia
  if (payload.conta) body.numero_conta = payload.conta
  const r = await apiClient.patch(`/contas-bancarias-empreendimentos/${id}/`, body)
  return r.data as ContaBancariaEmpreendimento
}

export async function deleteContaBancaria(id: number) {
  await apiClient.delete(`/contas-bancarias-empreendimentos/${id}/`)
}

// ─── Custos ───────────────────────────────────────────────────────────────────

export async function createCusto(payload: CustoEmpreendimentoFormData) {
  const valor = parseFloat(payload.valor) || 0
  const quantidade = parseFloat(payload.quantidade) || 1
  const r = await apiClient.post('/custos-empreendimentos/', {
    ...payload,
    valor_total: (valor * quantidade).toFixed(2),
  })
  return r.data as CustoEmpreendimento
}

export async function updateCusto(id: number, payload: Partial<CustoEmpreendimentoFormData>) {
  const body: Record<string, unknown> = { ...payload }
  if (payload.valor !== undefined || payload.quantidade !== undefined) {
    const valor = parseFloat(payload.valor ?? '0') || 0
    const quantidade = parseFloat(payload.quantidade ?? '1') || 1
    body.valor_total = (valor * quantidade).toFixed(2)
  }
  const r = await apiClient.patch(`/custos-empreendimentos/${id}/`, body)
  return r.data as CustoEmpreendimento
}

export async function deleteCusto(id: number) {
  await apiClient.delete(`/custos-empreendimentos/${id}/`)
}
