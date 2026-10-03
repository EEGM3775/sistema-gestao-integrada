import { keepPreviousData, useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import { buscarGrupos, buscarPagina, LINHAS_POR_GRUPO } from './api'
import { filtrosDoGrupo, idDoNo } from './arvore'
import type { Filtros, NoGrupo, PaginaGrade } from './tipos'

const CHAVE = erpKeys.grade.all

/**
 * A lista plana, em páginas — a rolagem infinita pede a próxima perto do fim.
 * `keepPreviousData` mantém o resultado anterior na tela enquanto a busca nova
 * chega: digitar não pisca a grade.
 */
export function useGradeInfinita<T>(recurso: string, filtros: Filtros, ordenar: string, ativo = true) {
  const consulta = useInfiniteQuery({
    queryKey: [...CHAVE, recurso, 'lista', filtros, ordenar],
    queryFn: ({ pageParam }) => buscarPagina<T>(recurso, filtros, ordenar, pageParam),
    getNextPageParam: (ultima: PaginaGrade<T>, todas) => (ultima.next ? todas.length + 1 : undefined),
    initialPageParam: 1,
    enabled: ativo,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  })
  const paginas = consulta.data?.pages ?? []
  return {
    linhas: paginas.flatMap(p => p.results),
    total: paginas[0]?.count ?? 0,
    carregando: consulta.isLoading,
    atualizando: consulta.isFetching && !consulta.isFetchingNextPage,
    buscandoMais: consulta.isFetchingNextPage,
    temMais: Boolean(consulta.hasNextPage),
    proximaPagina: () => { if (consulta.hasNextPage && !consulta.isFetchingNextPage) consulta.fetchNextPage() },
    erro: consulta.isError,
  }
}

/** Os totais do recorte e os cabeçalhos de grupo, com subtotais do banco. */
export function useGruposDaGrade(recurso: string, filtros: Filtros, por: string[]) {
  const consulta = useQuery({
    queryKey: [...CHAVE, recurso, 'grupos', filtros, por],
    queryFn: () => buscarGrupos(recurso, filtros, por),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  })
  return {
    totais: consulta.data?.totais,
    grupos: consulta.data?.grupos ?? [],
    dimensoes: consulta.data?.dimensoes ?? [],
    tetoNiveis: consulta.data?.teto_niveis ?? 3,
    carregando: consulta.isLoading,
  }
}

/** As linhas de cada grupo aberto, sob demanda — nunca a carteira inteira na memória. */
export function useLinhasDosGrupos<T>(recurso: string, filtros: Filtros, ordenar: string, abertos: NoGrupo[]) {
  const consultas = useQueries({
    queries: abertos.map(no => {
      const f = filtrosDoGrupo(filtros, no)
      return {
        queryKey: [...CHAVE, recurso, 'grupo-linhas', f, ordenar],
        queryFn: () => buscarPagina<T>(recurso, f, ordenar, 1, LINHAS_POR_GRUPO),
        staleTime: 15_000,
      }
    }),
  })
  const porNo = new Map<string, { linhas: T[]; total: number; carregando: boolean }>()
  abertos.forEach((no, i) => {
    const c = consultas[i]
    porNo.set(idDoNo(no), { linhas: c.data?.results ?? [], total: c.data?.count ?? 0, carregando: c.isLoading })
  })
  return porNo
}
