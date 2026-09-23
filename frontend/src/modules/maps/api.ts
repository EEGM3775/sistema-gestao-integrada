import apiClient from '@/api/apiClient'
import type {
  Camada, CandidatoEndereco, Feicao, Geofence, Local, LocalResumo, MapaDaEmpresa,
  MemoriaDoVoo, Ortofoto, Paginado, PlanoVoo, Rota, StatusMaps, ViolacaoDeJanela,
} from './types'

const base = '/maps'

/** Mapa da empresa + fila de decisão. Não exige o módulo — `Local` é fundação. */
export const carregarMapa = () =>
  apiClient.get<MapaDaEmpresa>(`${base}/mapa/`).then((r) => r.data)

export const statusMaps = () =>
  apiClient.get<StatusMaps>(`${base}/status/`).then((r) => r.data)

// ── Locais (fundação) ──────────────────────────────────────────────────────
export const listarLocais = (params?: Record<string, unknown>) =>
  apiClient.get<Paginado<Local>>(`${base}/locais/`, { params }).then((r) => r.data)

export const salvarLocal = (dados: Partial<Local> & { ponto?: { lon: number; lat: number } | null }) =>
  dados.local_id
    ? apiClient.patch<Local>(`${base}/locais/${dados.local_id}/`, dados).then((r) => r.data)
    : apiClient.post<Local>(`${base}/locais/`, dados).then((r) => r.data)

export const geocodificarLocal = (id: number, forcar = false) =>
  apiClient
    .post<{ geocodificado: boolean; motivo: string; local: Local }>(
      `${base}/locais/${id}/geocodificar/${forcar ? '?forcar=1' : ''}`,
    )
    .then((r) => r.data)

export const locaisProximos = (de: number, raio_km: number, tipo?: string) =>
  apiClient
    .get<{ origem: LocalResumo; raio_km: number; resultados: LocalResumo[] }>(
      `${base}/locais/proximos/`, { params: { de, raio_km, tipo } },
    )
    .then((r) => r.data)

// ── Camadas e feições ──────────────────────────────────────────────────────
export const listarCamadas = () =>
  apiClient.get<Paginado<Camada>>(`${base}/camadas/`).then((r) => r.data)

export const listarFeicoes = (params?: Record<string, unknown>) =>
  apiClient.get<Paginado<Feicao>>(`${base}/feicoes/`, { params }).then((r) => r.data)

// ── Ortofotos ──────────────────────────────────────────────────────────────
export const listarOrtofotos = (params?: Record<string, unknown>) =>
  apiClient.get<Paginado<Ortofoto>>(`${base}/ortofotos/`, { params }).then((r) => r.data)

/** Template de tile servido pelo BACKEND (com gate), nunca o COG cru do drone. */
export const tilesDaOrtofoto = (id: number) =>
  `${apiClient.defaults.baseURL ?? '/api'}${base}/ortofotos/${id}/tiles/{z}/{x}/{y}/`

// ── Planos de voo ──────────────────────────────────────────────────────────
export const listarPlanos = () =>
  apiClient.get<Paginado<PlanoVoo>>(`${base}/planos-voo/`).then((r) => r.data)

export const calcularPlano = (id: number) =>
  apiClient
    .post<{ plano: PlanoVoo; memoria: MemoriaDoVoo }>(`${base}/planos-voo/${id}/calcular/`)
    .then((r) => r.data)

/**
 * O plano nasce de um local que a empresa já tem — perímetro do canteiro se
 * houver, círculo de raio se não. A resposta diz qual dos dois aconteceu, e a
 * tela repete isso: voo sobre um círculo de 150 m não é voo sobre o canteiro.
 */
export const criarPlanoDoLocal = (dados: {
  local: number; nome?: string; tipo?: string; raio_m?: number; gsd_alvo_cm?: number
}) =>
  apiClient
    .post<{ plano: PlanoVoo; origem_da_area: 'perimetro' | 'raio'; raio_m: number | null }>(
      `${base}/planos-voo/do-local/`, dados,
    )
    .then((r) => r.data)

/**
 * Baixa o plano no formato do drone. Passa pelo axios (e não por `window.open`)
 * porque o endpoint exige o header de autorização — o access token vive em
 * memória, não em cookie, então uma navegação direta chegaria sem credencial.
 */
export async function exportarPlano(id: number, formato: 'kml' | 'plan' | 'litchi' | 'wpml', nome: string) {
  const resposta = await apiClient.get(`${base}/planos-voo/${id}/exportar/`, {
    params: { formato }, responseType: 'blob',
  })
  const extensao = { kml: 'kml', plan: 'plan', litchi: 'csv', wpml: 'kmz' }[formato]
  const url = URL.createObjectURL(resposta.data as Blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${nome.replace(/[^\w-]+/g, '_')}.${extensao}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// ── Rotas ──────────────────────────────────────────────────────────────────
export const listarRotas = () =>
  apiClient.get<Paginado<Rota>>(`${base}/rotas/`).then((r) => r.data)

export const otimizarRota = (id: number) =>
  apiClient
    .post<{ rota: Rota; violacoes_de_janela: ViolacaoDeJanela[] }>(`${base}/rotas/${id}/otimizar/`)
    .then((r) => r.data)

export const tracarRota = (id: number) =>
  apiClient.post<Rota>(`${base}/rotas/${id}/tracar/`).then((r) => r.data)

// ── Geofences ──────────────────────────────────────────────────────────────
export const listarGeofences = () =>
  apiClient.get<Paginado<Geofence>>(`${base}/geofences/`).then((r) => r.data)

export const gerarGeofence = (dados: { local: number; nome?: string; tipo?: string; raio_m?: number }) =>
  apiClient.post<Geofence>(`${base}/geofences/gerar/`, dados).then((r) => r.data)

// ── MAP.5 — detecção de endereço ───────────────────────────────────────────
export const detectarEndereco = (payload: { texto?: string; xml?: string; papel?: string }) =>
  apiClient
    .post<{ candidatos: CandidatoEndereco[] }>(`${base}/detectar-endereco/`, payload)
    .then((r) => r.data.candidatos)
