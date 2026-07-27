import { useEffect, useRef, useState } from 'react'
import maplibregl, { type Map as MapLibreMap, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useTheme } from '@/hooks/useTheme'
import { getAccessToken } from '@/api/tokenStore'

/**
 * `<Mapa>` — a superfície espacial da Malha (MAP.1).
 *
 * Mora no kit COMPARTILHADO, não num quinto kit de módulo: obra, fornecedor,
 * almoxarifado e voo caem no mesmo mapa, e um mapa por módulo seria a dívida
 * dos kits paralelos multiplicada (docs/frontend.md §2).
 *
 * **MapLibre, e não Leaflet**, por dois motivos concretos: o mapa da empresa
 * desenha milhares de feições (vector/WebGL aguenta, DOM não) e o estilo é
 * JSON — claro e escuro saem do mesmo mecanismo de tema, sem trocar de
 * provedor de tile. O Leaflet fica no drone; são dois contextos, não uma
 * migração.
 *
 * **A precisão é desenhada, não escrita.** Cada pin ganha um halo cujo raio
 * cresce quando a coordenada é grossa: pin de porta é um ponto firme; centroide
 * de município é uma mancha larga. É a regra de ouro da planta §5 virada em
 * pixel — quem olha o mapa entende a incerteza sem ler legenda.
 */

export interface PontoMapa {
  id: string | number
  lon: number
  lat: number
  nome: string
  /** `exata` | `endereco` | `cep` | `municipio` | `desconhecida` */
  precisao?: string
  tipo?: string
  detalhe?: string
}

export interface CamadaGeoJSON {
  id: string
  data: GeoJSON.FeatureCollection | GeoJSON.Feature | GeoJSON.Geometry
  cor?: string
  largura?: number
  preenchimento?: boolean
}

export interface CamadaRaster {
  id: string
  /** URLs de tile com `{z}/{x}/{y}` — do backend, com gate (nunca o COG cru). */
  tiles: string[]
  opacidade?: number
}

interface Props {
  pontos?: PontoMapa[]
  camadas?: CamadaGeoJSON[]
  rasters?: CamadaRaster[]
  altura?: number | string
  centro?: [number, number]
  zoom?: number
  /** Enquadra automaticamente tudo que foi passado (default: sim). */
  ajustar?: boolean
  satelite?: boolean
  onSelecionar?: (id: string | number) => void
  onClicarMapa?: (lon: number, lat: number) => void
}

/** Raio do halo por precisão (px). É a incerteza em escala visual. */
const HALO: Record<string, number> = {
  exata: 0, endereco: 7, cep: 13, municipio: 22, desconhecida: 0,
}
const COR: Record<string, string> = {
  obra: '#E79A22', empreendimento: '#274D8C', fornecedor: '#1D9AA6',
  local_estoque: '#3E9C6E', unidade: '#8C5BD6', avulso: '#8892A6',
}
// Centro do Brasil — enquadramento inicial de quem ainda não tem nenhum pin.
const BRASIL: [number, number] = [-51.9, -14.2]

function estilo(escuro: boolean, satelite: boolean): StyleSpecification {
  // Provedores GRÁTIS por padrão (planta §9). O tile público do OSM fica de
  // fora de propósito: a política de uso dele restringe uso comercial pesado, e
  // um SaaS multi-tenant é exatamente isso. Pago entra como knob de payment/.
  const base = satelite
    ? {
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        attribution: 'Esri, Maxar, Earthstar Geographics',
      }
    : {
        tiles: [`https://basemaps.cartocdn.com/${escuro ? 'dark_all' : 'light_all'}/{z}/{x}/{y}{ratio}.png`.replace('{ratio}', '')],
        attribution: '© OpenStreetMap · © CARTO',
      }
  return {
    version: 8,
    sources: { base: { type: 'raster', tileSize: 256, ...base } },
    layers: [{ id: 'base', type: 'raster', source: 'base' }],
  }
}

function paraFeatures(pontos: PontoMapa[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: pontos.map((p) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] },
      properties: {
        id: String(p.id),
        nome: p.nome,
        detalhe: p.detalhe ?? '',
        precisao: p.precisao ?? 'exata',
        halo: HALO[p.precisao ?? 'exata'] ?? 0,
        cor: COR[p.tipo ?? 'avulso'] ?? COR.avulso,
      },
    })),
  }
}

export function Mapa({
  pontos = [], camadas = [], rasters = [], altura = 460,
  centro, zoom = 4, ajustar = true, satelite = false,
  onSelecionar, onClicarMapa,
}: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapa = useRef<MapLibreMap | null>(null)
  const [pronto, setPronto] = useState(false)
  const { resolved } = useTheme()
  const escuro = resolved === 'dark'

  // ── criação (uma vez) ────────────────────────────────────────────────────
  useEffect(() => {
    if (!container.current || mapa.current) return
    const m = new maplibregl.Map({
      container: container.current,
      style: estilo(escuro, satelite),
      center: centro ?? BRASIL,
      zoom: centro ? zoom : 3.4,
      attributionControl: { compact: true },
      // Tile de ortofoto sai do NOSSO backend, com entitlement e escopo de
      // tenant (o COG do drone é `permitAll` — achado S10). O MapLibre não
      // manda header sozinho: é aqui que o access token entra.
      transformRequest: (url) => {
        if (url.startsWith('/api/') || url.includes('/api/maps/')) {
          const token = getAccessToken()
          return token ? { url, headers: { Authorization: `Bearer ${token}` } } : { url }
        }
        return { url }
      },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }))
    m.on('load', () => setPronto(true))
    if (onClicarMapa) {
      m.on('click', (e) => {
        const alvos = m.queryRenderedFeatures(e.point, { layers: ['pinos'] })
        if (!alvos.length) onClicarMapa(e.lngLat.lng, e.lngLat.lat)
      })
    }
    mapa.current = m
    return () => { m.remove(); mapa.current = null }
    // Recriar o mapa a cada mudança de prop mataria o estado de navegação do
    // usuário (zoom, pan). Estilo, dados e tema são atualizados nos efeitos
    // abaixo, sobre a MESMA instância.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── tema e basemap ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapa.current || !pronto) return
    mapa.current.setStyle(estilo(escuro, satelite))
    // `setStyle` descarta as camadas próprias; o efeito de dados abaixo as
    // reconstrói no `styledata` seguinte.
    const m = mapa.current
    const recarregar = () => { desenhar(m, pontos, camadas, rasters, escuro); m.off('styledata', recarregar) }
    m.on('styledata', recarregar)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escuro, satelite, pronto])

  // ── dados ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapa.current || !pronto) return
    desenhar(mapa.current, pontos, camadas, rasters, escuro)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pontos, camadas, rasters, pronto])

  // ── enquadramento ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapa.current || !pronto || !ajustar || !pontos.length) return
    const limites = new maplibregl.LngLatBounds()
    pontos.forEach((p) => limites.extend([p.lon, p.lat]))
    mapa.current.fitBounds(limites, { padding: 64, maxZoom: 14, duration: 420 })
  }, [pontos, ajustar, pronto])

  // ── seleção ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const m = mapa.current
    if (!m || !pronto || !onSelecionar) return
    const clique = (e: maplibregl.MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.id
      if (id != null) onSelecionar(id as string)
    }
    const entrar = () => { m.getCanvas().style.cursor = 'pointer' }
    const sair = () => { m.getCanvas().style.cursor = '' }
    m.on('click', 'pinos', clique)
    m.on('mouseenter', 'pinos', entrar)
    m.on('mouseleave', 'pinos', sair)
    return () => { m.off('click', 'pinos', clique); m.off('mouseenter', 'pinos', entrar); m.off('mouseleave', 'pinos', sair) }
  }, [onSelecionar, pronto])

  return (
    <div
      ref={container}
      style={{
        height: typeof altura === 'number' ? `${altura}px` : altura,
        width: '100%',
        borderRadius: 'var(--r-md)',
        overflow: 'hidden',
        border: '1px solid var(--line)',
        background: 'var(--surface-2)',
      }}
    />
  )
}

/** (Re)desenha as camadas próprias sobre o estilo atual. */
function desenhar(
  m: MapLibreMap,
  pontos: PontoMapa[],
  camadas: CamadaGeoJSON[],
  rasters: CamadaRaster[],
  escuro: boolean,
) {
  if (!m.isStyleLoaded()) return

  rasters.forEach((r) => {
    const id = `raster-${r.id}`
    if (m.getSource(id)) return
    m.addSource(id, { type: 'raster', tiles: r.tiles, tileSize: 256 })
    m.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': r.opacidade ?? 0.85 } })
  })

  camadas.forEach((c) => {
    const id = `geo-${c.id}`
    const cor = c.cor ?? '#E79A22'
    const dados = (c.data.type === 'FeatureCollection' || c.data.type === 'Feature'
      ? c.data
      : { type: 'Feature' as const, geometry: c.data, properties: {} }) as GeoJSON.FeatureCollection | GeoJSON.Feature
    const fonte = m.getSource(id) as maplibregl.GeoJSONSource | undefined
    if (fonte) { fonte.setData(dados); return }
    m.addSource(id, { type: 'geojson', data: dados })
    if (c.preenchimento !== false) {
      m.addLayer({ id: `${id}-fill`, type: 'fill', source: id, paint: { 'fill-color': cor, 'fill-opacity': 0.18 }, filter: ['==', ['geometry-type'], 'Polygon'] })
    }
    m.addLayer({ id: `${id}-line`, type: 'line', source: id, paint: { 'line-color': cor, 'line-width': c.largura ?? 2.5 } })
  })

  const dados = paraFeatures(pontos)
  const fonte = m.getSource('locais') as maplibregl.GeoJSONSource | undefined
  if (fonte) { fonte.setData(dados); return }

  m.addSource('locais', { type: 'geojson', data: dados })
  // Halo da incerteza — desenhado ANTES do pino para ficar por baixo.
  m.addLayer({
    id: 'halos',
    type: 'circle',
    source: 'locais',
    filter: ['>', ['get', 'halo'], 0],
    paint: {
      'circle-radius': ['get', 'halo'],
      'circle-color': ['get', 'cor'],
      'circle-opacity': 0.16,
      'circle-stroke-width': 1,
      'circle-stroke-color': ['get', 'cor'],
      'circle-stroke-opacity': 0.4,
    },
  })
  m.addLayer({
    id: 'pinos',
    type: 'circle',
    source: 'locais',
    paint: {
      'circle-radius': 6,
      'circle-color': ['get', 'cor'],
      'circle-stroke-width': 2,
      'circle-stroke-color': escuro ? '#0E1116' : '#FFFFFF',
    },
  })

  const balao = new maplibregl.Popup({ closeButton: false, offset: 12 })
  m.on('mouseenter', 'pinos', (e) => {
    const f = e.features?.[0]
    if (!f) return
    const p = f.properties as Record<string, string>
    const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number]
    balao
      .setLngLat(coords)
      .setHTML(
        `<div style="font-family:system-ui;font-size:12.5px;line-height:1.35">
           <b>${escapar(p.nome)}</b>
           ${p.detalhe ? `<br><span style="opacity:.75">${escapar(p.detalhe)}</span>` : ''}
           <br><span style="opacity:.6;font-size:11px">Precisão: ${escapar(p.precisao)}</span>
         </div>`,
      )
      .addTo(m)
  })
  m.on('mouseleave', 'pinos', () => balao.remove())
}

function escapar(texto: string): string {
  return String(texto ?? '').replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] ?? c))
}

export default Mapa
