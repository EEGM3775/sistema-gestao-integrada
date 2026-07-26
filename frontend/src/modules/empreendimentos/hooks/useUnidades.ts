import { useCallback, useEffect, useState } from 'react'
import apiClient from '@/api/apiClient'
import type { Unidade, UnidadeFormData } from '@/types'

/**
 * As unidades de um empreendimento.
 *
 * Paginado: um loteamento tem milhares de lotes e a aba carrega de página em
 * página ("carregar mais"), como a carteira de clientes. Filtro e ordenação vão
 * ao servidor — ordenar só o que já veio daria uma ordem que muda conforme o
 * usuário rola, que é pior do que não ordenar.
 */
export interface FiltrosUnidades {
  situacao?: string
  quadra?: string
  busca?: string
  ordering?: string
}

const TAMANHO_PAGINA = 100

export function useUnidades(empreendimentoId: number | null, filtros: FiltrosUnidades) {
  const [unidades, setUnidades] = useState<Unidade[]>([])
  const [total, setTotal] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { situacao, quadra, busca, ordering } = filtros

  const buscar = useCallback(async (paginaAlvo: number, acumular: boolean) => {
    if (!empreendimentoId) return
    setLoading(true)
    setError(null)
    try {
      const { data } = await apiClient.get('/unidades/', {
        params: {
          empreendimento: empreendimentoId,
          page: paginaAlvo,
          page_size: TAMANHO_PAGINA,
          ...(situacao ? { situacao } : {}),
          ...(quadra ? { quadra } : {}),
          ...(busca ? { search: busca } : {}),
          ...(ordering ? { ordering } : {}),
        },
      })
      const linhas: Unidade[] = data.results ?? data
      setTotal(data.count ?? linhas.length)
      setUnidades(anteriores => (acumular ? [...anteriores, ...linhas] : linhas))
      setPagina(paginaAlvo)
    } catch {
      setError('Erro ao carregar as unidades')
    } finally {
      setLoading(false)
    }
  }, [empreendimentoId, situacao, quadra, busca, ordering])

  // Trocar filtro/ordem recomeça da primeira página: manter o acumulado
  // misturaria linhas de dois critérios diferentes na mesma tabela.
  useEffect(() => { buscar(1, false) }, [buscar])

  return {
    unidades,
    total,
    loading,
    error,
    temMais: unidades.length < total,
    carregarMais: () => buscar(pagina + 1, true),
    recarregar: () => buscar(1, false),
  }
}

export async function createUnidade(payload: UnidadeFormData) {
  const r = await apiClient.post('/unidades/', payload)
  return r.data as Unidade
}

export async function updateUnidade(id: number, payload: Partial<UnidadeFormData>) {
  const r = await apiClient.patch(`/unidades/${id}/`, payload)
  return r.data as Unidade
}

export async function deleteUnidade(id: number) {
  await apiClient.delete(`/unidades/${id}/`)
}

/** As unidades que ainda podem ser vendidas — alimenta o seletor da aquisição.
 *  `incluir` mantém na lista a unidade da aquisição que está sendo editada, que
 *  já está "vendida" e sumiria do próprio formulário que a mostra. */
export async function buscarUnidadesDisponiveis(
  empreendimentoId?: number, busca?: string, incluir?: number,
): Promise<Unidade[]> {
  const { data } = await apiClient.get('/unidades/', {
    params: {
      situacao: 'disponivel',
      page_size: 300,
      ...(empreendimentoId ? { empreendimento: empreendimentoId } : {}),
      ...(busca ? { search: busca } : {}),
    },
  })
  const disponiveis: Unidade[] = data.results ?? data
  if (!incluir || disponiveis.some(u => u.unidade_id === incluir)) return disponiveis
  try {
    const { data: atual } = await apiClient.get(`/unidades/${incluir}/`)
    return [atual as Unidade, ...disponiveis]
  } catch {
    return disponiveis
  }
}
