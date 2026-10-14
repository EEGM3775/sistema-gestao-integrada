import { useSyncExternalStore } from 'react'
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'

/**
 * A camada do ERP (docs/modulos/entidades.md §6): `null` é o consolidado das
 * entidades que a pessoa alcança; um número é uma entidade só. Vale para todo o
 * ERP de uma vez — a lista, o painel e o relatório leem a mesma escolha — e
 * sobrevive ao recarregar a página.
 */
const CHAVE = 'sgi.erp.entidade'
let atual: number | null = ler()
const ouvintes = new Set<() => void>()

function ler(): number | null {
  try {
    const bruto = window.localStorage.getItem(CHAVE)
    return bruto ? Number(bruto) || null : null
  } catch {
    return null
  }
}

export function entidadeAtiva(): number | null {
  return atual
}

export function escolherEntidade(id: number | null) {
  atual = id
  try {
    if (id === null) window.localStorage.removeItem(CHAVE)
    else window.localStorage.setItem(CHAVE, String(id))
  } catch { /* navegação privada: vale só nesta aba */ }
  ouvintes.forEach(f => f())
}

export function useEntidadeAtiva(): number | null {
  return useSyncExternalStore(
    f => { ouvintes.add(f); return () => { ouvintes.delete(f) } },
    () => atual,
  )
}

const ligados = new WeakSet<AxiosInstance>()

/** Todo pedido ao ERP leva a camada escolhida, a não ser que já diga outra. */
export function ligarCamadaDoErp(cliente: AxiosInstance) {
  if (ligados.has(cliente)) return
  ligados.add(cliente)
  cliente.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const url = (config.url ?? '').replace(/^\//, '')
    if (atual !== null && url.startsWith('erp/')) {
      const params = (config.params ?? {}) as Record<string, unknown>
      if (params.entidade === undefined) config.params = { ...params, entidade: atual }
    }
    return config
  })
}
