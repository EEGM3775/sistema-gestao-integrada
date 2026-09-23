import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query'
import { buscarCarteira, buscarGrupos, buscarOpcoes } from './api'
import type { FiltrosCarteira, PaginaCarteira, Visao } from './types'

/** O mínimo para pedir as linhas de um grupo: onde filtrar e por qual valor.
 *  Aceita tanto a combinação crua do backend quanto o nó já montado em árvore. */
interface GrupoEndereçavel {
  chaves: string[]
  filtros: string[]
}

const CHAVE = ['clientes', 'carteira'] as const

/**
 * A folha plana, em páginas — a rolagem infinita pede a próxima quando chega
 * perto do fim. Nunca baixa a carteira inteira (era o que a tela antiga fazia,
 * e com 5000 cadastros ela parava de pé).
 */
export function useCarteira(params: {
  visao: Visao
  filtros: FiltrosCarteira
  ordenar: string
  ativo: boolean
}) {
  const consulta = useInfiniteQuery({
    queryKey: [...CHAVE, 'lista', params.visao, params.filtros, params.ordenar],
    queryFn: ({ pageParam = 1 }) =>
      buscarCarteira({ visao: params.visao, filtros: params.filtros, ordenar: params.ordenar, page: pageParam }),
    getNextPageParam: (ultima: PaginaCarteira) => (ultima.temMais ? ultima.page + 1 : undefined),
    initialPageParam: 1,
    enabled: params.ativo,
    staleTime: 30_000,
  })

  const paginas = consulta.data?.pages ?? []
  return {
    linhas: paginas.flatMap(p => p.results),
    total: paginas[0]?.count ?? 0,
    podeFinanceiro: paginas[0]?.podeFinanceiro ?? false,
    podeDocumento: paginas[0]?.podeDocumento ?? false,
    carregando: consulta.isLoading,
    buscandoMais: consulta.isFetchingNextPage,
    temMais: consulta.hasNextPage,
    proximaPagina: consulta.fetchNextPage,
    erro: consulta.isError,
  }
}

/** Os cabeçalhos recolhíveis, com contagem e subtotais da carteira inteira. */
export function useGruposCarteira(params: {
  visao: Visao
  filtros: FiltrosCarteira
  niveis: string[]
  ativo: boolean
}) {
  const consulta = useQuery({
    queryKey: [...CHAVE, 'grupos', params.visao, params.filtros, params.niveis],
    queryFn: () => buscarGrupos({ visao: params.visao, filtros: params.filtros, niveis: params.niveis }),
    enabled: params.ativo && params.niveis.length > 0,
    staleTime: 30_000,
  })
  return {
    grupos: consulta.data?.grupos ?? [],
    // O total vem do servidor, contado distinto sobre o mesmo recorte. Somar os
    // grupos aqui seria contar duas vezes quem pertence a dois.
    total: consulta.data?.count ?? 0,
    somaDosGrupos: consulta.data?.somaDosGrupos ?? 0,
    podeFinanceiro: consulta.data?.podeFinanceiro ?? false,
    podeDocumento: consulta.data?.podeDocumento ?? false,
    carregando: consulta.isLoading,
    erro: consulta.isError,
  }
}

/**
 * As linhas de cada grupo aberto, carregadas sob demanda.
 *
 * Abrir um grupo é uma consulta nova com o filtro daquele grupo — é assim que
 * uma carteira de milhares de linhas fica navegável agrupada, sem trazer tudo
 * para a memória do navegador só porque um grupo foi aberto.
 */
export function useLinhasDeGrupos(params: {
  visao: Visao
  filtros: FiltrosCarteira
  ordenar: string
  abertos: GrupoEndereçavel[]
}) {
  const consultas = useQueries({
    queries: params.abertos.map(g => {
      const filtrosDoGrupo: FiltrosCarteira = { ...params.filtros }
      g.filtros.forEach((campo, i) => {
        filtrosDoGrupo[campo as keyof FiltrosCarteira] = g.chaves[i]
      })
      return {
        queryKey: [...CHAVE, 'grupo-linhas', params.visao, filtrosDoGrupo, params.ordenar],
        queryFn: () =>
          buscarCarteira({
            visao: params.visao, filtros: filtrosDoGrupo, ordenar: params.ordenar,
            page: 1, pageSize: 200,
          }),
        staleTime: 30_000,
      }
    }),
  })

  const porChave = new Map<string, { linhas: PaginaCarteira['results']; total: number; carregando: boolean }>()
  params.abertos.forEach((g, i) => {
    const c = consultas[i]
    porChave.set(g.chaves.join('␟'), {
      linhas: c.data?.results ?? [],
      total: c.data?.count ?? 0,
      carregando: c.isLoading,
    })
  })
  return porChave
}

export function useOpcoesCarteira() {
  return useQuery({
    queryKey: [...CHAVE, 'opcoes'],
    queryFn: buscarOpcoes,
    staleTime: 5 * 60_000,
  })
}
