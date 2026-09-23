import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './api'

export const mapsKeys = {
  mapa: ['maps', 'mapa'] as const,
  status: ['maps', 'status'] as const,
  locais: (params?: Record<string, unknown>) => ['maps', 'locais', params ?? {}] as const,
  proximos: (de: number, raio: number, tipo?: string) => ['maps', 'proximos', de, raio, tipo] as const,
  camadas: ['maps', 'camadas'] as const,
  feicoes: (params?: Record<string, unknown>) => ['maps', 'feicoes', params ?? {}] as const,
  ortofotos: ['maps', 'ortofotos'] as const,
  planos: ['maps', 'planos'] as const,
  rotas: ['maps', 'rotas'] as const,
  geofences: ['maps', 'geofences'] as const,
}

export const useMapa = () => useQuery({ queryKey: mapsKeys.mapa, queryFn: api.carregarMapa })

/** Status é o que diz à tela quais provedores esta instalação tem — sem ele,
 *  a UI ofereceria botão de rota num ambiente sem motor de rota. */
export const useStatusMaps = (habilitado: boolean) =>
  useQuery({ queryKey: mapsKeys.status, queryFn: api.statusMaps, enabled: habilitado, retry: false })

export const useLocais = (params?: Record<string, unknown>) =>
  useQuery({ queryKey: mapsKeys.locais(params), queryFn: () => api.listarLocais(params) })

export const useProximos = (de: number | null, raio: number, tipo?: string) =>
  useQuery({
    queryKey: mapsKeys.proximos(de ?? 0, raio, tipo),
    queryFn: () => api.locaisProximos(de as number, raio, tipo),
    enabled: !!de,
  })

export const useCamadas = () => useQuery({ queryKey: mapsKeys.camadas, queryFn: api.listarCamadas })

export const useFeicoes = (params?: Record<string, unknown>) =>
  useQuery({ queryKey: mapsKeys.feicoes(params), queryFn: () => api.listarFeicoes(params) })

export const useOrtofotos = () => useQuery({ queryKey: mapsKeys.ortofotos, queryFn: () => api.listarOrtofotos() })
export const usePlanos = () => useQuery({ queryKey: mapsKeys.planos, queryFn: api.listarPlanos })
export const useRotas = () => useQuery({ queryKey: mapsKeys.rotas, queryFn: api.listarRotas })
export const useGeofences = () => useQuery({ queryKey: mapsKeys.geofences, queryFn: api.listarGeofences })

/** Geocodificar muda o mapa inteiro (um pin a menos na fila) — invalida os dois. */
export function useGeocodificar() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, forcar }: { id: number; forcar?: boolean }) => api.geocodificarLocal(id, forcar),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mapsKeys.mapa })
      qc.invalidateQueries({ queryKey: ['maps', 'locais'] })
    },
  })
}

export function useCalcularPlano() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.calcularPlano(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: mapsKeys.planos }),
  })
}

export function useCriarPlanoDoLocal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.criarPlanoDoLocal,
    onSuccess: () => qc.invalidateQueries({ queryKey: mapsKeys.planos }),
  })
}

export function useOtimizarRota() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.otimizarRota(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: mapsKeys.rotas }),
  })
}

/** Traçar ≠ otimizar: desenha na ordem que está, sem reordenar as paradas. */
export function useTracarRota() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.tracarRota(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: mapsKeys.rotas }),
  })
}
