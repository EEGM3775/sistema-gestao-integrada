import { useQuery } from '@tanstack/react-query'
import { fetchObrasLocalidades, fetchMunicipios, fetchFeriadosStatus } from '../api/endpoints/localidades'

/** Obras do tenant com localidade resolvida (para o seletor de obra). As obras
 * (e seus endereços) vivem em outro módulo; revalida ao montar para detectar
 * obra excluída ou endereço alterado e reconciliar a seleção persistida. */
export function useObrasLocalidades() {
  return useQuery({
    queryKey: ['calendar', 'localidades', 'obras'],
    queryFn: fetchObrasLocalidades,
    staleTime: 5 * 60 * 1000,
    refetchOnMount: 'always',
  })
}

/** Municípios de uma UF; só busca quando a UF está definida. */
export function useMunicipios(uf: string) {
  return useQuery({
    queryKey: ['geo', 'municipios', uf],
    queryFn: () => fetchMunicipios(uf),
    enabled: !!uf,
    staleTime: 60 * 60 * 1000,
  })
}

/**
 * Status de sincronização de feriados — só o superuser recebe 200; para os
 * demais o endpoint responde 403 e o hook devolve `null` (banner some).
 */
export function useFeriadosStatus() {
  return useQuery({
    queryKey: ['calendar', 'feriados', 'status'],
    queryFn: fetchFeriadosStatus,
    retry: false,          // 403 não deve re-tentar
    staleTime: 10 * 60 * 1000,
  })
}
