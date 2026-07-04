import { AxiosError } from 'axios'
import apiClient from '@/api/apiClient'
import type { ContribuirData, DiarioObra } from '@/types'

// Caminho único de escrita: get-or-create do diário do dia + entrada e/ou foto.
export async function contribuir(data: ContribuirData) {
  const form = new FormData()
  if (data.obra != null) form.append('obra', String(data.obra))
  if (data.texto.trim()) form.append('texto', data.texto.trim())
  form.append('eh_ocorrencia', String(data.eh_ocorrencia))
  if (data.condicoes_climaticas.trim()) form.append('condicoes_climaticas', data.condicoes_climaticas.trim())
  if (data.arquivo) form.append('arquivo', data.arquivo)
  const r = await apiClient.post('/diario/diarios/contribuir/', form)
  return r.data as DiarioObra
}

// Moderação (apenas responsável técnico — o backend valida).
export async function deleteEntrada(id: number) {
  await apiClient.delete(`/diario/entradas/${id}/`)
}

export async function deleteDocumento(id: number) {
  await apiClient.delete(`/diario/documentos/${id}/`)
}

// Extrai a mensagem mais útil de um erro da API (ex.: 403 { detail }).
export function extractApiError(err: unknown, fallback: string): string {
  if (err instanceof AxiosError && err.response?.data) {
    const d = err.response.data
    if (typeof d === 'string') return d
    if (typeof d.detail === 'string') return d.detail
    if (typeof d.error === 'string') return d.error
    const first = Object.values(d)[0]
    if (Array.isArray(first) && typeof first[0] === 'string') return first[0]
    if (typeof first === 'string') return first
  }
  return fallback
}
