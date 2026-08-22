/**
 * IE.0c — o que as duas telas compartilhadas precisam saber do motor.
 *
 * O `useRecursos` é o que faz o botão **sumir antes do clique** (planta §10):
 * o backend devolve só o que esta pessoa pode operar, então a ausência na lista
 * é a resposta. Botão que aparece e dá 403 no clique é pior que botão ausente —
 * ensina o usuário a desconfiar da tela.
 */
import { useMutation, useQuery } from '@tanstack/react-query'

import {
  consultarExportacao, consultarImportacao, desfazerImportacao, listarCatalogo, listarImportacoes,
  listarMapas,
} from './api'
import type { LimitesDoPlano, RecursoImpExp } from './api'

export const impexpKeys = {
  recursos: ['impexp', 'recursos'] as const,
  importacao: (id: number, filtro: string) => ['impexp', 'importacao', id, filtro] as const,
  historico: (recurso: string) => ['impexp', 'historico', recurso] as const,
  exportacao: (id: number) => ['impexp', 'exportacao', id] as const,
  mapas: (recurso: string) => ['impexp', 'mapas', recurso] as const,
}

export function useHistorico(recurso: string) {
  return useQuery({
    queryKey: impexpKeys.historico(recurso),
    queryFn: () => listarImportacoes(recurso),
    retry: false,
  })
}

/**
 * O catálogo inteiro — recursos **e** os tetos do plano, numa consulta só.
 *
 * Os dois vêm juntos do servidor porque a tela precisa dos dois antes do
 * primeiro clique: o teto dito antes é a parte 3 do método do assinador gov.br
 * ([limites.py](../../../../../backend/funcoesimpexp/limites.py)), e descobri-lo
 * no 402 depois de esperar o upload é a experiência que ele evita.
 */
export function useCatalogoImpExp() {
  return useQuery({
    queryKey: impexpKeys.recursos,
    queryFn: listarCatalogo,
    // A lista muda com o papel da pessoa, não com o dado — e o papel muda no
    // refresh do token, não a cada navegação.
    staleTime: 5 * 60_000,
    retry: false,
  })
}

export function useRecursos() {
  const { data, ...resto } = useCatalogoImpExp()
  return { ...resto, data: data?.recursos }
}

/** O recurso, se esta pessoa puder operá-lo. `undefined` = não pode (ou não existe). */
export function useRecurso(id: string): {
  recurso?: RecursoImpExp
  limites?: LimitesDoPlano
  carregando: boolean
} {
  const { data, isLoading } = useCatalogoImpExp()
  return {
    recurso: data?.recursos.find(r => r.id === id),
    limites: data?.limites,
    carregando: isLoading,
  }
}

export function useConferencia(id: number | undefined, filtro: string) {
  return useQuery({
    queryKey: impexpKeys.importacao(id ?? 0, filtro),
    queryFn: () => consultarImportacao(id as number, filtro ? { situacao: filtro } : {}),
    enabled: !!id,
    // R10 — enquanto o job lê, a tela acompanha. Parar o polling assim que sai
    // de `lendo` evita bater no servidor para sempre numa aba esquecida aberta.
    refetchInterval: query =>
      query.state.data?.status === 'lendo' ? 1500 : false,
  })
}

export function useExportacaoEmCurso(id: number | undefined) {
  return useQuery({
    queryKey: impexpKeys.exportacao(id ?? 0),
    queryFn: () => consultarExportacao(id as number),
    enabled: !!id,
    refetchInterval: query => (query.state.data?.status === 'gerando' ? 2000 : false),
  })
}

/** R6 — desfaz o lote inteiro, restaurando valor **e** procedência de cada linha. */
export function useDesfazerImportacao() {
  return useMutation({ mutationFn: (id: number) => desfazerImportacao(id) })
}

export function useMapas(recurso: string, ativo: boolean) {
  return useQuery({
    queryKey: impexpKeys.mapas(recurso),
    queryFn: () => listarMapas(recurso),
    enabled: ativo,
    retry: false,
  })
}
