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
 *
 * **Cada grupo rola infinito, como a lista plana.** Antes o grupo parava na
 * primeira página ("Mostrando 200 de 534 — refine o filtro") e não havia como
 * ver o resto sem filtrar. `paginas` diz quantas páginas de cada grupo a tela
 * já pediu; cada página é uma consulta própria no cache, então pedir a próxima
 * não refaz as anteriores.
 */
export const PAGINA_DO_GRUPO = 200

export function useLinhasDeGrupos(params: {
  visao: Visao
  filtros: FiltrosCarteira
  ordenar: string
  abertos: GrupoEndereçavel[]
  /** Páginas pedidas por grupo (chave `chaves.join('␟')`); ausente = 1. */
  paginas: ReadonlyMap<string, number>
}) {
  const pedidos = params.abertos.flatMap(g => {
    const chave = g.chaves.join('␟')
    const filtrosDoGrupo: FiltrosCarteira = { ...params.filtros }
    g.filtros.forEach((campo, i) => {
      filtrosDoGrupo[campo as keyof FiltrosCarteira] = g.chaves[i]
    })
    const n = params.paginas.get(chave) ?? 1
    return Array.from({ length: n }, (_, i) => ({ chave, filtrosDoGrupo, page: i + 1 }))
  })

  const consultas = useQueries({
    queries: pedidos.map(p => ({
      queryKey: [...CHAVE, 'grupo-linhas', params.visao, p.filtrosDoGrupo, params.ordenar, p.page],
      queryFn: () =>
        buscarCarteira({
          visao: params.visao, filtros: p.filtrosDoGrupo, ordenar: params.ordenar,
          page: p.page, pageSize: PAGINA_DO_GRUPO,
        }),
      staleTime: 30_000,
    })),
  })

  const porChave = new Map<string, {
    linhas: PaginaCarteira['results']; total: number; carregando: boolean; buscandoMais: boolean
  }>()
  pedidos.forEach((p, i) => {
    const c = consultas[i]
    const atual = porChave.get(p.chave) ?? { linhas: [], total: 0, carregando: false, buscandoMais: false }
    if (p.page === 1) {
      atual.total = c.data?.count ?? 0
      atual.carregando = c.isLoading
    } else if (c.isLoading) {
      atual.buscandoMais = true
    }
    atual.linhas = atual.linhas.concat(c.data?.results ?? [])
    porChave.set(p.chave, atual)
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
