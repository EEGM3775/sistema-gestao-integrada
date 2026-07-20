import apiClient from '@/api/apiClient'
import { CALENDAR_BASE } from '../calendarClient'
import type { ObraLocalidade, Municipio, FeriadosStatus } from '../../types'

/** Obras do tenant com a localidade (uf/ibge/cidade) resolvida do endereço. */
export async function fetchObrasLocalidades(): Promise<ObraLocalidade[]> {
  const { data } = await apiClient.get<{ obras: ObraLocalidade[] }>(`${CALENDAR_BASE}localidades/`)
  return data.obras
}

/** Municípios de uma UF (serviço geo compartilhado). */
export async function fetchMunicipios(uf: string): Promise<Municipio[]> {
  const { data } = await apiClient.get<{ municipios: Municipio[] }>('geo/municipios/', {
    params: { uf },
  })
  return data.municipios
}

/** Status da última sincronização de feriados (403 para não-superuser). */
export async function fetchFeriadosStatus(): Promise<FeriadosStatus> {
  const { data } = await apiClient.get<FeriadosStatus>(`${CALENDAR_BASE}feriados/status/`)
  return data
}
